"""
Delivery receipts.

A receipt arrives as an unsolicited ``deliver_sm`` on the same bind that
carried the message out. Its body is not structured data -- SMPP v3.4 appendix
B describes a plain-text form that gateways follow loosely:

    id:0123456789 sub:001 dlvrd:001 submit date:2609091200
    done date:2609091205 stat:DELIVRD err:000 text:...

So this is deliberately a tolerant scraper rather than a strict parser. A
receipt whose ``stat`` we cannot read is worth recording as unparsed; throwing
it away would lose the only evidence that the gateway said anything at all.
"""

import re

from api.models.sms import SmsStatus

#: Field extraction. Values run to the next key or the end, and `text:` is
#: last by convention -- it can contain spaces and is not read here.
_FIELD = re.compile(r'\b(id|sub|dlvrd|stat|err)\s*:\s*(\S+)', re.IGNORECASE)

#: The receipt states SMPP defines, mapped onto ours. Anything absent from
#: this table is left for the caller to treat as unknown rather than guessed
#: at -- inventing a status here would report deliveries that never happened.
STAT_TO_STATUS = {
    'DELIVRD': SmsStatus.DELIVERED,
    'EXPIRED': SmsStatus.EXPIRED,
    'DELETED': SmsStatus.FAILED,
    'UNDELIV': SmsStatus.FAILED,
    'ACCEPTD': SmsStatus.SUBMITTED,
    'UNKNOWN': SmsStatus.SUBMITTED,
    'REJECTD': SmsStatus.REJECTED,
}


class DeliveryReceipt:
    """One parsed receipt."""

    def __init__(self, *, message_id='', stat='', error_code='', raw=''):
        self.message_id = message_id
        self.stat = stat
        self.error_code = error_code
        self.raw = raw

    @property
    def status(self):
        """Our status, or None when the gateway's ``stat`` is unrecognised."""
        return STAT_TO_STATUS.get(self.stat.upper()) if self.stat else None

    def __repr__(self):
        return f'DeliveryReceipt(message_id={self.message_id!r}, stat={self.stat!r})'


def parse_receipt_text(text: str) -> DeliveryReceipt:
    """Read a receipt body. Never raises: an unreadable receipt is still data."""
    if not text:
        return DeliveryReceipt(raw='')

    fields = {key.lower(): value for key, value in _FIELD.findall(text)}
    return DeliveryReceipt(
        message_id=fields.get('id', ''),
        stat=fields.get('stat', ''),
        error_code=fields.get('err', ''),
        raw=text,
    )


def receipt_from_pdu(pdu) -> DeliveryReceipt:
    """Read a receipt out of a ``deliver_sm`` PDU.

    The text lives in ``short_message``; some gateways put it in
    ``message_payload`` instead when it would not fit, so both are tried.
    """
    body = getattr(pdu, 'short_message', None) or getattr(pdu, 'message_payload', None) or b''
    if isinstance(body, bytes):
        body = body.decode('utf-8', errors='replace')
    return parse_receipt_text(body)
