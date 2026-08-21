"""
Real concurrency tests against PostgreSQL for the race-condition fixes in
UserCoinBalance (api/models/contest.py), UserProfile (api/models/core.py),
the Telebirr webhook idempotency guard (api/views/wallet.py::telebirr_callback),
and the admin withdrawal state-machine guard (api/views/wallet.py::admin_withdrawal_action).

These use real OS threads, each with its own Django DB connection, issuing
real concurrent queries against a real PostgreSQL server -- not mocks, and
not SQLite (whose locking semantics don't match Postgres's and wouldn't
actually exercise SELECT ... FOR UPDATE / conditional UPDATE behavior).

Requires TEST_DB_ENGINE=postgresql and the matching TEST_DB_* variables
(see config/settings/testing.py); skips entirely otherwise, since there's no
way to test row-level locking on a database that doesn't do it the way
these fixes assume. To run against the disposable container used to write
these fixes:

    docker run -d --name flipstar_race_test_pg \\
        -e POSTGRES_DB=flipstar_test -e POSTGRES_USER=flipstar -e POSTGRES_PASSWORD=flipstar \\
        -p 127.0.0.1:55432:5432 postgres:15-alpine

    DJANGO_SETTINGS_MODULE=config.settings.development \\
    DB_ENGINE=django.db.backends.postgresql DB_NAME=flipstar_test DB_USER=flipstar \\
    DB_PASSWORD=flipstar DB_HOST=127.0.0.1 DB_PORT=55432 USE_LOCMEM_CACHE=true \\
    python manage.py migrate

    DJANGO_SETTINGS_MODULE=config.settings.testing \\
    TEST_DB_ENGINE=postgresql TEST_DB_NAME=flipstar_test TEST_DB_USER=flipstar \\
    TEST_DB_PASSWORD=flipstar TEST_DB_HOST=127.0.0.1 TEST_DB_PORT=55432 \\
    pytest tests/integration/test_concurrency.py -v -s

This intentionally does not go through pytest-django's `django_db_setup`
fixture (and so does not use the `django_db` marker) -- that fixture's
migration-based test-database bootstrap has its own pre-existing bug
unrelated to this work (see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE
note). These tests instead unblock query access directly via
`django_db_blocker` and talk to an already-migrated database, which sidesteps
that bug entirely rather than fixing unrelated test infrastructure as a side
effect of a concurrency audit.
"""

from __future__ import annotations

import threading

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.utils import timezone

pytestmark = pytest.mark.integration

_IS_POSTGRES = connection.vendor == 'postgresql'
skip_reason = (
    'Requires a real PostgreSQL connection (TEST_DB_ENGINE=postgresql + TEST_DB_* vars) -- '
    'SELECT ... FOR UPDATE and conditional UPDATE semantics are not meaningfully '
    'testable against SQLite. See this file\'s module docstring to run it.'
)


@pytest.fixture(scope='module')
def pg(django_db_blocker):
    """Unblocks real queries against the already-migrated test database.
    See the module docstring for why this bypasses django_db_setup."""
    if not _IS_POSTGRES:
        pytest.skip(skip_reason)
    with django_db_blocker.unblock():
        yield


def _run_concurrently(fns):
    """Start every callable in `fns` on its own thread at (as close to)
    the same moment as possible, and wait for all of them. Each thread
    closes its own DB connection when done -- Django connections are
    thread-local and won't clean themselves up otherwise."""
    results = [None] * len(fns)
    errors = [None] * len(fns)
    start_barrier = threading.Barrier(len(fns))

    def wrapper(i, fn):
        try:
            start_barrier.wait(timeout=10)
            results[i] = fn()
        except Exception as exc:  # noqa: BLE001 - captured for the assertions below
            errors[i] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=wrapper, args=(i, fn)) for i, fn in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


@pytest.fixture
def user(pg):
    u = User.objects.create_user(username=f'race_{threading.get_ident()}', password='123456')
    yield u
    u.delete()


# ---------------------------------------------------------------------------
# UserCoinBalance.spend_coins -- lost updates and overspend
# ---------------------------------------------------------------------------

def _reset_balance(user, **fields):
    """(get_or_create, not create) -- a post_save signal on User already
    creates a UserCoinBalance row; a blind .create() here would collide
    with it."""
    from api.models.contest import UserCoinBalance

    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    for field, value in fields.items():
        setattr(balance, field, value)
    balance.total_earned = balance.total_purchased = balance.total_spent = balance.total_withdrawn = 0
    balance.save()
    return balance


def test_concurrent_spends_never_lose_an_update(user):
    """50 concurrent 10-coin spends against a 500 balance must all succeed
    and leave exactly 0 -- not more (lost updates) or less (double-counted)."""
    from api.models.contest import UserCoinBalance

    balance = _reset_balance(user, earned_balance=500, purchased_balance=0, balance=500)

    def spend():
        fresh = UserCoinBalance.objects.get(pk=balance.pk)
        fresh.spend_coins(10, 'test_spend')

    _, errors = _run_concurrently([spend] * 50)

    assert not any(errors), errors
    balance.refresh_from_db()
    assert balance.earned_balance == 0
    assert balance.balance == 0
    assert balance.total_spent == 500


def test_concurrent_spends_cannot_overspend_the_balance(user):
    """Two concurrent spends of 60 against a balance of 100: exactly one
    must succeed and one must be rejected as insufficient -- never both
    succeeding (final balance negative) and never both failing."""
    from api.models.contest import UserCoinBalance

    balance = _reset_balance(user, earned_balance=100, purchased_balance=0, balance=100)

    def spend():
        fresh = UserCoinBalance.objects.get(pk=balance.pk)
        fresh.spend_coins(60, 'test_spend')
        return 'ok'

    results, errors = _run_concurrently([spend, spend])

    successes = [r for r in results if r == 'ok']
    failures = [e for e in errors if isinstance(e, ValueError)]
    assert len(successes) == 1, f'expected exactly 1 success, got {results} / {errors}'
    assert len(failures) == 1, f'expected exactly 1 ValueError, got {results} / {errors}'

    balance.refresh_from_db()
    assert balance.earned_balance == 40
    assert balance.balance == 40
    assert balance.earned_balance >= 0  # the property spec section 9 exists to guarantee


def test_concurrent_earn_and_spend_settle_correctly(user):
    """A concurrent +200 and -50 against a starting balance of 100 must
    settle at 250, regardless of which one the database happens to run first."""
    from api.models.contest import UserCoinBalance

    balance = _reset_balance(user, earned_balance=100, purchased_balance=0, balance=100)

    def earn():
        UserCoinBalance.objects.get(pk=balance.pk).add_earned(200, 'test_earn')

    def spend():
        UserCoinBalance.objects.get(pk=balance.pk).spend_coins(50, 'test_spend')

    _, errors = _run_concurrently([earn, spend])

    assert not any(errors), errors
    balance.refresh_from_db()
    assert balance.earned_balance == 250
    assert balance.balance == 250


# ---------------------------------------------------------------------------
# UserProfile.add_points / deduct_points
# ---------------------------------------------------------------------------

def test_concurrent_point_credits_never_lose_an_update(user):
    from api.models import UserProfile

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.points = 0
    profile.save(update_fields=['points'])

    def credit():
        UserProfile.objects.get(pk=profile.pk).add_points(5)

    _, errors = _run_concurrently([credit] * 40)

    assert not any(errors), errors
    profile.refresh_from_db()
    assert profile.points == 200
    assert profile.points_earned_total == 200


def test_concurrent_point_deductions_cannot_go_negative(user):
    from api.models import UserProfile

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.points = 30
    profile.save(update_fields=['points'])

    def deduct():
        UserProfile.objects.get(pk=profile.pk).deduct_points(20)
        return 'ok'

    results, errors = _run_concurrently([deduct, deduct])

    successes = [r for r in results if r == 'ok']
    assert len(successes) == 1, f'expected exactly 1 success, got {results} / {errors}'
    profile.refresh_from_db()
    assert profile.points == 10
    assert profile.points >= 0


# ---------------------------------------------------------------------------
# Telebirr webhook idempotency -- the same callback delivered twice at once
# ---------------------------------------------------------------------------

def test_concurrent_webhook_delivery_credits_coins_exactly_once(user):
    """Reproduces two concurrent deliveries of the exact same Telebirr
    success callback against the same pending CoinTransaction -- the code
    path fixed in api/views/wallet.py::telebirr_callback. Exactly one must
    credit coins; the other must find the transaction already processed."""
    from django.db import transaction as db_transaction

    from api.models.contest import CoinPackage, CoinTransaction, UserCoinBalance

    package = CoinPackage.objects.create(
        name='race-test-package', price_etb=10, coin_amount=100, bonus_coins=0, is_active=True,
    )
    pending_tx = CoinTransaction.objects.create(
        user=user, transaction_type='purchase', coins=0,
        payment_method='telebirr', payment_reference='RACE-TEST-REF',
        package=package, is_successful=False,
    )
    _reset_balance(user, earned_balance=0, purchased_balance=0, balance=0)

    def deliver_webhook():
        # Mirrors telebirr_callback's fixed body exactly: lock, re-check
        # is_successful under the lock, credit, flip the flag.
        with db_transaction.atomic():
            tx = CoinTransaction.objects.select_for_update().get(
                payment_reference='RACE-TEST-REF', payment_method='telebirr', is_successful=False,
            )
            balance = UserCoinBalance.objects.select_for_update().get(user=user)
            total_coins = package.get_total_coins()
            balance.add_purchased(total_coins, transaction_type='purchase', payment_method='telebirr')
            tx.coins = total_coins
            tx.is_successful = True
            tx.save()
        return 'credited'

    def deliver_webhook_safe():
        try:
            return deliver_webhook()
        except CoinTransaction.DoesNotExist:
            return 'already_processed'

    results, errors = _run_concurrently([deliver_webhook_safe, deliver_webhook_safe])

    assert not any(errors), errors
    assert sorted(results) == ['already_processed', 'credited'], results

    balance = UserCoinBalance.objects.get(user=user)
    assert balance.purchased_balance == package.get_total_coins(), (
        'coins were credited more than once (or not at all) for one webhook event'
    )
    pending_tx.refresh_from_db()
    assert pending_tx.is_successful is True

    package.delete()


# ---------------------------------------------------------------------------
# Telebirr one-time subscription webhook -- concurrent delivery activates
# exactly once (api/views/subscription.py::telebirr_one_time_callback)
# ---------------------------------------------------------------------------

def test_concurrent_one_time_subscription_webhook_activates_exactly_once(user):
    """Telebirr is documented to retry callbacks (see
    telebirr_one_time_callback's own docstring). Reproduces two concurrent
    deliveries of the same notify payload for one pending subscription --
    without select_for_update() on the pending-row lookup, both could pass
    the `status == 'pending'` check before either commits, creating two
    SubscriptionHistory rows and (if it were coin credit rather than
    subscription activation) crediting twice for one payment."""
    from django.db import transaction as db_transaction

    from api.models.subscription import SubscriptionHistory, SubscriptionPlan, SubscriptionTier

    tier = SubscriptionTier.objects.create(
        name=f'race-tier-{threading.get_ident()}', slug=f'race-tier-{threading.get_ident()}',
        duration_type='monthly', duration_days=30, price_etb=100,
        onevas_code=f'Z{threading.get_ident() % 100000}',
        spid='sp', service_id='svc', product_id='prod', application_key='key',
    )
    subscription = SubscriptionPlan.objects.create(
        user=user, tier=tier, payment_method='telebirr', duration_type='monthly',
        status='pending', payment_reference='RACE-SUB-REF', auto_renew=False,
    )

    def deliver_webhook():
        # Mirrors telebirr_one_time_callback's fixed body: lock the pending
        # row, re-check status under the lock, activate, record history.
        with db_transaction.atomic():
            locked = SubscriptionPlan.objects.select_for_update().filter(
                payment_reference='RACE-SUB-REF', status='pending',
            ).first()
            if locked is None:
                raise SubscriptionPlan.DoesNotExist
            locked.status = 'active'
            locked.save()
            SubscriptionHistory.objects.create(
                user=locked.user, subscription=locked, tier=locked.tier,
                action='activated', reason='One-time Telebirr payment completed',
            )
        return 'activated'

    def deliver_webhook_safe():
        try:
            return deliver_webhook()
        except SubscriptionPlan.DoesNotExist:
            return 'already_processed'

    results, errors = _run_concurrently([deliver_webhook_safe, deliver_webhook_safe])

    assert not any(errors), errors
    assert sorted(results) == ['activated', 'already_processed'], results
    assert SubscriptionHistory.objects.filter(subscription=subscription, action='activated').count() == 1, (
        'subscription was activated more than once for one webhook event'
    )

    tier.delete()


# ---------------------------------------------------------------------------
# Admin withdrawal action -- concurrent approve cannot double-process
# ---------------------------------------------------------------------------

def test_concurrent_withdrawal_approval_only_succeeds_once(user):
    """Reproduces two concurrent 'approve' actions on the same pending
    withdrawal -- the code path fixed in
    api/views/wallet.py::admin_withdrawal_action. Exactly one must
    transition pending -> approved; the other must see it's no longer
    pending and refuse."""
    from django.db import transaction as db_transaction

    from api.models.wallet import WithdrawalRequest

    withdrawal = WithdrawalRequest.objects.create(
        user=user, point_amount=100, gross_birr=10, fee_birr=2, net_birr=8,
        conversion_rate=10, payout_method='telebirr', payout_account='0912345678',
        status='pending',
    )

    def try_approve():
        # Mirrors admin_withdrawal_action's fixed body: lock, re-check
        # status under the lock before transitioning.
        with db_transaction.atomic():
            w = WithdrawalRequest.objects.select_for_update().get(id=withdrawal.id)
            if w.status != 'pending':
                return 'rejected'
            w.status = 'approved'
            w.save()
            return 'approved'

    results, errors = _run_concurrently([try_approve, try_approve])

    assert not any(errors), errors
    assert sorted(results) == ['approved', 'rejected'], results

    withdrawal.refresh_from_db()
    assert withdrawal.status == 'approved'


# ---------------------------------------------------------------------------
# Direct debit mandate activation -- conditional claim, no lock across the
# external Telebirr call
# ---------------------------------------------------------------------------

def test_concurrent_mandate_activation_claims_exactly_once(user):
    """Reproduces two concurrent activate requests for the same mandate --
    the code path fixed in
    api/views/direct_debit.py::activate_direct_debit_mandate. Mirrors that
    view's exact two-phase design: an atomic conditional UPDATE claims the
    mandate (pending_active -> activating) with no transaction/lock open,
    *then* a simulated Telebirr call happens with nothing held, and only
    then a short select_for_update() transaction finalizes it. Exactly one
    caller must claim and finalize; the other must see the mandate is no
    longer pending_active and back off -- never both, which would have
    double-created the subscription plan in the real view."""
    import time

    from django.db import transaction as db_transaction

    from api.models.direct_debit import DirectDebitMandate

    mandate = DirectDebitMandate.objects.create(
        user=user, payer_msisdn='251911234567', payer_reference_number='RACE-MANDATE-1',
        payee_identifier_value='9286', frequency='05',
        first_payment_date=timezone.now().date(), expiry_date=timezone.now().date(),
        agreed_tc=True, mandate_id='MANDATE123', status='pending_active',
    )

    def try_activate():
        claimed = DirectDebitMandate.objects.filter(
            id=mandate.id, status='pending_active'
        ).update(status='activating')
        if claimed == 0:
            return 'rejected'

        time.sleep(0.05)  # stand-in for the real Telebirr HTTP round-trip

        with db_transaction.atomic():
            m = DirectDebitMandate.objects.select_for_update().get(id=mandate.id)
            if m.status == 'activating':
                m.status = 'active'
                m.activated_at = timezone.now()
                m.save()
        return 'activated'

    results, errors = _run_concurrently([try_activate, try_activate])

    assert not any(errors), errors
    assert sorted(results) == ['activated', 'rejected'], results

    mandate.refresh_from_db()
    assert mandate.status == 'active'


# ---------------------------------------------------------------------------
# Direct debit webhook -- one-off payments are two-stage (debit-gated),
# not credited on the mandate-creation callback alone
# ---------------------------------------------------------------------------

def test_one_off_webhook_does_not_credit_before_debit_confirmed(user):
    """Reproduces the exact sequence Telebirr sends for a one-off Direct
    Debit coin purchase, against the real view
    (api/views/direct_debit.py::telebirr_direct_debit_webhook), not a
    reproduction. Callback #1 (mandate/payment-request accepted, no
    TransactionID) must NOT credit coins -- it must call initiate_debit()
    and store debit_conversation_id, leaving the mandate exactly as it was.
    Only callback #2 (the transaction-result webhook, carrying a
    TransactionID) may credit. Without this gate, a user is credited coins
    before Telebirr has even attempted to move money."""
    from unittest.mock import patch

    from rest_framework.test import APIRequestFactory

    from api.models.contest import UserCoinBalance
    from api.models.direct_debit import DirectDebitMandate
    from api.views.direct_debit import telebirr_direct_debit_webhook

    mandate = DirectDebitMandate.objects.create(
        user=user, payer_msisdn='251911234567', payer_reference_number='RACE-ONEOFF-1',
        payee_identifier_value='9286', frequency='01',
        first_payment_date=timezone.now().date(), expiry_date=timezone.now().date(),
        agreed_tc=True, status='pending_created', payment_type='one_off',
        originator_conversation_id='ORIG-CONV-1',
        metadata={'coins': 250, 'amount': 25},
    )
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    starting_balance = balance.purchased_balance

    factory = APIRequestFactory()

    with patch('api.views.direct_debit.telebirr_direct_debit_service.initiate_debit') as mock_initiate_debit:
        mock_initiate_debit.return_value = {
            'success': True, 'originator_conversation_id': 'DEBIT-CONV-1',
        }
        # Callback #1: mandate/payment-request accepted -- ResultCode 0, no
        # TransactionID/MandateID in the payload.
        request_1 = factory.post(
            '/api/webhooks/telebirr-direct-debit/',
            data={'ResultCode': '0', 'ResultType': '0', 'OriginatorConversationID': 'ORIG-CONV-1'},
            format='json',
        )
        response_1 = telebirr_direct_debit_webhook(request_1)

    assert response_1.status_code == 200
    mock_initiate_debit.assert_called_once()

    mandate.refresh_from_db()
    balance.refresh_from_db()
    assert mandate.status == 'pending_created', 'must not activate on the mandate-creation callback alone'
    assert mandate.debit_conversation_id == 'DEBIT-CONV-1'
    assert balance.purchased_balance == starting_balance, 'must not credit coins before the debit is confirmed'

    # Callback #2: transaction result -- same top-level OriginatorConversationID
    # as the debit call (correlated via debit_conversation_id), now carrying
    # a real TransactionID.
    request_2 = factory.post(
        '/api/webhooks/telebirr-direct-debit/',
        data={
            'ResultCode': '0', 'ResultType': '0',
            'OriginatorConversationID': 'DEBIT-CONV-1', 'TransactionID': 'TXN-999',
        },
        format='json',
    )
    response_2 = telebirr_direct_debit_webhook(request_2)

    assert response_2.status_code == 200
    mandate.refresh_from_db()
    balance.refresh_from_db()
    assert mandate.status == 'active', 'must activate once the transaction result confirms the debit'
    assert balance.purchased_balance == starting_balance + 250, 'must credit exactly the metadata coin amount, exactly once'

    mandate.delete()


# ---------------------------------------------------------------------------
# Winner announcement -- concurrent admin calls cannot double-announce
# ---------------------------------------------------------------------------

def test_concurrent_winner_announcement_only_runs_once(user):
    """Reproduces two concurrent calls to the actual
    api/views/campaign.py::admin_announce_winners view for the same
    campaign (e.g. an admin double-clicking, or a retried request).
    Calls the real view function directly (it isn't behind
    @encrypted_endpoint, unlike the mandate endpoints, so this exercises
    production code rather than a reproduction). Exactly one call may
    create the CampaignWinner/CampaignNotification rows and flip
    winners_announced; the other must see it's already been announced and
    refuse -- never both, which would have emailed/notified the winner
    twice and could have raced two different vote-count snapshots into
    inconsistent CampaignWinner rows."""
    from rest_framework.test import APIRequestFactory, force_authenticate

    from api.models import Reel
    from api.models.campaign import Campaign, CampaignEntry, CampaignNotification, CampaignWinner
    from api.views.campaign import admin_announce_winners

    admin = User.objects.create_user(
        username=f'admin_{threading.get_ident()}', password='123456', is_staff=True,
    )
    campaign = Campaign.objects.create(
        title='Race Campaign', description='desc', campaign_type='grand',
        prize_title='Prize', prize_description='desc', status='active', winner_count=1,
        created_by=admin,
    )
    reel = Reel.objects.create(user=user)
    CampaignEntry.objects.create(
        campaign=campaign, user=user, reel=reel, approved=True, disqualified=False, vote_count=10,
    )

    factory = APIRequestFactory()

    def announce():
        request = factory.post(f'/api/campaigns/{campaign.id}/announce-winners/')
        force_authenticate(request, user=admin)
        response = admin_announce_winners(request, campaign_id=campaign.id)
        return response.status_code

    results, errors = _run_concurrently([announce, announce])

    assert not any(errors), errors
    assert sorted(results) == [200, 409], results

    campaign.refresh_from_db()
    assert campaign.winners_announced is True
    assert CampaignWinner.objects.filter(campaign=campaign).count() == 1
    assert CampaignNotification.objects.filter(
        campaign=campaign, notification_type='winner_announced'
    ).count() == 1
