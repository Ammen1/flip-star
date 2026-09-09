"""
Turning inbound delivery receipts into delivery state.

The receipt arrives on the SMPP reader thread, not in a task. That thread must
stay alive -- it is also what notices the connection dropping -- so nothing
here is allowed to raise into it, and the database work is deliberately small:
match on the gateway's message id, write the status.
"""

import logging

from api.integrations.smpp.dlr import receipt_from_pdu

logger = logging.getLogger(__name__)


def handle_deliver_sm(pdu):
    """Apply one ``deliver_sm`` to the message it refers to."""
    from django.db import close_old_connections

    from api.services.sms.dispatch import record_delivery_receipt

    receipt = receipt_from_pdu(pdu)
    try:
        # This runs on a thread Django did not create, so its connection is
        # not managed by the request cycle. Without this a long-lived reader
        # eventually works through a stale socket.
        close_old_connections()
        record_delivery_receipt(receipt)
    except Exception:
        logger.exception('SMS_DLR_RECORD_FAILED message_id=%s', receipt.message_id)
    finally:
        close_old_connections()


def attach_dlr_handler(client):
    """Point an SmppClient's receipt callback at this module."""
    client.set_dlr_handler(handle_deliver_sm)
