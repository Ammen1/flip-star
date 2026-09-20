"""
The SkyConnect gateway.

Adapts `api/integrations/skyconnect/sms.py` to the SmsGateway contract, so a
telebirr subscription notice gets the same idempotency, retry and delivery
state as every other message without the dispatch layer knowing anything
about HTTP.
"""

import logging

from api.integrations.skyconnect.sms import (
    SkyConnectError,
    send_sms,
)
from api.integrations.skyconnect.sms import (
    health as provider_health,
)
from api.integrations.smpp.errors import SmppConnectionError, SmppSubmitRejected
from api.services.sms.base import SmsGateway, SubmitResult

logger = logging.getLogger(__name__)


class SkyConnectGateway(SmsGateway):
    """Telebirr subscription notices, over SkyConnect's HTTP API."""

    name = 'skyconnect'

    def submit(self, *, destination, text):
        """Send one message, translated into the dispatch layer's vocabulary.

        The existing error types are reused rather than new ones introduced:
        `deliver()` already knows that a connection error is worth retrying
        and a rejection is not, and that logic should not have to grow a
        branch per provider.
        """
        try:
            message_id = send_sms(destination=destination, text=text)
        except SkyConnectError as exc:
            if exc.retryable:
                raise SmppConnectionError(str(exc)) from exc
            raise SmppSubmitRejected(str(exc)) from exc

        return SubmitResult(provider=self.name, message_id=message_id)

    def health(self):
        return provider_health()
