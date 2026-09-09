"""
The gateway contract.

One method, because that is all a caller needs: hand it a normalised number
and some text, get back what the gateway said. Everything else -- retries,
delivery state, idempotency -- belongs to the dispatch layer above, so that
adding a second transport never means reimplementing that logic.
"""

from abc import ABC, abstractmethod


class SubmitResult:
    """What a gateway reported about one submission."""

    def __init__(self, *, provider, message_id='', accepted=True):
        self.provider = provider
        #: The gateway's own id. Empty when the gateway does not issue one,
        #: which also means no delivery receipt can ever be correlated.
        self.message_id = message_id
        self.accepted = accepted

    def __repr__(self):
        return f'SubmitResult(provider={self.provider!r}, message_id={self.message_id!r})'


class SmsGateway(ABC):
    """A transport that can put an SMS on the network."""

    #: Short name, recorded on SmsMessage.provider.
    name = 'gateway'

    @abstractmethod
    def submit(self, *, destination: str, text: str) -> SubmitResult:
        """Send one message.

        Raises on failure rather than returning a flag, so that the ambiguous
        case -- submitted but unacknowledged -- can be a distinct type the
        caller is forced to handle. See api/integrations/smpp/errors.py.
        """

    def health(self) -> dict:
        """Operational state, free of credentials."""
        return {'provider': self.name}
