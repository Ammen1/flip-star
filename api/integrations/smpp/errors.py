"""
Failures the SMPP transport can raise.

Split by what the caller should *do*, not by where they came from. A retry
that resends a message is safe after SmppSubmitRejected -- the gateway said no
-- and unsafe after SmppSubmitUncertain, where the message may already be on
its way to a handset.
"""

from api.integrations.smpp.status import status_label


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

    @property
    def code_label(self) -> str:
        """What dispatch records as error_code.

        The real SMPP status with its name -- ``SMPP_ESME_RINVMSGLEN (1)`` --
        when the gateway gave one, plain ``rejected`` when it could not be
        read. This is what turns a wall of identical ``code=1`` lines into
        something an operator can act on.
        """
        return status_label(self.status_code)


class SmppSubmitUncertain(SmppError):
    """submit_sm was written to the socket but no response came back.

    The ambiguous case, and the reason it has its own type. The gateway may
    have accepted the message and lost the response, or never seen it. A
    caller must NOT resend on this -- see api/services/sms/dispatch.py.
    """
