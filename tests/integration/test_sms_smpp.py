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
    def __init__(self, message_id=b'MSG-1', command='submit_sm_resp', sequence=1, status=None):
        self.message_id = message_id
        self.command = command
        self.sequence = sequence
        self.status = status


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
        self.sent_handler = None
        self.error_handler = None
        self.sequence = 0
        # A real gateway answers submit_sm with a submit_sm_resp carrying the
        # message id. Set False to simulate one that never replies.
        self.respond = True
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

    def set_message_sent_handler(self, handler):
        self.sent_handler = handler

    def set_error_pdu_handler(self, handler):
        self.error_handler = handler

    def send_message(self, **kwargs):
        if self.submit_error is not None:
            raise self.submit_error
        self.sent.append(kwargs)
        self.sequence += 1
        request = FakePdu(message_id=b'', command='submit_sm', sequence=self.sequence)
        if self.respond and self.sent_handler is not None:
            # The response arrives asynchronously in reality; firing it inline
            # is enough to exercise the correlation, and keeps tests fast.
            self.sent_handler(
                FakePdu(
                    message_id=f'MSG-{self.sequence}'.encode(),
                    command='submit_sm_resp',
                    sequence=self.sequence,
                )
            )
        return request

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
# The exact submit_sm parameters, and what gets logged about them
# ---------------------------------------------------------------------------


def test_a_submitted_part_carries_the_configured_ton_npi_and_encoding():
    """The addressing and encoding the gateway actually receives."""
    client = make_client()
    client.submit(destination='251912345678', text='hello')

    sent = FakeSmppClient.instances[0].sent[0]
    assert sent['data_coding'] == 0
    assert sent['esm_class'] == 0
    assert sent['registered_delivery'] == 1
    assert sent['source_addr_ton'] == 3
    assert sent['source_addr_npi'] == 0
    assert sent['dest_addr_ton'] == 1
    assert sent['dest_addr_npi'] == 1
    assert sent['service_type'] == ''
    client.close()


def test_source_addr_comes_from_settings_not_hardcoded():
    """9286 is what staging's environment sets, not something baked in."""
    client = make_client(TIMWE_SMPP_SOURCE_ADDR='FLIPSTAR')
    client.submit(destination='251912345678', text='hi')

    assert FakeSmppClient.instances[0].sent[0]['source_addr'] == 'FLIPSTAR'
    client.close()

    client = make_client(TIMWE_SMPP_SOURCE_ADDR='')
    client.submit(destination='251912345678', text='hi')

    assert FakeSmppClient.instances[-1].sent[0]['source_addr'] == ''
    client.close()


def test_transmission_is_logged_with_parameters_but_no_pii(caplog):
    """
    The log line an operator reads to answer "what exactly did we send?".

    It carries the parts, byte sizes, character count, data coding and
    addressing -- and never the recipient, the OTP, the password or the
    system id, which is what this test pins down.
    """
    client = make_client()
    with caplog.at_level('INFO'):
        client.submit(destination='251912345678', text='Your FlipStar code is 123456')

    transmitted = [r for r in caplog.records if r.getMessage().startswith('SMPP_SUBMIT_TRANSMITTED')]
    assert transmitted, 'no SMPP_SUBMIT_TRANSMITTED line'
    line = transmitted[0].getMessage()
    assert 'parts=1' in line
    assert 'chars=28' in line
    assert 'data_coding=SMPP_ENCODING_DEFAULT' in line
    assert 'esm_class=0' in line
    assert 'registered_delivery=1' in line
    assert 'source_ton=3' in line
    assert 'dest_ton=1' in line
    assert '251912345678' not in caplog.text
    assert '123456' not in caplog.text
    client.close()


def test_acceptance_is_logged_with_the_message_id(caplog):
    client = make_client()
    with caplog.at_level('INFO'):
        client.submit(destination='251912345678', text='hi')

    accepted = [r for r in caplog.records if r.getMessage().startswith('SMPP_SUBMIT_ACCEPTED')]
    assert accepted, 'no SMPP_SUBMIT_ACCEPTED line'
    assert 'message_id=MSG-1' in accepted[0].getMessage()
    client.close()


def test_a_nonzero_response_is_logged_as_the_real_status_name(caplog):
    """
    The heart of the staging mystery.

    Every failure there logged ``code=1`` -- SMPP command_status 1, which is
    ``SMPP_ESME_RINVMSGLEN`` ("Message Length is invalid"). The label is what
    an operator needs to act, and it must come along with the rejection.
    """
    client = make_client()
    client.connect()
    fake = FakeSmppClient.instances[0]
    fake.respond = False

    original = fake.send_message

    def send_then_reject(**kwargs):
        pdu = original(**kwargs)
        fake.error_handler(FakePdu(command='submit_sm_resp', sequence=pdu.sequence, status=1))
        return pdu

    fake.send_message = send_then_reject

    with caplog.at_level('INFO'):
        with pytest.raises(SmppSubmitRejected) as excinfo:
            client.submit(destination='251912345678', text='hi')

    assert excinfo.value.status_code == 1
    assert excinfo.value.code_label == 'SMPP_ESME_RINVMSGLEN (1)'
    assert any(
        'SMPP_SUBMIT_REJECTED' in r.getMessage() and 'SMPP_ESME_RINVMSGLEN (1)' in r.getMessage()
        for r in caplog.records
    ), 'rejection not logged with the named status'
    client.close()


def test_an_unknown_status_is_labeled_by_the_number_not_invented(caplog):
    """A status outside the table is shown verbatim rather than guessed at."""
    client = make_client()
    client.connect()
    fake = FakeSmppClient.instances[0]
    fake.respond = False

    original = fake.send_message

    def send_then_reject(**kwargs):
        pdu = original(**kwargs)
        fake.error_handler(FakePdu(command='submit_sm_resp', sequence=pdu.sequence, status=999))
        return pdu

    fake.send_message = send_then_reject

    with caplog.at_level('INFO'):
        with pytest.raises(SmppSubmitRejected) as excinfo:
            client.submit(destination='251912345678', text='hi')

    assert excinfo.value.code_label == 'status 999'
    assert any(
        'SMPP_SUBMIT_REJECTED' in r.getMessage() and 'status 999' in r.getMessage()
        for r in caplog.records
    )
    client.close()


def test_a_synchronous_rejection_carries_the_named_status(caplog):
    """A submit_sm_resp that errors while sending is the same definite 'no'."""
    client = make_client()
    client.connect()
    FakeSmppClient.instances[0].submit_error = smpplib.exceptions.PDUError('rejected', 1)

    with caplog.at_level('INFO'):
        with pytest.raises(SmppSubmitRejected) as excinfo:
            client.submit(destination='251912345678', text='hi')

    assert excinfo.value.code_label == 'SMPP_ESME_RINVMSGLEN (1)'
    assert any(
        'SMPP_SUBMIT_REJECTED' in r.getMessage() and 'SMPP_ESME_RINVMSGLEN (1)' in r.getMessage()
        for r in caplog.records
    )
    client.close()


def test_submit_logs_never_expose_credentials_otps_or_numbers(caplog):
    """
    The hard rule for this whole path: a log line may identify a submission,
    never a subscriber. The OTP, the phone number, the SMPP password and the
    system id must all stay out of what a log aggregator can index.
    """
    client = make_client()
    with caplog.at_level('DEBUG'):
        client.submit(destination='251912345678', text='Your OTP is 123456')

    assert 'test-password-not-real' not in caplog.text
    assert 'test-system' not in caplog.text
    assert '251912345678' not in caplog.text
    assert '123456' not in caplog.text
    client.close()


def test_an_unanswered_submission_is_logged_as_uncertain(monkeypatch, caplog):
    import api.integrations.smpp.client as client_module

    monkeypatch.setattr(client_module, 'SUBMIT_TIMEOUT_SECONDS', 0.2)

    client = make_client()
    client.connect()
    FakeSmppClient.instances[0].respond = False

    with caplog.at_level('INFO'):
        with pytest.raises(SmppSubmitUncertain):
            client.submit(destination='251912345678', text='hi')

    assert any(
        'SMPP_SUBMIT_UNANSWERED' in r.getMessage() for r in caplog.records
    )
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


# ---------------------------------------------------------------------------
# The submit_sm_resp correlation
# ---------------------------------------------------------------------------


def test_the_message_id_comes_from_the_response_not_the_request():
    """
    The bug this covers shipped and reached staging.

    smpplib's send_message() returns the REQUEST pdu, whose message_id is
    always empty -- the gateway's id arrives later on a submit_sm_resp. Reading
    it off the return value silently produced '' for every message, which meant
    no delivery receipt could ever be matched and nothing could reach
    'delivered'. Real submissions logged `message_id=` before this was fixed.
    """
    client = make_client()

    message_id = client.submit(destination='251912345678', text='hi')

    request = FakeSmppClient.instances[0].sent
    assert len(request) == 1
    # The id is the one the response carried, not the request's empty field.
    assert message_id == 'MSG-1'
    assert message_id != ''
    client.close()


def test_a_gateway_that_never_responds_is_uncertain(monkeypatch):
    """
    No submit_sm_resp is the ambiguous case, not a failure.

    The gateway may have taken the message and lost the reply, so this must
    not be reported as something a retry can safely repeat.
    """
    import api.integrations.smpp.client as client_module

    monkeypatch.setattr(client_module, 'SUBMIT_TIMEOUT_SECONDS', 0.2)

    client = make_client()
    client.connect()
    FakeSmppClient.instances[0].respond = False

    with pytest.raises(SmppSubmitUncertain):
        client.submit(destination='251912345678', text='hi')


def test_an_error_response_is_a_rejection():
    """A non-zero command_status is definite -- the gateway said no."""
    client = make_client()
    client.connect()
    fake = FakeSmppClient.instances[0]
    fake.respond = False

    original = fake.send_message

    def send_then_error(**kwargs):
        pdu = original(**kwargs)
        fake.error_handler(FakePdu(command='submit_sm_resp', sequence=pdu.sequence))
        return pdu

    fake.send_message = send_then_error

    with pytest.raises(SmppSubmitRejected):
        client.submit(destination='251912345678', text='hi')


def test_waiting_for_a_response_does_not_deadlock_the_reader():
    """
    The wait happens outside the connection lock, deliberately.

    The reader thread needs that lock for its keepalive; holding it while
    waiting for a response the reader itself must deliver would hang every
    send until the timeout.
    """
    client = make_client()
    client.connect()

    # The reader thread is running; a submit must still complete promptly.
    message_id = client.submit(destination='251912345678', text='hi')

    assert message_id == 'MSG-1'
    client.close()


def test_pending_responses_do_not_leak():
    """Each sequence is cleaned up, or a long-lived worker grows for ever."""
    client = make_client()

    for _ in range(5):
        client.submit(destination='251912345678', text='hi')

    assert client._pending == {}
    client.close()


# ---------------------------------------------------------------------------
# Spec-required: destination format, source address, transmitted= marker
# ---------------------------------------------------------------------------


def test_destination_wire_format_is_251_without_plus():
    """
    normalize_ethiopian_phone returns '251XXXXXXXXX' (no leading '+'), and
    that is exactly what hits the SMPP wire.  dest_ton=1 (International) /
    dest_npi=1 (ISDN) is the correct pairing for that format with TIMWE.
    If a '+' slipped in, the gateway would reject with RINVDSTADR.
    """
    client = make_client()
    client.submit(destination='251912345678', text='hi')

    sent = FakeSmppClient.instances[0].sent[0]
    assert sent['destination_addr'] == '251912345678', (
        'destination_addr must be 251... not +251... on the wire'
    )
    assert not sent['destination_addr'].startswith('+'), (
        'a leading + is not expected; dest_ton=1/npi=1 works with bare digits'
    )
    assert sent['dest_addr_ton'] == 1
    assert sent['dest_addr_npi'] == 1
    client.close()


def test_transmitted_log_includes_source_addr(caplog):
    """
    An operator who reads a submitted log must be able to see which
    source address (short code) was used, without having to inspect
    the Kubernetes secret or the Vault path.
    """
    client = make_client(TIMWE_SMPP_SOURCE_ADDR='9286')
    with caplog.at_level('INFO'):
        client.submit(destination='251912345678', text='Your code is 999888')

    transmitted = [
        r for r in caplog.records
        if r.getMessage().startswith('SMPP_SUBMIT_TRANSMITTED')
    ]
    assert transmitted, 'no SMPP_SUBMIT_TRANSMITTED log line'
    line = transmitted[0].getMessage()
    assert 'source_addr=9286' in line, (
        'source_addr must appear in SMPP_SUBMIT_TRANSMITTED so staging '
        'operators can confirm which short-code reached the gateway'
    )
    # The recipient and message text must never appear in the log.
    assert '251912345678' not in line
    assert '999888' not in line
    client.close()


def test_unanswered_submission_log_shows_transmitted_yes(monkeypatch, caplog):
    """
    When submit_sm is sent but no submit_sm_resp arrives, the uncertainty
    log must carry 'transmitted=yes' so an operator knows the PDU reached
    the socket layer, distinguishing it from a pre-send failure.
    """
    import api.integrations.smpp.client as client_module

    monkeypatch.setattr(client_module, 'SUBMIT_TIMEOUT_SECONDS', 0.2)

    client = make_client()
    client.connect()
    FakeSmppClient.instances[0].respond = False

    with caplog.at_level('WARNING'):
        with pytest.raises(SmppSubmitUncertain):
            client.submit(destination='251912345678', text='hi')

    unanswered = [
        r for r in caplog.records
        if 'SMPP_SUBMIT_UNANSWERED' in r.getMessage()
    ]
    assert unanswered, 'no SMPP_SUBMIT_UNANSWERED log line'
    assert 'transmitted=yes' in unanswered[0].getMessage(), (
        'unanswered log must carry transmitted=yes so it is distinct from '
        'a pre-send connection failure'
    )
    client.close()
