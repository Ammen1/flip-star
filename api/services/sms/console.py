"""A gateway that logs instead of sending.

For local development, where there is no SMPP gateway to reach. Never
selected in production: SMS_PROVIDER is set explicitly there, and an
unrecognised value is refused rather than defaulted.
"""

import logging
import uuid

from api.services.sms.base import SmsGateway, SubmitResult

logger = logging.getLogger(__name__)


class ConsoleGateway(SmsGateway):
    name = 'console'

    def submit(self, *, destination, text):
        # The body is logged in full here deliberately: this gateway exists so
        # a developer can read the OTP they would otherwise have received.
        # That is also why it must never be selected in production.
        logger.info('SMS_CONSOLE to=%s body=%s', destination, text)
        return SubmitResult(provider=self.name, message_id=f'console-{uuid.uuid4().hex[:12]}')

    def health(self):
        return {'provider': self.name, 'configured': True, 'bound': True}
