"""
Getting prizes out without a person pressing a button, and noticing when
that is not working.

Three things are pinned here, each of which was missing:

**Nothing delivered prizes.** Winner selection recorded what was owed and
stopped, so every prize sat 'pending' until an operator opened the admin --
against a requirement promising delivery within 10 days, and 20 for the
Grand Final.

**The CRM transaction id collided.** It was ``strftime('%Y%m%d%H%M%S')``,
one second of resolution, against a UNIQUE column. Provisioning the twenty
Daily Sprint winners takes well under a second, so every winner after the
first collided: an IntegrityError on the old path, and a silent overwrite of
the previous winner's ledger row on the new one.

**Failures retried forever.** Nothing capped attempts, so a prize failing
for a reason retrying cannot fix -- a wrong number, an unprovisionable
subscriber -- would be attempted on every run indefinitely.

A payout in 'processing' is never re-sent by any of this. That state means
Telebirr has the instruction and has not confirmed, and re-sending is how
one winner gets paid twice.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from api.models.campaign import Campaign
from api.models.crm import CRMGiftTransaction
from api.models.gift import WinnerGiftTransaction
from api.services import prize_delivery
from api.services.crm_service import CRMService
from api.tasks.prizes import deliver_pending_prizes, report_prize_delivery_problems

pytestmark = pytest.mark.django_db

B2C_PAYMENT = (
    'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment'
)
CRM_SEND = 'api.services.crm_service.CRMService.send_gift'


@pytest.fixture
def make_user(django_user_model):
    counter = {'n': 0}

    def _make(name=None):
        counter['n'] += 1
        user = django_user_model.objects.create_user(
            username=name or f'sched_{counter["n"]}', password='x'
        )
        user.profile.phone_number = f'09117{counter["n"]:05d}'
        user.profile.save(update_fields=['phone_number'])
        return user

    return _make


@pytest.fixture(autouse=True)
def winners_can_receive_telebirr():
    """Every winner here can be paid, unless a test says otherwise.

    is_telebirr_user() reads a Telebirr SubscriptionPayment, which needs a
    whole subscription chain to build; these tests are about what the
    scheduler decides, not how that flag is derived.
    """
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True):
        yield


@pytest.fixture
def campaign(db):
    start = timezone.now() - timedelta(days=7)
    return Campaign.objects.create(
        title='Weekly Battle',
        campaign_type='weekly',
        status='active',
        start_date=start,
        entry_deadline=timezone.now(),
    )


def accepted(**overrides):
    result = {'success': True, 'originator_conversation_id': 'O', 'conversation_id': 'C'}
    result.update(overrides)
    return result


# ── the transaction id actually being unique ────────────────────────────────


def test_two_transaction_ids_generated_together_differ():
    """The collision, at its source.

    Twenty calls in a tight loop stood for twenty Daily Sprint winners; a
    second of resolution gave them all the same id.
    """
    ids = {CRMService.generate_transaction_id() for _ in range(20)}

    assert len(ids) == 20


def test_the_transaction_id_is_still_numeric():
    """The shape the CRM has always been sent does not change."""
    assert CRMService.generate_transaction_id().isdigit()


def test_the_transaction_id_fits_the_column():
    from api.models.crm import CRMGiftTransaction as Model

    limit = Model._meta.get_field('transaction_id').max_length
    assert len(CRMService.generate_transaction_id()) <= limit


def test_provisioning_several_winners_leaves_a_row_each(campaign, make_user, settings):
    """What the collision actually cost: nineteen missing ledger rows.

    Each CRM call returns its own id, so each winner gets their own row
    rather than overwriting the one before.
    """
    settings.DATA_PRIZE_OFFERING_ID = 'OFFER-1GB'
    winners = [make_user() for _ in range(5)]
    prizes = [prize_delivery.award(campaign, winner, 'daily')[0] for winner in winners]

    def send(**kwargs):
        return True, 'ok', {'transaction_id': CRMService.generate_transaction_id()}

    with patch(CRM_SEND, side_effect=send):
        for prize in prizes:
            prize_delivery.deliver(prize)

    assert CRMGiftTransaction.objects.count() == 5
    assert CRMGiftTransaction.objects.values('transaction_id').distinct().count() == 5
    # Every winner's own row, not five rows for whoever was provisioned last.
    assert set(CRMGiftTransaction.objects.values_list('user_id', flat=True)) == {
        winner.pk for winner in winners
    }


# ── the scheduled delivery run ──────────────────────────────────────────────


def test_the_scheduler_delivers_a_pending_prize(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    assert prize.status == 'pending'

    with patch(B2C_PAYMENT, return_value=accepted()) as initiate:
        deliver_pending_prizes()

    prize.refresh_from_db()
    assert initiate.call_count == 1
    assert prize.status == 'processing'
    assert prize.attempt_count == 1


def test_the_scheduler_never_resends_a_payout_in_flight(campaign, make_user):
    """The one thing it must never do."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')

    with patch(B2C_PAYMENT, return_value=accepted()):
        deliver_pending_prizes()

    with patch(B2C_PAYMENT, return_value=accepted()) as initiate:
        deliver_pending_prizes()

    prize.refresh_from_db()
    assert not initiate.called, 'a payout awaiting confirmation was sent again'
    assert prize.attempt_count == 1


def test_the_scheduler_never_resends_a_delivered_prize(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'grand')
    prize.mark_success('TX')

    with patch(B2C_PAYMENT, return_value=accepted()) as initiate:
        deliver_pending_prizes()

    assert not initiate.called


def test_the_scheduler_retries_a_failed_prize(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    prize.mark_failed('timeout')

    with patch(B2C_PAYMENT, return_value=accepted()) as initiate:
        deliver_pending_prizes()

    prize.refresh_from_db()
    assert initiate.called
    assert prize.status == 'processing'


def test_the_scheduler_gives_up_after_the_attempt_cap(campaign, make_user):
    """A prize failing for a reason a retry cannot fix must not be hammered
    on every run for ever."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    WinnerGiftTransaction.objects.filter(pk=prize.pk).update(
        status='failed', attempt_count=prize_delivery.MAX_DELIVERY_ATTEMPTS
    )

    with patch(B2C_PAYMENT, return_value=accepted()) as initiate:
        deliver_pending_prizes()

    assert not initiate.called


def test_a_manual_retry_also_respects_the_cap(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    WinnerGiftTransaction.objects.filter(pk=prize.pk).update(
        status='failed', attempt_count=prize_delivery.MAX_DELIVERY_ATTEMPTS
    )
    prize.refresh_from_db()

    ok, message = prize_delivery.retry(prize)

    assert not ok
    assert 'Given up' in message


def test_an_abandoned_prize_is_listed_for_a_person(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    WinnerGiftTransaction.objects.filter(pk=prize.pk).update(
        status='failed', attempt_count=prize_delivery.MAX_DELIVERY_ATTEMPTS
    )

    assert prize_delivery.abandoned_deliveries().filter(pk=prize.pk).exists()
    assert not prize_delivery.deliverable().filter(pk=prize.pk).exists()


def test_the_scheduler_delivers_data_prizes_too(campaign, make_user, settings):
    settings.DATA_PRIZE_OFFERING_ID = 'OFFER-1GB'
    prize, _ = prize_delivery.award(campaign, make_user(), 'daily')

    with patch(CRM_SEND, return_value=(True, 'ok', {'transaction_id': 'CRM-SCHED'})):
        deliver_pending_prizes()

    prize.refresh_from_db()
    assert prize.status == 'success'
    assert prize.delivered_at is not None


def test_one_failing_prize_does_not_stop_the_run(campaign, make_user):
    """A batch is a batch: one bad row must not strand the rest."""
    doomed, fine = make_user(), make_user()
    prize_delivery.award(campaign, doomed, 'weekly')
    prize_delivery.award(campaign, fine, 'monthly')

    calls = {'n': 0}

    def flaky(**kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            raise RuntimeError('connection reset')
        return accepted()

    with patch(B2C_PAYMENT, side_effect=flaky):
        deliver_pending_prizes()

    assert WinnerGiftTransaction.objects.filter(status='processing').count() == 1
    assert WinnerGiftTransaction.objects.filter(status='failed').count() == 1


def test_a_run_with_nothing_to_do_is_harmless():
    with patch(B2C_PAYMENT) as initiate:
        result = deliver_pending_prizes()

    assert not initiate.called
    assert 'Delivered 0' in result


# ── reporting what delivery cannot fix ──────────────────────────────────────


def test_an_unconfirmed_payout_is_reported_as_stuck(campaign, make_user):
    """Telebirr accepted it and never called back.

    No retry can resolve this -- there is no B2C query API to ask -- so it
    is surfaced rather than waited on. Two withdrawals on this deployment
    have sat in exactly this state.
    """
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    WinnerGiftTransaction.objects.filter(pk=prize.pk).update(
        status='processing', updated_at=timezone.now() - timedelta(days=2)
    )

    assert prize_delivery.stuck_deliveries().filter(pk=prize.pk).exists()


def test_a_payout_sent_moments_ago_is_not_stuck(campaign, make_user):
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')

    with patch(B2C_PAYMENT, return_value=accepted()):
        prize_delivery.deliver(prize)

    assert not prize_delivery.stuck_deliveries().filter(pk=prize.pk).exists()


def test_the_report_counts_each_kind_of_problem(campaign, make_user):
    overdue, stuck, abandoned = make_user(), make_user(), make_user()

    overdue_prize, _ = prize_delivery.award(campaign, overdue, 'weekly')
    WinnerGiftTransaction.objects.filter(pk=overdue_prize.pk).update(
        deadline_at=timezone.now() - timedelta(days=1)
    )

    stuck_prize, _ = prize_delivery.award(campaign, stuck, 'monthly')
    WinnerGiftTransaction.objects.filter(pk=stuck_prize.pk).update(
        status='processing', updated_at=timezone.now() - timedelta(days=3)
    )

    abandoned_prize, _ = prize_delivery.award(campaign, abandoned, 'grand')
    WinnerGiftTransaction.objects.filter(pk=abandoned_prize.pk).update(
        status='failed', attempt_count=prize_delivery.MAX_DELIVERY_ATTEMPTS
    )

    summary = report_prize_delivery_problems()

    assert 'overdue' in summary
    assert 'unconfirmed' in summary
    assert 'abandoned' in summary


def test_the_report_changes_nothing(campaign, make_user):
    """It reports; it does not retry, resend or settle anything."""
    prize, _ = prize_delivery.award(campaign, make_user(), 'weekly')
    WinnerGiftTransaction.objects.filter(pk=prize.pk).update(
        status='processing', updated_at=timezone.now() - timedelta(days=2)
    )
    prize.refresh_from_db()
    before = (prize.status, prize.attempt_count, prize.delivered_at)

    with patch(B2C_PAYMENT) as initiate:
        report_prize_delivery_problems()

    prize.refresh_from_db()
    assert (prize.status, prize.attempt_count, prize.delivered_at) == before
    assert not initiate.called


# ── the data rail records a prize like the cash rail does ───────────────────


def test_a_data_prize_awarded_by_an_operator_is_a_tracked_prize(campaign, make_user, settings):
    """The gap this closed.

    award_campaign_winners wrote a CRMGiftTransaction and nothing else, so a
    Daily Sprint prize had no prize row: no idempotency key, no attempt
    count, no campaign link, and it never appeared in the prize views.
    """
    from api.models.crm import CRMGiftPackage

    settings.CRM_ACCESS_USER = 'u'
    package = CRMGiftPackage.objects.create(
        name='1GB Data', offering_id='OFF-1GB', charge_amount=Decimal('0'), is_active=True
    )
    winner = make_user()

    prize, _ = prize_delivery.award(campaign, winner, 'daily')
    with patch(CRM_SEND, return_value=(True, 'ok', {'transaction_id': 'CRM-OP'})):
        prize_delivery.deliver(prize, package=package)

    prize.refresh_from_db()
    assert prize.idempotency_key is not None
    assert prize.campaign == campaign
    assert prize.attempt_count == 1
    assert prize.status == 'success'
    assert CRMGiftTransaction.objects.get(transaction_id='CRM-OP').package == package
    # And it shows up where an operator looks for delivered prizes.
    assert prize in prize_delivery.successful_deliveries(campaign)


def test_an_operator_chosen_package_wins_over_the_default(campaign, make_user, settings):
    from api.models.crm import CRMGiftPackage

    settings.DATA_PRIZE_OFFERING_ID = 'DEFAULT-OFFER'
    package = CRMGiftPackage.objects.create(
        name='5GB Data', offering_id='OFF-5GB', charge_amount=Decimal('0'), is_active=True
    )
    prize, _ = prize_delivery.award(campaign, make_user(), 'daily')

    with patch(CRM_SEND, return_value=(True, 'ok', {'transaction_id': 'CRM-PKG'})) as send:
        prize_delivery.deliver(prize, package=package)

    assert send.call_args.kwargs['offering_id'] == 'OFF-5GB'


def test_a_data_prize_cannot_be_provisioned_twice(campaign, make_user, settings):
    settings.DATA_PRIZE_OFFERING_ID = 'OFFER-1GB'
    winner = make_user()

    prize, _ = prize_delivery.award(campaign, winner, 'daily')
    with patch(CRM_SEND, return_value=(True, 'ok', {'transaction_id': 'CRM-ONCE'})) as send:
        prize_delivery.deliver(prize)
        prize.refresh_from_db()

        again, created = prize_delivery.award(campaign, winner, 'daily')
        ok, message = prize_delivery.deliver(again)

    assert not created
    assert not ok
    assert 'already' in message
    assert send.call_count == 1
