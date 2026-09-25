"""
Getting a won prize to the winner, exactly once.

The shape of it
---------------
Awarding and delivering are two separate steps, deliberately:

    award(campaign, winner, tier)   ->  a prize row, idempotent
    deliver(prize)                  ->  one attempt at sending it

A prize is recorded the moment it is won, before anything external is
called. So if provisioning is down, or Telebirr times out, or the process
dies mid-request, the debt to the winner is already written down and can be
retried. The alternative -- call first, record what happened -- loses the
prize whenever the recording step is the thing that fails.

Paying once
-----------
``idempotency_key`` is ``campaign:tier:user``, and it is UNIQUE in the
database. Two callers racing to award the same prize both build the same key
and Postgres refuses the second INSERT. That is the guarantee; a check like
"does a row already exist?" is not, because both callers can read "no" in
the same millisecond.

Delivery is then guarded separately: ``deliver`` refuses a prize that is
already settled, and a retry reuses the same row and increments
``attempt_count`` rather than creating a second one. So a prize can be
attempted any number of times and paid at most once.

What "delivered" means
----------------------
For data, the CRM call is synchronous: it either provisioned or it did not,
and the result says which.

For cash it is not. ``initiate_b2c_payment`` starting successfully means
Telebirr *accepted* the instruction, not that the winner has the money --
the confirmation arrives later at telebirr_b2c_webhook. So a cash prize goes
to 'processing' here and only the webhook writes 'success'. Marking it
delivered on a successful initiation is precisely the bug this codebase's
B2C work was built to avoid, and with 300,000 ETB on the Grand Final it is
not a subtle one.

Why the integrations are imported here and not in the model
-----------------------------------------------------------
WinnerGiftTransaction stays a record of what happened. Giving a model a
method that posts SOAP to Ethio Telecom makes every test that touches a
prize row a test that needs the network stubbed, and makes the audit trail
depend on the integration being importable.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from api.models.gift import WinnerGiftPackage, WinnerGiftTransaction
from api.services.prize_structure import CRM, TELEBIRR, prize_for

logger = logging.getLogger(__name__)

#: How many times the scheduler will try a prize before leaving it alone.
#:
#: A delivery that has failed this often is failing for a reason retrying
#: will not fix -- a wrong number, an unprovisionable subscriber, a
#: misconfigured package -- and a scheduled job hammering it every hour
#: turns one problem into a log full of them. An operator can still retry
#: from the admin.
MAX_DELIVERY_ATTEMPTS = 5

#: A cash payout Telebirr accepted but never confirmed is *stuck*, not
#: delivered and not failed. Nothing in this codebase can resolve it --
#: there is no B2C query API -- so after this long it is surfaced for a
#: human rather than waited on indefinitely. Two withdrawals on this
#: deployment have sat in exactly this state since September.
STUCK_AFTER_HOURS = 24


def idempotency_key(campaign, winner, tier) -> str:
    """One prize per winner, per tier, per campaign.

    A campaign-less award (a manual one-off) keys on 'none', so two manual
    awards of the same tier to the same person still collide -- which is the
    safe direction to fail.
    """
    campaign_id = getattr(campaign, 'pk', None) or 'none'
    return f'{campaign_id}:{tier}:{winner.pk}'


def package_for(tier):
    """The WinnerGiftPackage row for a tier, reconciled with the structure.

    The row exists so the admin can see what each tier pays. It is not
    trusted: the documented amount and channel are written back over it, so
    an edited row cannot change what a winner is actually paid.
    """
    prize = prize_for(tier)
    package, _created = WinnerGiftPackage.objects.update_or_create(
        winner_type=tier,
        defaults={
            'gift_type': prize.gift_type,
            'payment_method': prize.channel,
            'amount': prize.amount,
            'is_active': True,
        },
    )
    return package


def award(campaign, winner, tier, *, closed_at=None, msisdn=None):
    """Record that `winner` has won `tier`, without delivering anything yet.

    Returns (prize, created). Calling it again for the same winner returns
    the existing row with created=False -- so a re-run of a winner-selection
    job does not create a second prize to pay.
    """
    prize_spec = prize_for(tier)
    key = idempotency_key(campaign, winner, tier)

    existing = WinnerGiftTransaction.objects.filter(idempotency_key=key).first()
    if existing is not None:
        return existing, False

    phone = msisdn or _winner_msisdn(winner)
    closed = closed_at or _campaign_close(campaign)

    try:
        with transaction.atomic():
            prize = WinnerGiftTransaction.objects.create(
                winner=winner,
                winner_type=tier,
                campaign=campaign,
                gift_package=package_for(tier),
                amount=prize_spec.amount,
                payment_method=prize_spec.channel,
                receiver_msisdn=phone or '',
                status='pending',
                idempotency_key=key,
                deadline_at=prize_spec.deadline_from(closed),
            )
    except IntegrityError:
        # Another caller won the race and inserted the same key. Theirs is
        # the prize; this one was never created.
        existing = WinnerGiftTransaction.objects.filter(idempotency_key=key).first()
        if existing is None:
            raise
        return existing, False

    # Told once, when the prize row is first created. Everything above is
    # what makes that safe: a re-run of winner selection returns early with
    # created=False and never reaches here, so a winner is not congratulated
    # twice for the same win.
    _notify_won(prize, prize_spec)

    return prize, True


def _notify_won(prize, prize_spec):
    """Tell the winner in-app that they won, before anything is delivered.

    Winners previously learned of a prize only when the money or the bundle
    arrived -- and for a cash prize that is up to twenty days later, or never
    if delivery fails.
    """
    from api.services.notifications import notify_system

    notify_system(
        prize.winner,
        'prize_won',
        f'You won {prize_spec.description}! '
        + (
            f'It will be delivered by {prize.deadline_at.date().isoformat()}.'
            if prize.deadline_at
            else 'It will be delivered shortly.'
        ),
    )


def award_all(campaign, winners, tier, *, closed_at=None):
    """Award a tier to a list of winners, capped at the documented count.

    `winners` arrives already selected and ordered by the scoring engine --
    which is what applies the participation rules and the win restriction.
    This does not re-rank them and does not decide who won; it takes as many
    as the tier pays and records a prize for each.
    """
    prize_spec = prize_for(tier)
    awarded = []

    for winner in list(winners)[: prize_spec.winner_count]:
        prize, _created = award(campaign, winner, tier, closed_at=closed_at)
        awarded.append(prize)

    return awarded


# ── delivery ────────────────────────────────────────────────────────────────


def deliver(prize, *, force=False, package=None):
    """One delivery attempt. Returns (ok, message).

    Refuses a prize that is already settled unless `force`, which exists for
    an operator who has confirmed out of band that a 'success' was wrong.
    Refusing is the default because the failure mode on the other side is
    paying somebody 300,000 ETB twice.

    `package` is an optional CRMGiftPackage for a data prize, so an operator
    awarding a specific bundle gets that bundle rather than the configured
    default. Ignored for cash.
    """
    if prize.is_settled and not force:
        return False, f'Prize is already {prize.status}; not delivering again'

    if prize.status == 'processing' and not force:
        # A Telebirr payout is in flight. Sending another now is how one
        # winner gets paid twice.
        return False, 'Delivery already in progress; awaiting confirmation'

    # F() rather than a read-then-write: two retries landing together must
    # count as two attempts, and `prize.attempt_count += 1` loses one of
    # them. See strategy 3 in api/services/concurrency.py.
    WinnerGiftTransaction.objects.filter(pk=prize.pk).update(
        attempt_count=F('attempt_count') + 1, status='processing'
    )
    prize.refresh_from_db()

    channel = prize.payment_method
    try:
        if channel == CRM:
            return _deliver_data(prize, package=package)
        if channel == TELEBIRR:
            return _deliver_cash(prize)
    except Exception as exc:  # noqa: BLE001 -- recorded, not swallowed
        logger.exception('PRIZE_DELIVERY_FAILED prize=%s tier=%s', prize.pk, prize.winner_type)
        prize.mark_failed(str(exc))
        return False, str(exc)

    prize.mark_failed(f'No delivery channel for {channel!r}')
    return False, f'No delivery channel for {channel!r}'


def retry(prize, *, package=None):
    """Re-attempt a failed delivery on the same row.

    The same row is the point: a retry must not create a second prize, and
    attempt_count has to keep counting so that "tried four times, paid once"
    stays visible.
    """
    if prize.is_settled:
        return False, f'Prize is already {prize.status}; nothing to retry'

    if prize.status == 'processing':
        return False, 'Delivery already in progress; awaiting confirmation'

    if prize.attempt_count >= MAX_DELIVERY_ATTEMPTS:
        return False, (
            f'Given up after {prize.attempt_count} attempts; '
            'needs an operator to look at why it keeps failing'
        )

    return deliver(prize, package=package)


def _deliver_data(prize, *, package=None):
    """Provision the data bundle through the CRM gift API.

    Synchronous: the CRM answers whether it provisioned, so this is one of
    the few deliveries that can be marked successful in the same request.
    """
    from django.conf import settings

    from api.models.crm import CRMGiftTransaction
    from api.services.crm_service import CRMService

    if not prize.receiver_msisdn:
        prize.mark_failed('No phone number on the winner')
        return False, 'No phone number on the winner'

    # An operator-chosen bundle wins over the configured default, so awarding
    # a specific package provisions that package.
    if package is not None:
        offering_id = package.offering_id
        charge_amount = float(package.charge_amount)
    else:
        offering_id = getattr(settings, 'DATA_PRIZE_OFFERING_ID', '') or getattr(
            settings, 'CRM_OFFERING_ID', ''
        )
        charge_amount = 0.0

    if not offering_id:
        prize.mark_failed('No data package configured (DATA_PRIZE_OFFERING_ID)')
        return False, 'No data package configured'

    success, message, response = CRMService.send_gift(
        service_number_b=prize.receiver_msisdn,
        offering_id=offering_id,
        charge_amount=charge_amount,
        access_user=getattr(settings, 'CRM_ACCESS_USER', ''),
        access_pwd=getattr(settings, 'CRM_ACCESS_PASSWORD', ''),
    )

    # The CRM's own ledger row, so a data prize is auditable in the same
    # place as every other CRM gift rather than only here.
    #
    # create, not update_or_create: these ids are unique per call now (see
    # CRMService.generate_transaction_id), and matching on one would let two
    # winners provisioned in the same moment share a row -- which is exactly
    # what the old second-resolution id caused.
    crm_transaction_id = (response or {}).get('transaction_id') or ''
    if crm_transaction_id:
        CRMGiftTransaction.objects.create(
            transaction_id=crm_transaction_id,
            user=prize.winner,
            phone_number=prize.receiver_msisdn,
            package=package,
            offering_id=offering_id,
            charge_amount=charge_amount,
            status='success' if success else 'failed',
            response_message=message or '',
            trigger_source=f'campaign_{prize.winner_type}',
            campaign_id=prize.campaign_id,
            completed_at=timezone.now(),
        )

    if success:
        prize.mark_success(crm_transaction_id)
        return True, message or 'Data prize provisioned'

    prize.mark_failed(message or 'CRM provisioning failed')
    return False, message or 'CRM provisioning failed'


def _deliver_cash(prize):
    """Instruct Telebirr to pay, and stop there.

    'processing' is the honest state on a successful initiation: Telebirr
    has accepted the instruction and the money has not moved yet.
    telebirr_b2c_webhook writes 'success' when it confirms.
    """
    from api.integrations.telebirr.direct_debit import telebirr_direct_debit_service

    if not prize.receiver_msisdn:
        prize.mark_failed('No phone number on the winner')
        return False, 'No phone number on the winner'

    # A cash prize for somebody with no Telebirr account has no route, and
    # retrying will not grow them one. Marked skipped rather than failed --
    # and rather than the winner being dropped before a prize row was ever
    # written, which is what used to happen: they won 1,000 ETB and nothing
    # anywhere recorded that anyone owed them it.
    if not _can_receive_telebirr(prize.winner):
        reason = 'Winner has no Telebirr account; needs paying another way'
        prize.mark_skipped(reason)
        logger.info(
            'PRIZE_SKIPPED prize=%s tier=%s reason=no_telebirr', prize.pk, prize.winner_type
        )
        return False, reason

    result = telebirr_direct_debit_service.initiate_b2c_payment(
        receiver_msisdn=prize.receiver_msisdn,
        amount=prize.amount,
        currency='ETB',
        reason_type='Winner prize payout',
        remark=f'{prize.winner_type.capitalize()} prize',
        reference_data={'winner_gift_transaction_id': str(prize.id)},
        initiator_type='org_operator',
    )

    if result.get('success'):
        prize.originator_conversation_id = result.get('originator_conversation_id') or ''
        prize.conversation_id = result.get('conversation_id') or ''
        prize.status = 'processing'
        prize.save(
            update_fields=[
                'originator_conversation_id',
                'conversation_id',
                'status',
                'updated_at',
            ]
        )
        logger.info(
            'PRIZE_PAYOUT_INITIATED prize=%s tier=%s attempt=%s',
            prize.pk,
            prize.winner_type,
            prize.attempt_count,
        )
        return True, 'Payout initiated; awaiting Telebirr confirmation'

    error = result.get('error', 'Unknown error')
    prize.mark_failed(error)
    return False, error


# ── what an operator needs to see ───────────────────────────────────────────


def pending_deliveries(campaign=None):
    """Won but not yet delivered -- the outstanding debt to winners."""
    prizes = WinnerGiftTransaction.objects.filter(status__in=('pending', 'processing'))
    return prizes.filter(campaign=campaign) if campaign else prizes


def failed_deliveries(campaign=None):
    prizes = WinnerGiftTransaction.objects.filter(status='failed')
    return prizes.filter(campaign=campaign) if campaign else prizes


def successful_deliveries(campaign=None):
    prizes = WinnerGiftTransaction.objects.filter(status='success')
    return prizes.filter(campaign=campaign) if campaign else prizes


def skipped_deliveries(campaign=None):
    """Won, and this system has no way to deliver it.

    Still owed. Listed separately from failed because no retry will help --
    somebody has to pay these another way -- and separately from delivered
    because they have not been.
    """
    prizes = WinnerGiftTransaction.objects.filter(status='skipped')
    return prizes.filter(campaign=campaign) if campaign else prizes


def owed_deliveries(campaign=None):
    """Every prize the winner does not yet have, whatever the reason.

    The number that answers "what do we still owe?" -- pending, in flight,
    failed and skipped together. A skipped prize belongs here: the winner is
    no less owed it because the payout rail could not reach them.
    """
    prizes = WinnerGiftTransaction.objects.exclude(status='success')
    return prizes.filter(campaign=campaign) if campaign else prizes


def stuck_deliveries(*, now=None, hours=None):
    """Payouts Telebirr accepted and never confirmed.

    'processing' means the instruction was sent and the webhook has not come
    back. That is normal for minutes and wrong after a day, and it is not a
    state this codebase can resolve on its own -- Telebirr offers no B2C
    query API, so the callback is the only confirmation there is. Surfacing
    them is the most that can be done in code; the rest is an operations
    question about why callbacks are not arriving.
    """
    moment = now or timezone.now()
    cutoff = moment - timedelta(hours=hours if hours is not None else STUCK_AFTER_HOURS)
    return WinnerGiftTransaction.objects.filter(status='processing', updated_at__lt=cutoff)


def deliverable(campaign=None):
    """Prizes a scheduled run should attempt.

    Pending ones, and failed ones still under the attempt cap. Never
    'processing' -- that one is in flight and sending it again is how a
    winner gets paid twice.
    """
    prizes = WinnerGiftTransaction.objects.filter(
        status__in=('pending', 'failed'), attempt_count__lt=MAX_DELIVERY_ATTEMPTS
    )
    return prizes.filter(campaign=campaign) if campaign else prizes


def abandoned_deliveries(campaign=None):
    """Failed as many times as the scheduler will try. Needs a person."""
    prizes = WinnerGiftTransaction.objects.filter(
        status='failed', attempt_count__gte=MAX_DELIVERY_ATTEMPTS
    )
    return prizes.filter(campaign=campaign) if campaign else prizes


def overdue_deliveries(campaign=None, *, now=None):
    """Past the promised deadline and still not delivered.

    This is the list that matters: the requirement promises 10 days (20 for
    the Grand Final), and a promise nobody can see being missed is one that
    gets missed.
    """
    moment = now or timezone.now()
    prizes = WinnerGiftTransaction.objects.filter(
        deadline_at__isnull=False, deadline_at__lt=moment
    ).exclude(status='success')
    return prizes.filter(campaign=campaign) if campaign else prizes


# ── helpers ─────────────────────────────────────────────────────────────────


def _winner_msisdn(winner):
    from api.views.crm import _normalize_local_phone

    phone = getattr(getattr(winner, 'profile', None), 'phone_number', None)
    return _normalize_local_phone(phone) if phone else ''


def _can_receive_telebirr(winner):
    """Whether a cash payout has anywhere to go.

    Absent a profile the answer is no, rather than an AttributeError in the
    middle of a payout run.
    """
    profile = getattr(winner, 'profile', None)
    if profile is None or not hasattr(profile, 'is_telebirr_user'):
        return False
    return bool(profile.is_telebirr_user())


def _campaign_close(campaign):
    """When the competition closed, which is what a deadline runs from."""
    if campaign is None:
        return timezone.now()
    return campaign.entry_deadline or campaign.start_date or timezone.now()
