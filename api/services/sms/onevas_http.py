"""
The retired gateway: OneVAS over HTTP.

Kept for reference and for a deliberate, explicit rollback -- not as a
fallback. Nothing selects it automatically: SMS_PROVIDER must name it, and
choosing it logs a warning on every submission. There is no code path that
reaches this class because TIMWE SMPP failed; that is the whole point of the
migration, and a silent failover would send subscribers messages over a
gateway that is being decommissioned while hiding the SMPP outage.

The HTTP call itself is the one that lived on OnevasWebhookView.send_sms,
moved here unchanged so there is a single copy of the payload shape.
"""

import logging

import requests
from django.conf import settings

from api.services.sms.base import SmsGateway, SubmitResult

logger = logging.getLogger(__name__)


class OnevasHttpGateway(SmsGateway):
    name = 'onevas_http'

    def __init__(self, tier_type=None):
        # OneVAS keys messages by product; the tier decides which application
        # key and product number the payload carries.
        self.tier_type = tier_type

    def _product_config(self):
        from api.services.superapp_sms_service import onevas_product_config

        return onevas_product_config(self.tier_type)

    def submit(self, *, destination, text):
        logger.warning(
            'SMS_LEGACY_GATEWAY_USED provider=onevas_http -- OneVAS is retired; '
            'production should run SMS_PROVIDER=timwe_smpp.'
        )
        product = self._product_config()
        payload = {
            'phone_number': destination,
            'application_key': product.get('application_key', ''),
            'text': text,
            'product_number': product.get('product_id', ''),
        }
        response = requests.post(settings.ONEVAS_SMS_URL, json=payload, timeout=10)
        if response.status_code != 200:
            from api.integrations.smpp.errors import SmppSubmitRejected

            raise SmppSubmitRejected(
                f'OneVAS refused the message: HTTP {response.status_code}',
                status_code=response.status_code,
            )
        # OneVAS returns no message id, so nothing can ever be correlated to a
        # delivery receipt -- one of the reasons it is being replaced.
        return SubmitResult(provider=self.name, message_id='')

    def health(self):
        return {'provider': self.name, 'configured': bool(settings.ONEVAS_SMS_URL)}
