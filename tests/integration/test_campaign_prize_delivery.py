"""
What each competition pays, and that it pays exactly once.

    tier            winners   prize                    deadline
    Daily Sprint       20     1 GB weekly data         on provisioning
    Weekly Battle      10     1,000 ETB via Telebirr   10 days
    Monthly Star        5     5,000 ETB via Telebirr   10 days
    Grand Final         1     300,000 ETB via Telebirr 20 days

Two things here are worth more than the rest.

**The amount used to come from the request body.** api/views/crm.py read
``amount = request.data.get('amount', 1000)``, so what a winner was paid was
whatever the caller asked for. The figures are contractual, so they now come
from api/services/prize_structure.py and the package row is written over
rather than trusted.

**Paying twice is the expensive failure.** A duplicate Grand Final payout is
300,000 ETB that does not come back. The guard is a UNIQUE column, not a
check -- two callers racing both build the same idempotency key and the
database refuses the second INSERT, where a "does a row exist?" check lets
both through when they read in the same millisecond. Delivery is guarded
separately so a retry reuses the row and cannot re-send a settled prize.

Telebirr and the CRM are stubbed throughout: these tests are about the
workflow's own decisions -- what it records, what it refuses, what it counts
-- not about SOAP envelopes, which are covered in the integration tests for
those services.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from api.models import Reel
from api.models.campaign import Campaign
from api.models.campaign_extended import PostScore
from api.models.gift import WinnerGiftPackage, WinnerGiftTransaction
from api.services import prize_delivery
from api.services.campaign_eligibility import local_date
from api.services.prize_structure import (
    CRM,
    ONE_GB_IN_MB,
    PRIZES,
    TELEBIRR,
    amount_for,
    prize_for,
    winner_count_for,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def make_user(django_user_model):
    """A winner with a phone number of their own.

    UserProfile.phone_number is unique, so each one gets a distinct number --
    sharing one makes every test after the first fail on the constraint
    rather than on anything it was testing.
    """
    counter = {'n': 0}

    def _make(name=None, phone=None):
        counter['n'] += 1
        user = django_user_model.objects.create_user(
            username=name or f'winner_{counter["n"]}', password='x'
        )
        number = phone if phone is not None else f'09110{counter["n"]:05d}'
        if number and hasattr(user, 'profile'):
            user.profile.phone_number = number
            user.profile.save(update_fields=['phone_number'])
        return user

    return _make


@pytest.fixture(autouse=True)
def winners_can_receive_telebirr():
    """Every winner here can be paid, unless a test says otherwise.

    is_telebirr_user() reads a Telebirr SubscriptionPayment, which needs a
    whole subscription chain to build. These tests are about what delivery
    decides, not about how that flag is derived, so it is patched -- the
    same approach test_crm_winner_gifts.py takes. The tests that care about
    a winner who *cannot* be paid patch it back to False themselves.
    """
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True):
        yield


@pytest.fixture
def campaign(db):
    start = timezone.make_aware(
        timezone.datetime.combine(
            local_date(timezone.now()) - timedelta(days=6), timezone.datetime.min.time()
        )
    )
    return Campaign.objects.create(
        title='Weekly Battle',
        campaign_type='weekly',
        status='active',
        start_date=start,
        entry_deadline=start + timedelta(days=7) - timedelta(seconds=1),
    )


def b2c_accepted(**overrides):
    result = {
        'success': True,
        'originator_conversation_id': 'OCID-1',
        'conversation_id': 'CID-1',
    }
    result.update(overrides)
    return result


# ── the prize structure ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('tier', 'winners'), [('daily', 20), ('weekly', 10), ('monthly', 5), ('grand', 1)]
)
def test_each_tier_has_the_documented_number_of_winners(tier, winners):
    assert winner_count_for(tier) == winners


@pytest.mark.parametrize(
    ('tier', 'amount'),
    [('weekly', '1000.00'), ('monthly', '5000.00'), ('grand', '300000.00')],
)
def test_each_cash_tier_pays_the_documented_amount(tier, amount):
    assert amount_for(tier) == Decimal(amount)


def test_the_daily_prize_is_one_gigabyte_of_data():
    prize = prize_for('daily')

    assert prize.gift_type == 'data'
    assert prize.channel == CRM
    assert prize.amount == ONE_GB_IN_MB == Decimal('1024')
    assert '1 GB' in prize.description


@pytest.mark.parametrize('tier', ['weekly', 'monthly', 'grand'])
def test_cash_prizes_go_out_over_telebirr(tier):
    assert prize_for(tier).channel == TELEBIRR
    assert prize_for(tier).is_cash


@pytest.mark.parametrize(('tier', 'days'), [('weekly', 10), ('monthly', 10), ('grand', 20)])
def test_the_delivery_deadlines_are_what_was_promised(tier, days):
    assert prize_for(tier).delivery_days == days


def test_the_grand_final_winner_is_contacted_by_phone():
    """300,000 ETB is not a payout to make without speaking to somebody."""
    assert prize_for('grand').requires_phone_contact
    assert not prize_for('weekly').requires_phone_contact


def test_an_unknown_tier_is_refused_rather_than_guessed():
    """Paying a guessed amount is worse than not paying."""
    with pytest.raises(ValueError, match='No prize defined'):
        prize_for('fortnightly')


def test_amounts_are_decimal_not_float():
    """Money through a float is money that stops adding up."""
    for prize in PRIZES.values():
        assert isinstance(prize.amount, Decimal)


# ── awarding records the debt ───────────────────────────────────────────────


def test_awarding_records_everything_the_requirement_asks_for(campaign, make_user):
    winner = make_user()

    prize, created = prize_delivery.award(campaign, winner, 'weekly')

    assert created
    assert prize.campaign == campaign
    assert prize.winner == winner
    assert prize.winner_type == 'weekly'
    assert prize.payment_method == TELEBIRR
    assert prize.amount == Decimal('1000.00')
    assert prize.status == 'pending'
    assert prize.attempt_count == 0
    assert prize.delivered_at is None
    assert prize.deadline_at is not None
    assert prize.error_message == ''


def test_the_deadline_runs_from_the_close_not_from_the_award(campaign, make_user):
    """Ten days from when the competition closed, which is what was
    promised -- not from whenever an admin got round to it."""
    winner = make_user()

    prize, _ = prize_delivery.award(campaign, winner, 'weekly')

    assert prize.deadline_at == campaign.entry_deadline + timedelta(days=10)


def test_the_grand_final_gets_twenty_days(campaign, make_user):
    winner = make_user()

    prize, _ = prize_delivery.award(campaign, winner, 'grand')

    assert prize.deadline_at == campaign.entry_deadline + timedelta(days=20)


def test_the_amount_comes_from_the_structure_not_from_a_package_row(campaign, make_user):
    """An edited package row cannot change what a winner is paid.

    The row is reconciled against the documented figure on every award, so
    somebody setting 'weekly' to 999,999 in the admin changes nothing.
    """
    WinnerGiftPackage.objects.update_or_create(
        winner_type='weekly',
        defaults={
            'gift_type': 'cash',
            'payment_method': TELEBIRR,
            'amount': Decimal('999999.00'),
            'is_active': True,
        },
    )

    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')

    assert prize.amount == Decimal('1000.00')
    assert WinnerGiftPackage.objects.get(winner_type='weekly').amount == Decimal('1000.00')


def test_awarding_caps_at_the_documented_winner_count(campaign, make_user):
    """Eleven candidates, ten prizes."""
    winners = [make_user() for _ in range(11)]

    awarded = prize_delivery.award_all(campaign, winners, 'weekly')

    assert len(awarded) == 10


def test_awarding_does_not_reorder_or_reselect(campaign, make_user):
    """Who won was decided by the scoring engine, which is what applies the
    eligibility rules. This takes the list as given."""
    winners = [make_user(f'w{i}') for i in range(3)]

    awarded = prize_delivery.award_all(campaign, winners, 'weekly')

    assert [p.winner for p in awarded] == winners


# ── paying once ─────────────────────────────────────────────────────────────


def test_awarding_the_same_prize_twice_returns_the_same_row(campaign, make_user):
    winner = make_user()

    first, created_first = prize_delivery.award(campaign, winner, 'weekly')
    second, created_second = prize_delivery.award(campaign, winner, 'weekly')

    assert created_first
    assert not created_second
    assert first.pk == second.pk
    assert WinnerGiftTransaction.objects.filter(winner=winner).count() == 1


def test_a_rerun_of_the_whole_award_creates_no_second_set(campaign, make_user):
    """A retried selection job must not double the payroll."""
    winners = [make_user() for _ in range(5)]

    prize_delivery.award_all(campaign, winners, 'weekly')
    prize_delivery.award_all(campaign, winners, 'weekly')

    assert WinnerGiftTransaction.objects.filter(campaign=campaign).count() == 5


def test_the_database_refuses_a_duplicate_key(campaign, make_user):
    """The guarantee is a UNIQUE column, not a check that could read stale
    state. Asserted by trying to insert the duplicate directly."""
    from django.db import IntegrityError

    winner = make_user()
    prize, _ = prize_delivery.award(campaign, winner, 'weekly')

    with pytest.raises(IntegrityError):
        WinnerGiftTransaction.objects.create(
            winner=winner,
            winner_type='weekly',
            campaign=campaign,
            amount=Decimal('1000.00'),
            payment_method=TELEBIRR,
            idempotency_key=prize.idempotency_key,
        )


def test_the_same_winner_can_win_different_tiers(campaign, make_user):
    """One prize per tier, not one prize ever."""
    winner = make_user()

    prize_delivery.award(campaign, winner, 'weekly')
    prize_delivery.award(campaign, winner, 'monthly')

    assert WinnerGiftTransaction.objects.filter(winner=winner).count() == 2


def test_the_same_winner_can_win_the_same_tier_in_another_campaign(campaign, make_user):
    other = Campaign.objects.create(
        title='Next week',
        campaign_type='weekly',
        status='active',
        start_date=timezone.now(),
        entry_deadline=timezone.now() + timedelta(days=7),
    )
    winner = make_user()

    prize_delivery.award(campaign, winner, 'weekly')
    prize_delivery.award(other, winner, 'weekly')

    assert WinnerGiftTransaction.objects.filter(winner=winner).count() == 2


# ── successful payout ───────────────────────────────────────────────────────


def test_a_successful_payout_is_only_initiated_not_completed(campaign, make_user):
    """Telebirr accepting the instruction is not the winner having the money.

    Marking it delivered here is the bug this codebase's B2C work exists to
    avoid, and on the Grand Final it would be 300,000 ETB reported as paid
    that never moved.
    """
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value=b2c_accepted(),
    ):
        ok, _message = prize_delivery.deliver(prize)

    prize.refresh_from_db()
    assert ok
    assert prize.status == 'processing'
    assert prize.delivered_at is None, 'reported as delivered before Telebirr confirmed'
    assert prize.originator_conversation_id == 'OCID-1'
    assert prize.attempt_count == 1


def test_the_payout_asks_telebirr_for_the_documented_amount(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'monthly')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value=b2c_accepted(),
    ) as initiate:
        prize_delivery.deliver(prize)

    assert initiate.call_args.kwargs['amount'] == Decimal('5000.00')


def test_the_webhook_is_what_marks_it_delivered(campaign, make_user):
    """The confirmation path, and where delivered_at is finally set."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value=b2c_accepted(),
    ):
        prize_delivery.deliver(prize)

    prize.refresh_from_db()
    prize.mark_success('TELEBIRR-TX-9')

    prize.refresh_from_db()
    assert prize.status == 'success'
    assert prize.telebirr_transaction_id == 'TELEBIRR-TX-9'
    assert prize.delivered_at is not None


# ── duplicate callback ──────────────────────────────────────────────────────


def test_a_duplicate_callback_does_not_pay_twice(campaign, make_user):
    """Telebirr retries callbacks, and this endpoint has no signature check.

    The delivered timestamp must not move on the second delivery, or an
    already-settled prize becomes re-deliverable.
    """
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    prize.mark_success('TELEBIRR-TX-1')
    prize.refresh_from_db()
    first_delivered = prize.delivered_at

    # The webhook guards on status: only a 'processing' prize is transitioned.
    assert prize.is_settled

    ok, message = prize_delivery.deliver(prize)

    prize.refresh_from_db()
    assert not ok
    assert 'already' in message
    assert prize.delivered_at == first_delivered
    assert prize.attempt_count == 0, 'a refused delivery counted as an attempt'


def test_a_settled_prize_is_never_re_sent(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'grand')
    prize.mark_success('TX')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment'
    ) as initiate:
        ok, _ = prize_delivery.deliver(prize)

    assert not ok
    assert not initiate.called, 'a delivered prize was sent to Telebirr again'


def test_a_payout_in_flight_is_not_sent_again(campaign, make_user):
    """'processing' means Telebirr has the instruction. Sending another now
    is how one winner gets paid twice."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value=b2c_accepted(),
    ):
        prize_delivery.deliver(prize)

    prize.refresh_from_db()

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment'
    ) as initiate:
        ok, message = prize_delivery.deliver(prize)

    assert not ok
    assert 'in progress' in message
    initiate.assert_not_called()


# ── failed payout, and retry ────────────────────────────────────────────────


def test_a_failed_payout_records_the_reason(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value={'success': False, 'error': 'Insufficient float'},
    ):
        ok, message = prize_delivery.deliver(prize)

    prize.refresh_from_db()
    assert not ok
    assert prize.status == 'failed'
    assert prize.error_message == 'Insufficient float'
    assert message == 'Insufficient float'
    assert prize.delivered_at is None


def test_an_exception_mid_payout_is_recorded_not_swallowed(campaign, make_user):
    """A network error must leave the debt visible and retryable."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        side_effect=RuntimeError('connection reset'),
    ):
        ok, _message = prize_delivery.deliver(prize)

    prize.refresh_from_db()
    assert not ok
    assert prize.status == 'failed'
    assert 'connection reset' in prize.error_message


def test_a_retry_reuses_the_row_and_counts_the_attempt(campaign, make_user):
    """'Paid once, tried four times' must stay distinguishable from 'paid
    four times'."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value={'success': False, 'error': 'timeout'},
    ):
        prize_delivery.deliver(prize)
        prize.refresh_from_db()
        prize_delivery.retry(prize)
        prize.refresh_from_db()
        prize_delivery.retry(prize)

    prize.refresh_from_db()
    assert prize.attempt_count == 3
    assert WinnerGiftTransaction.objects.filter(campaign=campaign).count() == 1


def test_a_retry_after_a_failure_can_succeed(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value={'success': False, 'error': 'timeout'},
    ):
        prize_delivery.deliver(prize)

    prize.refresh_from_db()
    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value=b2c_accepted(),
    ):
        ok, _ = prize_delivery.retry(prize)

    prize.refresh_from_db()
    assert ok
    assert prize.status == 'processing'
    assert prize.attempt_count == 2


def test_retrying_a_delivered_prize_is_refused(campaign, make_user):
    """The whole point of retry: it must never double-pay."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'grand')
    prize.mark_success('TX')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment'
    ) as initiate:
        ok, message = prize_delivery.retry(prize)

    assert not ok
    assert 'already' in message
    initiate.assert_not_called()


def test_a_winner_without_telebirr_is_recorded_as_owed_not_dropped(campaign, make_user):
    """The gap this closed.

    A winner with no Telebirr account used to be filtered out before a prize
    row was written -- they had won 1,000 ETB and nothing anywhere recorded
    that anyone owed them it. Now the prize exists, marked skipped with a
    reason, so somebody can settle it another way.
    """
    winner = make_user()
    prize, _ = prize_delivery.award(campaign, winner, 'weekly')

    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=False), patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment'
    ) as initiate:
        ok, message = prize_delivery.deliver(prize)

    prize.refresh_from_db()
    assert not ok
    assert prize.status == 'skipped'
    assert 'Telebirr' in message
    assert prize.amount == Decimal('1000.00'), 'the debt is still recorded in full'
    assert not initiate.called


def test_an_undeliverable_prize_is_still_owed(campaign, make_user):
    """Skipped is not delivered. It must not read as settled business."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    prize.mark_skipped('no Telebirr account')
    prize.refresh_from_db()

    assert prize.is_owed
    assert prize.delivered_at is None
    assert prize in prize_delivery.skipped_deliveries()
    assert prize in prize_delivery.owed_deliveries()
    assert prize not in prize_delivery.successful_deliveries()


def test_an_undeliverable_prize_is_not_retried_forever(campaign, make_user):
    """No retry grows somebody a Telebirr account, so it is terminal --
    visible, but not hammered on every scheduled run."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    prize.mark_skipped('no Telebirr account')
    prize.refresh_from_db()

    ok, message = prize_delivery.retry(prize)

    assert not ok
    assert 'already' in message
    assert prize not in prize_delivery.deliverable()


def test_a_payout_without_a_phone_number_fails_rather_than_sending(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(phone=''), 'weekly')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment'
    ) as initiate:
        ok, _ = prize_delivery.deliver(prize)

    prize.refresh_from_db()
    assert not ok
    assert prize.status == 'failed'
    initiate.assert_not_called()


# ── the daily data prize ────────────────────────────────────────────────────


def test_the_daily_prize_provisions_data_not_cash(campaign, make_user, settings):
    """Synchronous, unlike a payout: the CRM says whether it provisioned."""
    settings.DATA_PRIZE_OFFERING_ID = 'OFFER-1GB'
    prize, _ = prize_delivery.award(campaign, make_user(), 'daily')

    with patch(
        'api.services.crm_service.CRMService.send_gift',
        return_value=(True, 'Gift sent', {'transaction_id': 'CRM-1'}),
    ) as send:
        ok, _ = prize_delivery.deliver(prize)

    prize.refresh_from_db()
    assert ok
    assert prize.status == 'success'
    assert prize.delivered_at is not None
    assert send.call_args.kwargs['offering_id'] == 'OFFER-1GB'


def test_the_data_prize_goes_to_the_winners_number(campaign, make_user, settings):
    settings.DATA_PRIZE_OFFERING_ID = 'OFFER-1GB'
    prize, _ = prize_delivery.award(campaign, make_user(phone='0912345678'), 'daily')

    with patch(
        'api.services.crm_service.CRMService.send_gift',
        return_value=(True, 'ok', {'transaction_id': 'CRM-2'}),
    ) as send:
        prize_delivery.deliver(prize)

    assert send.call_args.kwargs['service_number_b'] == prize.receiver_msisdn


def test_the_data_prize_is_provisioned_from_the_documented_number(settings):
    """The business requirement names 0911227833 as the provisioning number."""
    from api.services.crm_service import CRMService

    assert settings.DATA_PRIZE_PROVISIONING_NUMBER == '0911227833'

    settings.CRM_SERVICE_NUMBER_A = ''
    assert CRMService.get_service_number_a() == '0911227833'


def test_a_configured_service_number_still_wins(settings):
    """The fallback must not override an environment that set its own."""
    from api.services.crm_service import CRMService

    settings.CRM_SERVICE_NUMBER_A = '0900000000'
    assert CRMService.get_service_number_a() == '0900000000'


def test_a_failed_provisioning_is_recorded_and_retryable(campaign, make_user, settings):
    settings.DATA_PRIZE_OFFERING_ID = 'OFFER-1GB'
    prize, _ = prize_delivery.award(campaign, make_user(), 'daily')

    with patch(
        'api.services.crm_service.CRMService.send_gift',
        return_value=(False, 'Subscriber not found', {'transaction_id': 'CRM-3'}),
    ):
        ok, _ = prize_delivery.deliver(prize)

    prize.refresh_from_db()
    assert not ok
    assert prize.status == 'failed'
    assert prize.error_message == 'Subscriber not found'
    assert prize.attempt_count == 1


def test_data_provisioning_without_a_package_configured_fails_clearly(
    campaign, make_user, settings
):
    settings.DATA_PRIZE_OFFERING_ID = ''
    settings.CRM_OFFERING_ID = ''
    prize, _ = prize_delivery.award(campaign, make_user(), 'daily')

    ok, message = prize_delivery.deliver(prize)

    prize.refresh_from_db()
    assert not ok
    assert prize.status == 'failed'
    assert 'data package' in message


def test_the_data_prize_leaves_a_crm_ledger_row(campaign, make_user, settings):
    """Auditable in the same place as every other CRM gift."""
    from api.models.crm import CRMGiftTransaction

    settings.DATA_PRIZE_OFFERING_ID = 'OFFER-1GB'
    winner = make_user()
    prize, _ = prize_delivery.award(campaign, winner, 'daily')

    with patch(
        'api.services.crm_service.CRMService.send_gift',
        return_value=(True, 'ok', {'transaction_id': 'CRM-LEDGER'}),
    ):
        prize_delivery.deliver(prize)

    row = CRMGiftTransaction.objects.get(transaction_id='CRM-LEDGER')
    assert row.user == winner
    assert row.status == 'success'
    assert row.campaign_id == campaign.pk


# ── deadline tracking ───────────────────────────────────────────────────────


def test_a_prize_past_its_deadline_is_overdue(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    WinnerGiftTransaction.objects.filter(pk=prize.pk).update(
        deadline_at=timezone.now() - timedelta(days=1)
    )
    prize.refresh_from_db()

    assert prize.is_overdue
    assert prize in prize_delivery.overdue_deliveries()


def test_a_delivered_prize_is_never_overdue(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    WinnerGiftTransaction.objects.filter(pk=prize.pk).update(
        deadline_at=timezone.now() - timedelta(days=1)
    )
    prize.refresh_from_db()
    prize.mark_success('TX')
    prize.refresh_from_db()

    assert not prize.is_overdue
    assert prize not in prize_delivery.overdue_deliveries()


def test_a_prize_inside_its_deadline_is_not_overdue(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    WinnerGiftTransaction.objects.filter(pk=prize.pk).update(
        deadline_at=timezone.now() + timedelta(days=3)
    )
    prize.refresh_from_db()

    assert not prize.is_overdue


def test_the_data_prize_gets_an_internal_deadline(campaign, make_user):
    """The requirement sets no deadline for the data prize, only for the
    three cash tiers. One day is set as an internal target so a stuck data
    prize appears in the overdue list rather than being invisible -- nothing
    is promised to winners on the strength of it."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'daily')

    assert prize.deadline_at == campaign.entry_deadline + timedelta(days=1)
    assert not prize.is_overdue


def test_a_stuck_data_prize_becomes_visible(campaign, make_user):
    """Which is the whole reason it has a deadline at all."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'daily')
    WinnerGiftTransaction.objects.filter(pk=prize.pk).update(
        deadline_at=timezone.now() - timedelta(hours=1)
    )
    prize.refresh_from_db()

    assert prize.is_overdue
    assert prize in prize_delivery.overdue_deliveries()


# ── what an operator can see ────────────────────────────────────────────────


def test_the_operator_views_separate_pending_failed_and_delivered(campaign, make_user):
    pending, failed, delivered = make_user(), make_user(), make_user()

    prize_delivery.award(campaign, pending, 'weekly')

    failed_prize, _ = prize_delivery.award(campaign, failed, 'monthly')
    failed_prize.mark_failed('nope')

    delivered_prize, _ = prize_delivery.award(campaign, delivered, 'grand')
    delivered_prize.mark_success('TX')

    assert [p.winner for p in prize_delivery.pending_deliveries(campaign)] == [pending]
    assert [p.winner for p in prize_delivery.failed_deliveries(campaign)] == [failed]
    assert [p.winner for p in prize_delivery.successful_deliveries(campaign)] == [delivered]


def test_a_payout_in_flight_counts_as_pending(campaign, make_user):
    """Money owed is money owed until Telebirr confirms it moved."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')

    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value=b2c_accepted(),
    ):
        prize_delivery.deliver(prize)

    assert prize in prize_delivery.pending_deliveries(campaign)


# ── winners come from the backend, not a score the client sent ──────────────


def test_prizes_are_awarded_to_engine_selected_winners_only(campaign, make_user):
    """The requirement's last line: a high score is not a win.

    The list handed to award_all comes from CampaignScoringEngine, which
    applies the participation rules and the win restriction. A subscriber who
    never qualified never reaches this table.
    """
    from api.services.scoring.engine import CampaignScoringEngine

    class Entry:
        def __init__(self, user, score):
            self.user = user
            self.score = score

    slacker, regular = make_user('slacker'), make_user('regular')
    for day in range(5):
        reel = Reel.objects.create(user=regular, caption='e', is_campaign_post=True)
        score = PostScore.objects.create(
            reel=reel, campaign=campaign, user=regular, moderation_status='approved'
        )
        PostScore.objects.filter(pk=score.pk).update(
            created_at=campaign.start_date + timedelta(days=day, hours=9)
        )

    winners = CampaignScoringEngine(campaign).select_winners(
        [Entry(slacker, 999_999), Entry(regular, 1)]
    )
    prize_delivery.award_all(campaign, [w['user'] for w in winners], 'weekly')

    paid = list(
        WinnerGiftTransaction.objects.filter(campaign=campaign).values_list(
            'winner__username', flat=True
        )
    )
    assert paid == ['regular']
    assert 'slacker' not in paid
