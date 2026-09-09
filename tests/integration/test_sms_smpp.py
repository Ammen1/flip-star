"""
The SMPP transport, against a fake gateway.

Nothing here touches the real TIMWE link. The fake stands in for
``smpplib.client.Client`` and is injected through ``SmppClient``'s
``client_factory``, which exists for exactly this -- so the tests drive bind
failures, dropped sockets and rejected submissions on demand rather than
waiting for a telecom to produce them.

What the fake does not prove: that TIMWE accepts our bind or our addressing.
Only a real submission can show that, and it has not been run -- see the
report accompanying this work.
"""

import pytest
import smpplib.exceptions
from django.test import override_settings

from api.integrations.smpp.client import SmppClient, SmppSettings
from api.integrations.smpp.dlr import parse_receipt_text
from api.integrations.smpp.errors import (
    SmppConnectionError,
    SmppNotConfigured,
    SmppSubmitRejected,
    SmppSubmitUncertain,
)
from api.models.sms import SmsStatus

SMPP_SETTINGS = {
    'TIMWE_SMPP_HOST': '10.0.0.1',
    'TIMWE_SMPP_PORT': 6986,
    'TIMWE_SMPP_SYSTEM_ID': 'test-system',
    'TIMWE_SMPP_PASSWORD': 'test-password-not-real',
    'TIMWE_SMPP_SOURCE_ADDR': '9286',
    'SMS_PROVIDER': 'timwe_smpp',
}


class FakePdu:
    def __init__(self, message_id=b'MSG-1', command='submit_sm_resp'):
        self.message_id = message_id
        self.command = command


class FakeSmppClient:
    """A stand-in for smpplib's client, driven by flags the tests set."""

    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.connected = False
        self.bound = False
        self.disconnected = False
        self.unbound = False
        self.sent = []
        self.pdus_sent = []
        self.handler = None
        # Failure switches.
        self.fail_connect = False
        self.fail_bind = False
        self.submit_error = None
        FakeSmppClient.instances.append(self)

    def connect(self):
        if self.fail_connect:
            raise OSError('connection refused')
        self.connected = True

    def bind_transceiver(self, **kwargs):
        if self.fail_bind:
            raise smpplib.exceptions.PDUError('Bind failed', 13)
        self.bound = True
        self.bind_kwargs = kwargs

    def set_message_received_handler(self, handler):
        self.handler = handler

    def send_message(self, **kwargs):
        if self.submit_error is not None:
            raise self.submit_error
        self.sent.append(kwargs)
        return FakePdu(message_id=f'MSG-{len(self.sent)}'.encode())

    def send_pdu(self, pdu):
        self.pdus_sent.append(pdu)

    def read_once(self):
        # Block-free no-op; the reader thread loops on this.
        import time

        time.sleep(0.01)

    def unbind(self):
        self.unbound = True

    def disconnect(self):
        self.disconnected = True
        self.connected = False


@pytest.fixture(autouse=True)
def _reset_fakes():
    FakeSmppClient.instances = []
    yield
    FakeSmppClient.instances = []


def make_client(**overrides):
    with override_settings(**{**SMPP_SETTINGS, **overrides}):
        client = SmppClient(config=SmppSettings(), client_factory=FakeSmppClient)
    return client


# ---------------------------------------------------------------------------
# Connection and bind
# ---------------------------------------------------------------------------


def test_it_connects_and_binds():
    client = make_client()
    client.connect()

    assert client.bound is True
    assert FakeSmppClient.instances[0].connected
    assert FakeSmppClient.instances[0].bound
    client.close()


def test_the_bind_carries_the_configured_system_id():
    client = make_client()
    client.connect()

    kwargs = FakeSmppClient.instances[0].bind_kwargs
    assert kwargs['system_id'] == 'test-system'
    client.close()


def test_a_failed_tcp_connection_is_a_connection_error():
    client = make_client()

    def failing(host, port, timeout=None):
        fake = FakeSmppClient(host, port, timeout)
        fake.fail_connect = True
        return fake

    client._client_factory = failing

    with pytest.raises(SmppConnectionError):
        client.connect()
    assert client.bound is False


def test_a_rejected_bind_is_a_connection_error():
    client = make_client()

    def failing(host, port, timeout=None):
        fake = FakeSmppClient(host, port, timeout)
        fake.fail_bind = True
        return fake

    client._client_factory = failing

    with pytest.raises(SmppConnectionError):
        client.connect()
    assert client.bound is False


def test_missing_configuration_is_refused_before_connecting():
    client = make_client(TIMWE_SMPP_HOST='')

    with pytest.raises(SmppNotConfigured):
        client.connect()
    assert FakeSmppClient.instances == []


def test_connect_is_idempotent_while_bound():
    client = make_client()
    client.connect()
    client.connect()

    assert len(FakeSmppClient.instances) == 1
    client.close()


def test_a_dropped_session_reconnects():
    client = make_client()
    client.connect()
    client.bound = False  # as the reader thread would mark it

    client.ensure_bound()

    assert client.bound is True
    assert client.reconnect_count == 1
    assert len(FakeSmppClient.instances) == 2
    client.close()


def test_close_unbinds_and_disconnects():
    client = make_client()
    client.connect()
    fake = FakeSmppClient.instances[0]

    client.close()

    assert fake.unbound is True
    assert fake.disconnected is True
    assert client.bound is False


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------


def test_submit_returns_the_gateway_message_id():
    client = make_client()

    message_id = client.submit(destination='251912345678', text='hello')

    assert message_id == 'MSG-1'
    client.close()


def test_submit_uses_the_configured_addressing():
    client = make_client()
    client.submit(destination='251912345678', text='hello')

    sent = FakeSmppClient.instances[0].sent[0]
    assert sent['destination_addr'] == '251912345678'
    assert sent['source_addr'] == '9286'
    assert sent['registered_delivery'] == 1
    client.close()


def test_submit_binds_on_demand():
    """A message arriving before the worker has bound must still go."""
    client = make_client()
    assert client.bound is False

    client.submit(destination='251912345678', text='hi')

    assert client.bound is True
    client.close()


def test_a_rejected_submission_is_definite():
    """The gateway answered 'no', so a resend cannot duplicate anything."""
    client = make_client()
    client.connect()
    FakeSmppClient.instances[0].submit_error = smpplib.exceptions.PDUError('rejected', 88)

    with pytest.raises(SmppSubmitRejected):
        client.submit(destination='251912345678', text='hi')
    client.close()


def test_a_socket_failure_on_the_first_part_is_retryable():
    """Nothing was accepted, so repeating is safe."""
    client = make_client()
    client.connect()
    FakeSmppClient.instances[0].submit_error = OSError('broken pipe')

    with pytest.raises(SmppConnectionError):
        client.submit(destination='251912345678', text='hi')


def test_an_unexpected_failure_is_uncertain_not_failed():
    """
    The ambiguous case, kept distinct on purpose.

    An unknown error after writing to the socket may mean the gateway has the
    message. Reporting that as a plain failure would invite a resend and a
    duplicate OTP.
    """
    client = make_client()
    client.connect()
    FakeSmppClient.instances[0].submit_error = RuntimeError('who knows')

    with pytest.raises(SmppSubmitUncertain):
        client.submit(destination='251912345678', text='hi')


def test_a_long_message_is_split_into_parts():
    """OTP text must never be truncated to fit one SMS."""
    client = make_client()
    long_text = 'A' * 400

    client.submit(destination='251912345678', text=long_text)

    sent = FakeSmppClient.instances[0].sent
    assert len(sent) > 1, 'expected concatenated parts'
    client.close()


def test_a_long_message_returns_the_first_part_id():
    """The receipt for a concatenated message quotes the first part."""
    client = make_client()

    message_id = client.submit(destination='251912345678', text='B' * 400)

    assert message_id == 'MSG-1'
    client.close()


# ---------------------------------------------------------------------------
# Credentials must not leak
# ---------------------------------------------------------------------------


def test_the_description_redacts_the_system_id():
    with override_settings(**SMPP_SETTINGS):
        description = SmppSettings().describe()

    assert 'test-system' not in description
    assert '<redacted>' in description
    assert 'test-password-not-real' not in description


def test_health_never_exposes_credentials():
    client = make_client()
    health = client.health()

    assert 'test-password-not-real' not in str(health)
    assert 'password' not in health


def test_a_bind_failure_does_not_log_the_password(caplog):
    client = make_client()

    def failing(host, port, timeout=None):
        fake = FakeSmppClient(host, port, timeout)
        fake.fail_bind = True
        return fake

    client._client_factory = failing

    with caplog.at_level('DEBUG'), pytest.raises(SmppConnectionError):
        client.connect()

    assert 'test-password-not-real' not in caplog.text
    assert 'test-system' not in caplog.text


# ---------------------------------------------------------------------------
# Delivery receipts
# ---------------------------------------------------------------------------


def test_a_delivered_receipt_parses():
    receipt = parse_receipt_text(
        'id:MSG-1 sub:001 dlvrd:001 submit date:2609091200 '
        'done date:2609091205 stat:DELIVRD err:000 text:hello'
    )

    assert receipt.message_id == 'MSG-1'
    assert receipt.stat == 'DELIVRD'
    assert receipt.status == SmsStatus.DELIVERED


def test_an_undelivered_receipt_maps_to_failed():
    receipt = parse_receipt_text('id:MSG-2 stat:UNDELIV err:042')

    assert receipt.status == SmsStatus.FAILED
    assert receipt.error_code == '042'


def test_an_expired_receipt_maps_to_expired():
    assert parse_receipt_text('id:M stat:EXPIRED').status == SmsStatus.EXPIRED


def test_a_malformed_receipt_does_not_raise():
    receipt = parse_receipt_text('total gibberish, no fields at all')

    assert receipt.message_id == ''
    assert receipt.status is None


def test_an_empty_receipt_does_not_raise():
    assert parse_receipt_text('').message_id == ''


def test_an_unrecognised_stat_yields_no_status():
    """Better to record it unmapped than to invent a delivery."""
    receipt = parse_receipt_text('id:M stat:WEIRDNESS')

    assert receipt.stat == 'WEIRDNESS'
    assert receipt.status is None
