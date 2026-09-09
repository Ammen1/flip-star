"""
Queueing, delivering and tracking an SMS.

The transport is faked here -- what is under test is everything around it:
the idempotency key, the status transitions, what a retry is allowed to do,
and the rule that OneVAS is never reached.
"""

import pytest
from django.test import override_settings

from api.integrations.smpp.dlr import parse_receipt_text
from api.integrations.smpp.errors import (
    SmppConnectionError,
    SmppNotConfigured,
    SmppSubmitRejected,
    SmppSubmitUncertain,
)
from api.models.sms import SmsMessage, SmsStatus
from api.services.sms import UnknownSmsProvider, get_gateway
from api.services.sms.base import SmsGateway, SubmitResult
from api.services.sms.dispatch import (
    SmsNotQueued,
    deliver,
    queue_sms,
    record_delivery_receipt,
)

pytestmark = pytest.mark.django_db

MSISDN = '251912345678'


class RecordingGateway(SmsGateway):
    """A gateway that remembers, and can be told to fail."""

    name = 'timwe_smpp'

    def __init__(self, error=None):
        self.submissions = []
        self.error = error

    def submit(self, *, destination, text):
        if self.error is not None:
            raise self.error
        self.submissions.append((destination, text))
        return SubmitResult(provider=self.name, message_id=f'MID-{len(self.submissions)}')


@pytest.fixture
def gateway(monkeypatch):
    """Install a fake gateway in place of whatever SMS_PROVIDER names."""
    recorder = RecordingGateway()
    monkeypatch.setattr('api.services.sms.dispatch.get_gateway', lambda **kw: recorder)
    return recorder


@pytest.fixture(autouse=True)
def _immediate_commit(monkeypatch):
    """Run on_commit callbacks immediately.

    pytest wraps each test in a transaction that never commits, so the
    enqueue would otherwise never fire.
    """
    monkeypatch.setattr(
        'api.services.sms.dispatch.transaction.on_commit', lambda fn, *a, **kw: fn()
    )


@pytest.fixture(autouse=True)
def _no_real_task(monkeypatch):
    """Keep the Celery task from being dispatched to a broker."""
    calls = []
    monkeypatch.setattr('api.tasks.sms.deliver_sms.delay', lambda *a, **kw: calls.append((a, kw)))
    return calls


# ---------------------------------------------------------------------------
# Queueing
# ---------------------------------------------------------------------------


def test_queueing_records_the_message():
    message = queue_sms(phone_number=MSISDN, text='hello', purpose='otp')

    assert message.status == SmsStatus.QUEUED
    assert message.recipient == MSISDN
    assert message.purpose == 'otp'


def test_queueing_normalises_the_number():
    """One normalisation for the whole system -- 0912... is the same person."""
    message = queue_sms(phone_number='0912345678', text='hi')

    assert message.recipient == MSISDN


def test_an_unusable_number_is_refused():
    with pytest.raises(SmsNotQueued):
        queue_sms(phone_number='not-a-number', text='hi')

    assert SmsMessage.objects.count() == 0


def test_an_empty_message_is_refused():
    with pytest.raises(SmsNotQueued):
        queue_sms(phone_number=MSISDN, text='')


def test_the_same_idempotency_key_yields_one_message():
    """The guard against a duplicate OTP."""
    first = queue_sms(phone_number=MSISDN, text='code 1', idempotency_key='welcome:42')
    second = queue_sms(phone_number=MSISDN, text='code 2', idempotency_key='welcome:42')

    assert first.id == second.id
    assert SmsMessage.objects.count() == 1
    # The first message wins; the second is not a second code.
    assert SmsMessage.objects.get().body == 'code 1'


def test_queueing_does_not_touch_the_gateway(gateway):
    """The request path must never wait on SMPP."""
    queue_sms(phone_number=MSISDN, text='hi')

    assert gateway.submissions == []


def test_queueing_enqueues_a_delivery_task(_no_real_task):
    message = queue_sms(phone_number=MSISDN, text='hi')

    assert len(_no_real_task) == 1
    assert _no_real_task[0][0][0] == str(message.id)


# ---------------------------------------------------------------------------
# Delivery and status
# ---------------------------------------------------------------------------


def test_delivery_submits_and_records_the_message_id(gateway):
    message = queue_sms(phone_number=MSISDN, text='hi')

    result = deliver(str(message.id))

    assert gateway.submissions == [(MSISDN, 'hi')]
    assert result.status == SmsStatus.SUBMITTED
    assert result.provider_message_id == 'MID-1'
    assert result.submitted_at is not None


def test_submitted_is_not_delivered(gateway):
    """
    The distinction that matters.

    submit_sm succeeding means the gateway accepted the message, not that a
    handset received it.
    """
    message = queue_sms(phone_number=MSISDN, text='hi')

    result = deliver(str(message.id))

    assert result.status == SmsStatus.SUBMITTED
    assert result.status != SmsStatus.DELIVERED
    assert result.delivered_at is None


def test_a_rejected_submission_is_marked_rejected(monkeypatch):
    monkeypatch.setattr(
        'api.services.sms.dispatch.get_gateway',
        lambda **kw: RecordingGateway(error=SmppSubmitRejected('no', status_code=88)),
    )
    message = queue_sms(phone_number=MSISDN, text='hi')

    deliver(str(message.id))

    assert SmsMessage.objects.get(pk=message.pk).status == SmsStatus.REJECTED


def test_a_connection_failure_raises_so_celery_can_retry(monkeypatch):
    monkeypatch.setattr(
        'api.services.sms.dispatch.get_gateway',
        lambda **kw: RecordingGateway(error=SmppConnectionError('down')),
    )
    message = queue_sms(phone_number=MSISDN, text='hi')

    with pytest.raises(SmppConnectionError):
        deliver(str(message.id))

    # Nothing reached the gateway, so it stays resendable.
    assert SmsMessage.objects.get(pk=message.pk).submitted_at is None


def test_missing_configuration_fails_without_retrying(monkeypatch):
    monkeypatch.setattr(
        'api.services.sms.dispatch.get_gateway',
        lambda **kw: RecordingGateway(error=SmppNotConfigured('no host')),
    )
    message = queue_sms(phone_number=MSISDN, text='hi')

    deliver(str(message.id))  # must not raise -- retrying cannot fix config

    row = SmsMessage.objects.get(pk=message.pk)
    assert row.status == SmsStatus.FAILED
    assert row.error_code == 'not_configured'


# ---------------------------------------------------------------------------
# The ambiguous case
# ---------------------------------------------------------------------------


def test_an_uncertain_submission_is_never_resent(monkeypatch):
    """
    The rule this whole design exists for.

    A timeout after submit_sm may mean the gateway already holds the message.
    Resending would put two OTPs on one handset and the second would
    invalidate the first, so the row is closed instead.
    """
    monkeypatch.setattr(
        'api.services.sms.dispatch.get_gateway',
        lambda **kw: RecordingGateway(error=SmppSubmitUncertain('timed out')),
    )
    message = queue_sms(phone_number=MSISDN, text='hi')

    deliver(str(message.id))

    row = SmsMessage.objects.get(pk=message.pk)
    assert row.status == SmsStatus.FAILED
    assert row.error_code == 'uncertain'
    # submitted_at is set precisely so nothing tries again.
    assert row.submitted_at is not None


def test_a_message_already_submitted_is_not_submitted_again(gateway):
    """Worker restart, duplicate task delivery, acks_late requeue."""
    message = queue_sms(phone_number=MSISDN, text='hi')
    deliver(str(message.id))

    deliver(str(message.id))

    assert len(gateway.submissions) == 1


def test_a_terminal_message_is_not_resubmitted(gateway):
    message = queue_sms(phone_number=MSISDN, text='hi')
    SmsMessage.objects.filter(pk=message.pk).update(status=SmsStatus.DELIVERED)

    deliver(str(message.id))

    assert gateway.submissions == []


def test_delivering_an_unknown_id_is_not_an_error(gateway):
    import uuid

    assert deliver(str(uuid.uuid4())) is None


# ---------------------------------------------------------------------------
# Delivery receipts
# ---------------------------------------------------------------------------


def test_a_receipt_marks_the_message_delivered(gateway):
    message = queue_sms(phone_number=MSISDN, text='hi')
    deliver(str(message.id))

    record_delivery_receipt(parse_receipt_text('id:MID-1 stat:DELIVRD err:000'))

    row = SmsMessage.objects.get(pk=message.pk)
    assert row.status == SmsStatus.DELIVERED
    assert row.delivered_at is not None


def test_a_failure_receipt_marks_the_message_failed(gateway):
    message = queue_sms(phone_number=MSISDN, text='hi')
    deliver(str(message.id))

    record_delivery_receipt(parse_receipt_text('id:MID-1 stat:UNDELIV err:042'))

    row = SmsMessage.objects.get(pk=message.pk)
    assert row.status == SmsStatus.FAILED
    assert row.error_code == '042'


def test_a_receipt_for_an_unknown_id_is_dropped(gateway):
    """Another system may share the bind; that is not our message."""
    assert record_delivery_receipt(parse_receipt_text('id:SOMEONE-ELSE stat:DELIVRD')) is None


def test_a_malformed_receipt_is_dropped_safely():
    assert record_delivery_receipt(parse_receipt_text('nonsense')) is None


def test_an_unmapped_stat_records_the_raw_receipt(gateway):
    """Recorded, not guessed at."""
    message = queue_sms(phone_number=MSISDN, text='hi')
    deliver(str(message.id))

    record_delivery_receipt(parse_receipt_text('id:MID-1 stat:WEIRD'))

    row = SmsMessage.objects.get(pk=message.pk)
    assert row.status == SmsStatus.SUBMITTED  # unchanged
    assert 'WEIRD' in row.raw_dlr


# ---------------------------------------------------------------------------
# Provider selection -- OneVAS must be unreachable
# ---------------------------------------------------------------------------


@override_settings(SMS_PROVIDER='timwe_smpp')
def test_production_selects_the_smpp_gateway():
    from api.services.sms.timwe_smpp import TimweSmppGateway

    assert isinstance(get_gateway(), TimweSmppGateway)


@override_settings(SMS_PROVIDER='')
def test_an_unset_provider_fails_loudly():
    """Better a clear error than silently sending over a retired gateway."""
    with pytest.raises(UnknownSmsProvider):
        get_gateway()


@override_settings(SMS_PROVIDER='typo_smpp')
def test_an_unknown_provider_fails_loudly():
    with pytest.raises(UnknownSmsProvider):
        get_gateway()


@override_settings(SMS_PROVIDER='timwe_smpp')
def test_onevas_http_is_never_called(monkeypatch):
    """
    The regression this migration exists to prevent.

    Any HTTP POST from the SMS path would mean OneVAS is still in it.
    """
    posted = []
    monkeypatch.setattr('requests.post', lambda *a, **kw: posted.append((a, kw)))

    submitted = []
    monkeypatch.setattr(
        'api.services.sms.dispatch.get_gateway',
        lambda **kw: RecordingGateway(),
    )

    message = queue_sms(phone_number=MSISDN, text='hi')
    deliver(str(message.id))

    assert posted == [], 'the SMS path made an HTTP request -- OneVAS is still reachable'
    assert submitted == []


@override_settings(SMS_PROVIDER='timwe_smpp')
def test_the_subscription_sms_helper_does_not_use_onevas(monkeypatch):
    """The welcome SMS goes over SMPP like everything else."""
    posted = []
    monkeypatch.setattr('requests.post', lambda *a, **kw: posted.append((a, kw)))

    from api.services import sms_subscription

    class Tier:
        duration_type = 'daily'

    assert sms_subscription.send_subscription_sms(MSISDN, 'welcome', Tier()) is True
    assert posted == []
    assert SmsMessage.objects.filter(purpose='subscription_welcome').count() == 1
