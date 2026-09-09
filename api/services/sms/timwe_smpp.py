"""The production gateway: TIMWE over SMPP."""

import logging

from api.integrations.smpp.client import get_client
from api.services.sms.base import SmsGateway, SubmitResult

logger = logging.getLogger(__name__)


class TimweSmppGateway(SmsGateway):
    """Submits over the process's single SMPP bind.

    Thin on purpose. The session, its reconnection and its keepalive live in
    api/integrations/smpp/client.py; this is the seam that lets the dispatch
    layer stay ignorant of which transport is underneath.
    """

    name = 'timwe_smpp'

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        return self._client if self._client is not None else get_client()

    def submit(self, *, destination, text):
        message_id = self.client.submit(destination=destination, text=text)
        return SubmitResult(provider=self.name, message_id=message_id)

    def health(self):
        return self.client.health()
