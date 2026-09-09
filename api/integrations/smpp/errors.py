"""
Failures the SMPP transport can raise.

Split by what the caller should *do*, not by where they came from. A retry
that resends a message is safe after SmppSubmitRejected -- the gateway said no
-- and unsafe after SmppSubmitUncertain, where the message may already be on
its way to a handset.
"""


class SmppError(Exception):
    """Base for every SMPP transport failure."""


class SmppNotConfigured(SmppError):
    """Host, port or credentials are missing. Not retryable."""


class SmppConnectionError(SmppError):
    """The TCP connection or the bind failed. Retryable: nothing was sent."""


class SmppSubmitRejected(SmppError):
    """The gateway answered submit_sm with an error.

    Definite: the message was not accepted, so re-sending cannot duplicate it.
    """

    def __init__(self, message, *, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class SmppSubmitUncertain(SmppError):
    """submit_sm was written to the socket but no response came back.

    The ambiguous case, and the reason it has its own type. The gateway may
    have accepted the message and lost the response, or never seen it. A
    caller must NOT resend on this -- see api/services/sms/dispatch.py.
    """
