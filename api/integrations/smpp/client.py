"""
A long-lived SMPP session.

Why this is not a request-scoped object
---------------------------------------
SMPP is a persistent TCP protocol. A bind is an authenticated session that the
gateway expects to stay open, with ``enquire_link`` keepalives across idle
periods; operators commonly limit an account to a small number of concurrent
binds. Connecting per message would spend more time binding than sending and
would exhaust that allowance under any real load.

So exactly one process owns one connection. That process is the SMS worker
(``k8s/base/deployment-sms-worker.yaml``): a single replica, ``--pool=solo``,
consuming only the ``sms`` queue. The general workers -- two replicas at
concurrency four -- never import this module, because a task routed to the
``sms`` queue is never delivered to them.

Within that process the connection is still guarded by a lock. ``smpplib`` is
not thread-safe, and the reader thread below shares the socket with whichever
thread is submitting.

What this class does not do
---------------------------
It holds no business rules and knows nothing about subscriptions. It sends
text to a number and reports what the gateway said. Delivery state lives in
``SmsMessage``; the mapping from receipt to row is in ``dlr.py``.
"""

import logging
import threading
import time

import smpplib.client
import smpplib.consts
import smpplib.gsm
from django.conf import settings

from api.integrations.smpp.errors import (
    SmppConnectionError,
    SmppNotConfigured,
    SmppSubmitRejected,
    SmppSubmitUncertain,
)
from api.integrations.smpp.status import data_coding_label, status_label

logger = logging.getLogger(__name__)

#: How long to wait for a bind before giving up on this attempt.
CONNECT_TIMEOUT_SECONDS = 15

#: Longest a caller waits for submit_sm to be acknowledged. Past this the
#: outcome is unknown rather than failed -- see SmppSubmitUncertain.
SUBMIT_TIMEOUT_SECONDS = 30


class SmppSettings:
    """The configured link, with credentials kept out of anything printable."""

    def __init__(self):
        self.host = getattr(settings, 'TIMWE_SMPP_HOST', '') or ''
        self.port = int(getattr(settings, 'TIMWE_SMPP_PORT', 0) or 0)
        self.system_id = getattr(settings, 'TIMWE_SMPP_SYSTEM_ID', '') or ''
        self.password = getattr(settings, 'TIMWE_SMPP_PASSWORD', '') or ''
        self.system_type = getattr(settings, 'TIMWE_SMPP_SYSTEM_TYPE', '') or ''
        self.source_addr = getattr(settings, 'TIMWE_SMPP_SOURCE_ADDR', '') or ''
        self.source_ton = int(getattr(settings, 'TIMWE_SMPP_SOURCE_TON', 3) or 0)
        self.source_npi = int(getattr(settings, 'TIMWE_SMPP_SOURCE_NPI', 0) or 0)
        self.dest_ton = int(getattr(settings, 'TIMWE_SMPP_DEST_TON', 1) or 0)
        self.dest_npi = int(getattr(settings, 'TIMWE_SMPP_DEST_NPI', 1) or 0)
        self.service_type = getattr(settings, 'TIMWE_SMPP_SERVICE_TYPE', '') or ''
        self.registered_delivery = int(getattr(settings, 'TIMWE_SMPP_REGISTERED_DELIVERY', 1) or 0)
        self.enquire_link_seconds = int(
            getattr(settings, 'TIMWE_SMPP_ENQUIRE_LINK_SECONDS', 30) or 30
        )

    def validate(self):
        """Refuse an incomplete link loudly, at the point of use."""
        missing = [
            name
            for name, value in (
                ('TIMWE_SMPP_HOST', self.host),
                ('TIMWE_SMPP_PORT', self.port),
                ('TIMWE_SMPP_SYSTEM_ID', self.system_id),
                ('TIMWE_SMPP_PASSWORD', self.password),
            )
            if not value
        ]
        if missing:
            raise SmppNotConfigured(f'SMPP is not configured: {", ".join(missing)} unset.')

    def describe(self) -> str:
        """A safe one-liner for logs. The password is never part of it."""
        return (
            f'gateway={self.host}:{self.port} system_id=<redacted> '
            f'system_type={self.system_type or "<none>"} '
            f'source_addr={self.source_addr or "<none>"}'
        )


class SmppClient:
    """One bound SMPP session, reconnecting as needed.

    Not safe to instantiate more than once per process -- see the module
    docstring. ``get_client()`` returns the single instance.
    """

    def __init__(self, config=None, client_factory=None):
        self.config = config or SmppSettings()
        # Injected by the tests so they can drive a fake gateway without
        # patching smpplib's internals.
        self._client_factory = client_factory or smpplib.client.Client
        self._client = None
        self._lock = threading.RLock()
        self._reader = None
        self._stopping = threading.Event()
        self._dlr_handler = None

        # submit_sm responses, keyed by the request's sequence number.
        #
        # smpplib's send_message() returns the REQUEST pdu, not the response --
        # the submit_sm_resp carrying the gateway's message_id arrives later on
        # the reader thread. Without capturing it there is no id to store, and
        # so no way to match a delivery receipt back to a message.
        #
        # Guarded by its own lock, deliberately not self._lock: the reader
        # thread must be able to record a response while a submitting thread
        # is waiting, and sharing one lock would deadlock the pair.
        self._pending = {}
        self._pending_lock = threading.Lock()

        # Health, for the operational check. Deliberately plain attributes:
        # this is read by a status endpoint, not a metrics pipeline.
        self.bound = False
        self.connect_attempts = 0
        self.reconnect_count = 0
        self.last_bound_at = None
        self.last_enquire_link_at = None
        self.last_submit_at = None
        self.last_error = ''

    # -- lifecycle ---------------------------------------------------------

    def set_dlr_handler(self, handler):
        """Register the callback invoked for each delivery receipt."""
        self._dlr_handler = handler

    def connect(self):
        """Establish and bind the session. Idempotent while already bound."""
        with self._lock:
            if self.bound and self._client is not None:
                return

            self.config.validate()
            self._teardown_locked()
            self.connect_attempts += 1

            logger.info('SMPP_CONNECTING %s', self.config.describe())
            try:
                client = self._client_factory(
                    self.config.host, self.config.port, timeout=CONNECT_TIMEOUT_SECONDS
                )
                client.connect()
                logger.info('SMPP_CONNECTED %s', self.config.describe())
            except Exception as exc:
                self.last_error = f'connect failed: {exc}'
                logger.warning('SMPP_DISCONNECTED %s error=%s', self.config.describe(), exc)
                raise SmppConnectionError(f'Could not connect: {exc}') from exc

            try:
                client.bind_transceiver(
                    system_id=self.config.system_id,
                    password=self.config.password,
                    system_type=self.config.system_type,
                )
            except Exception as exc:
                self.last_error = f'bind failed: {exc}'
                # The message may quote the credentials back; it is logged as
                # a type and a safe description rather than verbatim.
                logger.error(
                    'SMPP_BIND_FAILED %s error_type=%s',
                    self.config.describe(),
                    type(exc).__name__,
                )
                try:
                    client.disconnect()
                except Exception:  # noqa: S110 - already failing; nothing to add
                    pass
                raise SmppConnectionError(f'Bind rejected: {type(exc).__name__}') from exc

            client.set_message_received_handler(self._on_pdu_received)
            client.set_message_sent_handler(self._on_message_sent)
            client.set_error_pdu_handler(self._on_error_pdu)
            self._client = client
            self.bound = True
            self.last_bound_at = time.time()
            self.last_error = ''
            logger.info('SMPP_BOUND %s', self.config.describe())

            self._start_reader_locked()

    def _start_reader_locked(self):
        """Read PDUs in the background so receipts arrive without polling.

        A delivery receipt is an unsolicited ``deliver_sm`` on the same bind.
        Nothing asks for it, so something has to be listening -- and the same
        loop is what notices the connection dying while idle.
        """
        if self._reader is not None and self._reader.is_alive():
            return
        self._stopping.clear()
        self._reader = threading.Thread(target=self._read_loop, name='smpp-reader', daemon=True)
        self._reader.start()

    def _read_loop(self):
        last_keepalive = time.time()
        while not self._stopping.is_set():
            client = self._client
            if client is None:
                return
            try:
                client.read_once()
            except Exception as exc:
                if self._stopping.is_set():
                    return
                self.last_error = f'read failed: {exc}'
                self.bound = False
                logger.warning('SMPP_DISCONNECTED reason=%s', type(exc).__name__)
                return

            now = time.time()
            if now - last_keepalive >= self.config.enquire_link_seconds:
                last_keepalive = now
                self._enquire_link()

    def _enquire_link(self):
        """Keepalive. A silent bind is closed by the gateway sooner or later."""
        with self._lock:
            client = self._client
            if client is None or not self.bound:
                return
            try:
                client.send_pdu(smpplib.smpp.make_pdu('enquire_link', client=client))
                self.last_enquire_link_at = time.time()
            except Exception as exc:
                self.bound = False
                self.last_error = f'enquire_link failed: {exc}'
                logger.warning('SMPP_DISCONNECTED reason=enquire_link_failed')

    def _waiter_for(self, sequence):
        """Get or create the slot for one sequence number.

        Get-or-create on both sides, because the response can arrive before
        the submitting thread has registered interest in it -- a fast gateway
        and a slow scheduler are enough.
        """
        with self._pending_lock:
            entry = self._pending.get(sequence)
            if entry is None:
                entry = {'event': threading.Event(), 'message_id': '', 'error': None}
                self._pending[sequence] = entry
            return entry

    def _on_message_sent(self, pdu):
        """Record a submit_sm_resp against the request that produced it."""
        sequence = getattr(pdu, 'sequence', None)
        if sequence is None:
            return
        message_id = getattr(pdu, 'message_id', '') or ''
        if isinstance(message_id, bytes):
            message_id = message_id.decode('ascii', 'replace')
        entry = self._waiter_for(sequence)
        entry['message_id'] = message_id
        entry['event'].set()

    def _on_error_pdu(self, pdu):
        """A non-zero command_status on a response we are waiting for."""
        sequence = getattr(pdu, 'sequence', None)
        if sequence is None:
            return
        entry = self._waiter_for(sequence)
        # Always truthy. Reaching this handler *is* the error; a status we
        # cannot read must not leave the entry looking like a success, which
        # is what storing a bare None did.
        status = getattr(pdu, 'status', None)
        entry['error'] = status if status is not None else 'unknown'
        entry['event'].set()

    def _on_pdu_received(self, pdu):
        """Route an inbound PDU. Only delivery receipts are acted on."""
        try:
            if getattr(pdu, 'command', '') != 'deliver_sm':
                return
            if self._dlr_handler is None:
                return
            self._dlr_handler(pdu)
        except Exception:
            # A malformed receipt must never take the reader thread down --
            # that would stop every subsequent receipt as well.
            logger.exception('SMS_DLR_HANDLER_FAILED')

    def ensure_bound(self):
        """Reconnect if the session has dropped."""
        with self._lock:
            if self.bound and self._client is not None:
                return
            if self.connect_attempts:
                self.reconnect_count += 1
                logger.info('SMPP_RECONNECTING attempt=%s', self.reconnect_count)
            self.connect()

    def close(self):
        """Unbind and close cleanly. Safe to call when never connected."""
        with self._lock:
            self._stopping.set()
            client = self._client
            if client is not None:
                try:
                    client.unbind()
                except Exception:  # noqa: S110 - shutting down regardless
                    pass
            self._teardown_locked()
            logger.info('SMPP_DISCONNECTED reason=shutdown')

    def _teardown_locked(self):
        client = self._client
        self._client = None
        self.bound = False
        if client is not None:
            try:
                client.disconnect()
            except Exception:  # noqa: S110 - best effort
                pass

    # -- sending -----------------------------------------------------------

    def submit(self, *, destination, text):
        """Submit one message. Returns the gateway's message id.

        Long messages are split into concatenated parts by ``smpplib.gsm``,
        which also chooses the encoding and builds the UDH. Every part goes on
        the same bind; the id of the first is returned, because that is the one
        a delivery receipt for the message quotes.

        The id comes from the ``submit_sm_resp``, which arrives asynchronously
        on the reader thread -- ``send_message`` hands back the request, not
        the response. So this sends, then waits for the reader to record the
        answer. Timing out is not the same as failing: the gateway may hold the
        message already, which is why it raises SmppSubmitUncertain.

        Everything here is logged with the *names* the gateway used
        (``SMPP_SUBMIT_TRANSMITTED`` / ``SMPP_SUBMIT_ACCEPTED`` /
        ``SMPP_SUBMIT_REJECTED``), and never with the recipient, the text,
        the OTP or any credential -- the message id and byte lengths identify
        the submission well enough to correlate with dispatch's own lines.
        """
        self.config.validate()
        self.ensure_bound()

        parts, encoding_flag, msg_type_flag = smpplib.gsm.make_parts(text)

        first_sequence = None
        with self._lock:
            client = self._client
            if client is None or not self.bound:
                raise SmppConnectionError('Not bound.')

            for index, part in enumerate(parts):
                try:
                    pdu = client.send_message(
                        source_addr_ton=self.config.source_ton,
                        source_addr_npi=self.config.source_npi,
                        source_addr=self.config.source_addr,
                        dest_addr_ton=self.config.dest_ton,
                        dest_addr_npi=self.config.dest_npi,
                        destination_addr=destination,
                        short_message=part,
                        data_coding=encoding_flag,
                        esm_class=msg_type_flag,
                        registered_delivery=self.config.registered_delivery,
                        service_type=self.config.service_type,
                    )
                except smpplib.exceptions.PDUError as exc:
                    # The gateway answered, and said no. Definite.
                    status = getattr(exc, 'args', [None, None])
                    code = status[1] if len(status) > 1 else None
                    self.last_error = f'submit rejected: {exc}'
                    logger.warning(
                        'SMPP_SUBMIT_REJECTED seq=%s status=%s part=%s/%s',
                        first_sequence if first_sequence is not None else 'pending',
                        status_label(code),
                        index + 1,
                        len(parts),
                    )
                    raise SmppSubmitRejected(str(exc), status_code=code) from exc
                except (OSError, smpplib.exceptions.ConnectionError) as exc:
                    # The socket broke. On the first part nothing was accepted;
                    # on a later one the message is already partly delivered,
                    # which resending does not fix.
                    self.bound = False
                    if index == 0:
                        raise SmppConnectionError(f'Submit failed: {exc}') from exc
                    raise SmppSubmitUncertain(
                        f'Connection lost after part {index + 1} of {len(parts)}: {exc}'
                    ) from exc
                except Exception as exc:
                    self.bound = False
                    raise SmppSubmitUncertain(
                        f'Submit outcome unknown (transmitted=unknown): {exc}'
                    ) from exc

                if index == 0:
                    first_sequence = getattr(pdu, 'sequence', None)

            self.last_submit_at = time.time()
            logger.info(
                'SMPP_SUBMIT_TRANSMITTED seq=%s parts=%s sizes=[%s] chars=%s '
                'data_coding=%s esm_class=%s registered_delivery=%s '
                'source_addr=%s source_ton=%s source_npi=%s dest_ton=%s dest_npi=%s '
                'service_type=%s',
                first_sequence if first_sequence is not None else 'pending',
                len(parts),
                ','.join(str(len(part)) for part in parts),
                len(text),
                data_coding_label(encoding_flag),
                msg_type_flag,
                self.config.registered_delivery,
                self.config.source_addr or '<none>',
                self.config.source_ton,
                self.config.source_npi,
                self.config.dest_ton,
                self.config.dest_npi,
                self.config.service_type or '<none>',
            )

        # Deliberately outside self._lock. The response is delivered by the
        # reader thread, which needs the lock for its keepalive -- waiting here
        # while holding it would deadlock the pair and time out every send.
        if first_sequence is None:
            return ''

        entry = self._waiter_for(first_sequence)
        try:
            if not entry['event'].wait(timeout=SUBMIT_TIMEOUT_SECONDS):
                logger.warning(
                    'SMPP_SUBMIT_UNANSWERED seq=%s waited=%ss transmitted=yes',
                    first_sequence,
                    SUBMIT_TIMEOUT_SECONDS,
                )
                raise SmppSubmitUncertain(
                    f'No submit_sm_resp within {SUBMIT_TIMEOUT_SECONDS}s (transmitted=yes); '
                    'the gateway may still have accepted the message.'
                )
            if entry['error'] is not None:
                error = entry['error']
                logger.warning(
                    'SMPP_SUBMIT_REJECTED seq=%s status=%s',
                    first_sequence,
                    status_label(error if isinstance(error, int) else error),
                )
                raise SmppSubmitRejected(
                    f'Gateway rejected submit_sm (status {error}).',
                    status_code=error,
                )
            logger.info(
                'SMPP_SUBMIT_ACCEPTED seq=%s message_id=%s',
                first_sequence,
                entry['message_id'],
            )
            return entry['message_id']
        finally:
            with self._pending_lock:
                self._pending.pop(first_sequence, None)

    # -- health ------------------------------------------------------------

    def health(self) -> dict:
        """Operational state. Never includes credentials."""
        return {
            'provider': 'timwe_smpp',
            'host': self.config.host,
            'port': self.config.port,
            'configured': bool(self.config.host and self.config.port and self.config.system_id),
            'bound': self.bound,
            'connect_attempts': self.connect_attempts,
            'reconnect_count': self.reconnect_count,
            'last_bound_at': self.last_bound_at,
            'last_enquire_link_at': self.last_enquire_link_at,
            'last_submit_at': self.last_submit_at,
            'last_error': self.last_error,
        }


_client = None
_client_lock = threading.Lock()


def get_client() -> SmppClient:
    """The process's single SMPP session, created on first use."""
    global _client
    with _client_lock:
        if _client is None:
            _client = SmppClient()
        return _client


def reset_client():
    """Drop the singleton. For tests and for worker shutdown."""
    global _client
    with _client_lock:
        if _client is not None:
            _client.close()
        _client = None
