"""
TIMWE Master Aggregator syncOrderRelation handling (inbound).

Direction reverses here: the MA is the client and FlipStar is the server. When
a subscription relationship is created, removed or changed on the MA -- by SMS
keyword, or on the web once that flow is published -- it POSTs a SOAP
``syncOrderRelation`` request to a URI we define, and expects a response
within 30 seconds (guide pp.10-17).

One endpoint covers every case. Unlike the OneVAS webhooks, which used a
separate URL per event, the operation is carried in ``updateType``:

    1  Add     -- subscribe
    2  Delete  -- unsubscribe
    3  Update  -- change an existing relationship

Parsing notes
-------------
Element lookups match on local name only. The MA's examples bind the payload
to ``ns1`` but nothing in the guide fixes that prefix, and the nested
``userID``/``extensionInfo`` children are unprefixed in the same examples --
so qualified-name matching would break on a conformant request.

DOCTYPE is rejected outright. This endpoint is unauthenticated by design (the
guide states the request has no header parameters at all, p.13), so it is
reachable by anyone who finds the URL, and ElementTree will happily expand
nested internal entities.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from xml.sax.saxutils import escape

from api.integrations.timwe.errors import SYNC_INVALID_FORMAT, SYNC_OK

SYNC_NAMESPACE = 'http://www.csapi.org/schema/parlayx/data/sync/v1_0/local'
SOAP_NAMESPACE = 'http://schemas.xmlsoap.org/soap/envelope/'

UPDATE_TYPE_ADD = 1
UPDATE_TYPE_DELETE = 2
UPDATE_TYPE_UPDATE = 3

UPDATE_TYPE_LABELS = {
    UPDATE_TYPE_ADD: 'subscription',
    UPDATE_TYPE_DELETE: 'unsubscription',
    UPDATE_TYPE_UPDATE: 'update',
}

USER_TYPE_MOBILE = 0
USER_TYPE_EMAIL = 11

#: Enough for the largest example in the guide with generous headroom. An
#: unauthenticated endpoint should not hand an arbitrary-sized document to the
#: XML parser.
MAX_PAYLOAD_BYTES = 64 * 1024


class SyncOrderRelationParseError(ValueError):
    """The request could not be understood. Answered with code 1211."""


@dataclass
class SyncOrderRelation:
    """One parsed syncOrderRelation request."""

    user_id: str
    user_type: int
    sp_id: str
    product_id: str
    service_id: str
    update_type: int
    update_time: str
    service_list: str = ''
    update_desc: str = ''
    effective_time: str = ''
    expiry_time: str = ''
    extensions: dict[str, str] = field(default_factory=dict)

    @property
    def is_subscribe(self) -> bool:
        return self.update_type == UPDATE_TYPE_ADD

    @property
    def is_unsubscribe(self) -> bool:
        return self.update_type == UPDATE_TYPE_DELETE

    @property
    def event_label(self) -> str:
        return UPDATE_TYPE_LABELS.get(self.update_type, 'unknown')

    @property
    def msisdn(self) -> str:
        """The subscriber number, for mobile users only."""
        return self.user_id if self.user_type == USER_TYPE_MOBILE else ''

    @property
    def transaction_id(self) -> str:
        return self.extensions.get('transactionID', '')

    @property
    def order_key(self) -> str:
        return self.extensions.get('orderKey', '')

    @property
    def keyword(self) -> str:
        return self.extensions.get('keyword', '')

    @property
    def update_reason(self) -> str:
        return self.extensions.get('updateReason', '')

    @property
    def is_free_period(self) -> bool:
        return self.extensions.get('isFreePeriod', '').strip().lower() == 'true'

    @property
    def service_ids(self) -> list[str]:
        """
        Subservice IDs. Bundles carry several separated by ``|``; a
        non-bundle product repeats serviceID (guide p.14).
        """
        source = self.service_list or self.service_id
        return [part for part in source.split('|') if part]

    def parsed_update_time(self) -> datetime | None:
        return parse_ma_timestamp(self.update_time)

    def parsed_expiry_time(self) -> datetime | None:
        return parse_ma_timestamp(self.expiry_time)


def parse_ma_timestamp(value: str) -> datetime | None:
    """Read ``yyyyMMddHHmmss`` UTC, or None when absent or malformed."""
    if not value or len(value.strip()) != 14:
        return None
    try:
        return datetime.strptime(value.strip(), '%Y%m%d%H%M%S').replace(tzinfo=UTC)
    except ValueError:
        return None


def _localname(element) -> str:
    return element.tag.rsplit('}', 1)[-1]


def _find(parent, name: str):
    for child in parent.iter():
        if _localname(child) == name:
            return child
    return None


def _text(parent, name: str, default: str = '') -> str:
    element = _find(parent, name)
    if element is None or element.text is None:
        return default
    return element.text.strip()


def parse_sync_order_relation(payload: bytes | str) -> SyncOrderRelation:
    """
    Parse a syncOrderRelation envelope.

    Raises SyncOrderRelationParseError for anything the guide marks mandatory
    but absent, so the caller can answer 1211 rather than half-applying a
    subscription change.
    """
    raw = payload.encode('utf-8') if isinstance(payload, str) else payload
    if not raw or not raw.strip():
        raise SyncOrderRelationParseError('Empty request body.')
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise SyncOrderRelationParseError('Request body is larger than the permitted size.')

    head = raw[:2048].lstrip().lower()
    if b'<!doctype' in head or b'<!entity' in head:
        raise SyncOrderRelationParseError('Document type declarations are not accepted.')

    try:
        root = ET.fromstring(raw)  # noqa: S314
    except ET.ParseError as exc:
        raise SyncOrderRelationParseError(f'Request is not well-formed XML: {exc}') from exc

    body = _find(root, 'syncOrderRelation')
    if body is None:
        raise SyncOrderRelationParseError('No syncOrderRelation element in the request body.')

    user_element = _find(body, 'userID')
    if user_element is None:
        raise SyncOrderRelationParseError('userID is mandatory.')

    user_id = _text(user_element, 'ID')
    if not user_id:
        raise SyncOrderRelationParseError('userID/ID is mandatory.')

    raw_user_type = _text(user_element, 'type')
    try:
        user_type = int(raw_user_type)
    except (TypeError, ValueError) as exc:
        raise SyncOrderRelationParseError('userID/type must be an integer.') from exc

    raw_update_type = _text(body, 'updateType')
    try:
        update_type = int(raw_update_type)
    except (TypeError, ValueError) as exc:
        raise SyncOrderRelationParseError('updateType must be an integer.') from exc
    if update_type not in UPDATE_TYPE_LABELS:
        raise SyncOrderRelationParseError(
            f'updateType {update_type} is not one of 1 (Add), 2 (Delete) or 3 (Update).'
        )

    for name in ('spID', 'productID', 'serviceID', 'updateTime'):
        if not _text(body, name):
            raise SyncOrderRelationParseError(f'{name} is mandatory.')

    extensions: dict[str, str] = {}
    extension_root = _find(body, 'extensionInfo')
    if extension_root is not None:
        for item in extension_root:
            if _localname(item) != 'item':
                continue
            key = _text(item, 'key')
            if key:
                extensions[key] = _text(item, 'value')

    return SyncOrderRelation(
        user_id=user_id,
        user_type=user_type,
        sp_id=_text(body, 'spID'),
        product_id=_text(body, 'productID'),
        service_id=_text(body, 'serviceID'),
        service_list=_text(body, 'serviceList'),
        update_type=update_type,
        update_time=_text(body, 'updateTime'),
        update_desc=_text(body, 'updateDesc'),
        effective_time=_text(body, 'effectiveTime'),
        expiry_time=_text(body, 'expiryTime'),
        extensions=extensions,
    )


def build_response(result: str = SYNC_OK, description: str = 'Success') -> str:
    """
    Build a syncOrderRelationResponse envelope.

    ``result`` is ``"0"`` for success and an error code from errors.py
    otherwise (guide p.16). Returned with HTTP 200 either way: the code in the
    body is what the MA reads, and a non-2xx status would make it retry a
    request we have already decided about.
    """
    return f"""<soapenv:Envelope xmlns:soapenv="{SOAP_NAMESPACE}">
  <soapenv:Body>
    <ns1:syncOrderRelationResponse xmlns:ns1="{SYNC_NAMESPACE}">
      <ns1:result>{escape(result)}</ns1:result>
      <ns1:resultDescription>{escape(description)}</ns1:resultDescription>
    </ns1:syncOrderRelationResponse>
  </soapenv:Body>
</soapenv:Envelope>"""


def build_error_response(result: str = SYNC_INVALID_FORMAT, description: str = '') -> str:
    from api.integrations.timwe.errors import SYNC_ORDER_RELATION_ERRORS

    return build_response(
        result=result,
        description=description or SYNC_ORDER_RELATION_ERRORS.get(result, 'Request failed.'),
    )
