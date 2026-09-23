"""
Tests for the TIMWE Master Aggregator integration.

The syncOrderRelation fixtures are the guide's own example documents
(pp.10-13) copied verbatim, so a parser change that drifts from the spec fails
here rather than in production against a live subscriber.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from api.integrations.timwe import datasync, errors
from api.integrations.timwe.datasync import (
    SyncOrderRelationParseError,
    build_error_response,
    build_response,
    parse_sync_order_relation,
)

pytestmark = pytest.mark.unit


# Guide p.10-12. Trimmed to the extensionInfo items the parser exposes.
SUBSCRIPTION_XML = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <soapenv:Body>
    <ns1:syncOrderRelation xmlns:ns1="http://www.csapi.org/schema/parlayx/data/sync/v1_0/local">
      <ns1:userID>
        <ID>8619800000001</ID>
        <type>0</type>
      </ns1:userID>
      <ns1:spID>001100</ns1:spID>
      <ns1:productID>1000000423</ns1:productID>
      <ns1:serviceID>0011002000001100</ns1:serviceID>
      <ns1:serviceList>0011002000001100</ns1:serviceList>
      <ns1:updateType>1</ns1:updateType>
      <ns1:updateTime>20130723082551</ns1:updateTime>
      <ns1:updateDesc>Addition</ns1:updateDesc>
      <ns1:effectiveTime>20130723082551</ns1:effectiveTime>
      <ns1:expiryTime>20361231160000</ns1:expiryTime>
      <ns1:extensionInfo>
        <item><key>accessCode</key><value>20086</value></item>
        <item><key>isFreePeriod</key><value>false</value></item>
        <item><key>transactionID</key><value>504016000001307231624304170004</value></item>
        <item><key>orderKey</key><value>999000000000000194</value></item>
        <item><key>keyword</key><value>sub</value></item>
        <item><key>channelID</key><value>1</value></item>
      </ns1:extensionInfo>
    </ns1:syncOrderRelation>
  </soapenv:Body>
</soapenv:Envelope>"""

# Guide p.12-13.
UNSUBSCRIPTION_XML = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <ns1:syncOrderRelation xmlns:ns1="http://www.csapi.org/schema/parlayx/data/sync/v1_0/local">
      <ns1:userID>
        <ID>8619800000001</ID>
        <type>0</type>
      </ns1:userID>
      <ns1:spID>001100</ns1:spID>
      <ns1:productID>1000000423</ns1:productID>
      <ns1:serviceID>0011002000001100</ns1:serviceID>
      <ns1:updateType>2</ns1:updateType>
      <ns1:updateTime>20130723094953</ns1:updateTime>
      <ns1:updateDesc>Deletion</ns1:updateDesc>
      <ns1:expiryTime>20130723094952</ns1:expiryTime>
      <ns1:extensionInfo>
        <item><key>updateReason</key><value>1</value></item>
        <item><key>keyword</key><value>unsub</value></item>
      </ns1:extensionInfo>
    </ns1:syncOrderRelation>
  </soapenv:Body>
</soapenv:Envelope>"""


def _without(xml: str, element: str) -> str:
    import re

    return re.sub(rf'\s*<ns1:{element}>.*?</ns1:{element}>', '', xml, flags=re.S)


# ---------------------------------------------------------------------------
# syncOrderRelation parsing
# ---------------------------------------------------------------------------


def test_parses_the_guides_subscription_example():
    relation = parse_sync_order_relation(SUBSCRIPTION_XML)

    assert relation.user_id == '8619800000001'
    assert relation.user_type == datasync.USER_TYPE_MOBILE
    assert relation.msisdn == '8619800000001'
    assert relation.sp_id == '001100'
    assert relation.product_id == '1000000423'
    assert relation.service_id == '0011002000001100'
    assert relation.update_type == datasync.UPDATE_TYPE_ADD
    assert relation.is_subscribe
    assert not relation.is_unsubscribe
    assert relation.event_label == 'subscription'


def test_parses_the_guides_unsubscription_example():
    relation = parse_sync_order_relation(UNSUBSCRIPTION_XML)

    assert relation.update_type == datasync.UPDATE_TYPE_DELETE
    assert relation.is_unsubscribe
    assert relation.event_label == 'unsubscription'
    assert relation.update_reason == '1'
    assert relation.keyword == 'unsub'


def test_extension_info_items_become_a_mapping():
    relation = parse_sync_order_relation(SUBSCRIPTION_XML)

    assert relation.transaction_id == '504016000001307231624304170004'
    assert relation.order_key == '999000000000000194'
    assert relation.keyword == 'sub'
    assert relation.extensions['accessCode'] == '20086'
    assert relation.is_free_period is False


def test_timestamps_are_read_as_utc():
    relation = parse_sync_order_relation(SUBSCRIPTION_XML)
    parsed = relation.parsed_update_time()

    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == (2013, 7, 23)
    assert parsed.utcoffset().total_seconds() == 0


def test_missing_service_list_falls_back_to_service_id():
    # Guide p.14: a non-bundle product repeats serviceID in serviceList.
    relation = parse_sync_order_relation(UNSUBSCRIPTION_XML)
    assert relation.service_ids == ['0011002000001100']


def test_bundle_service_list_splits_on_pipe():
    xml = SUBSCRIPTION_XML.replace(
        '<ns1:serviceList>0011002000001100</ns1:serviceList>',
        '<ns1:serviceList>0003042000001075|0003042000001076</ns1:serviceList>',
    )
    relation = parse_sync_order_relation(xml)
    assert relation.service_ids == ['0003042000001075', '0003042000001076']


def test_parsing_ignores_the_namespace_prefix():
    # Nothing in the guide fixes "ns1"; only the namespace URI is normative.
    xml = SUBSCRIPTION_XML.replace('ns1:', 'sync:').replace('xmlns:sync=', 'xmlns:sync=')
    relation = parse_sync_order_relation(xml.replace('xmlns:ns1=', 'xmlns:sync='))
    assert relation.product_id == '1000000423'


@pytest.mark.parametrize('element', ['spID', 'productID', 'serviceID', 'updateTime'])
def test_missing_mandatory_element_is_rejected(element):
    with pytest.raises(SyncOrderRelationParseError, match=element):
        parse_sync_order_relation(_without(SUBSCRIPTION_XML, element))


def test_missing_user_id_is_rejected():
    with pytest.raises(SyncOrderRelationParseError, match='userID'):
        parse_sync_order_relation(_without(SUBSCRIPTION_XML, 'userID'))


def test_unknown_update_type_is_rejected():
    xml = SUBSCRIPTION_XML.replace(
        '<ns1:updateType>1</ns1:updateType>', '<ns1:updateType>9</ns1:updateType>'
    )
    with pytest.raises(SyncOrderRelationParseError, match='updateType'):
        parse_sync_order_relation(xml)


def test_non_numeric_update_type_is_rejected():
    xml = SUBSCRIPTION_XML.replace(
        '<ns1:updateType>1</ns1:updateType>', '<ns1:updateType>add</ns1:updateType>'
    )
    with pytest.raises(SyncOrderRelationParseError):
        parse_sync_order_relation(xml)


def test_malformed_xml_is_rejected():
    with pytest.raises(SyncOrderRelationParseError, match='well-formed'):
        parse_sync_order_relation('<soapenv:Envelope><unclosed>')


def test_empty_body_is_rejected():
    with pytest.raises(SyncOrderRelationParseError, match='Empty'):
        parse_sync_order_relation(b'')


def test_doctype_is_refused():
    # The endpoint is unauthenticated (guide p.13), and ElementTree expands
    # nested internal entities. A billion-laughs payload must not reach it.
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;">]><lolz>&lol2;</lolz>'
    )
    with pytest.raises(SyncOrderRelationParseError, match='Document type'):
        parse_sync_order_relation(bomb)


def test_oversized_payload_is_refused():
    padding = '<x>' + ('a' * datasync.MAX_PAYLOAD_BYTES) + '</x>'
    with pytest.raises(SyncOrderRelationParseError, match='larger than'):
        parse_sync_order_relation(padding)


def test_email_user_type_has_no_msisdn():
    xml = SUBSCRIPTION_XML.replace('<type>0</type>', '<type>11</type>')
    relation = parse_sync_order_relation(xml)
    assert relation.user_type == datasync.USER_TYPE_EMAIL
    assert relation.msisdn == ''


# ---------------------------------------------------------------------------
# syncOrderRelation response
# ---------------------------------------------------------------------------


def test_success_response_carries_result_zero():
    body = build_response()
    assert '<ns1:result>0</ns1:result>' in body
    assert datasync.SYNC_NAMESPACE in body


def test_error_response_uses_the_guides_code_and_description():
    body = build_error_response(errors.SYNC_SERVICE_NOT_FOUND)
    assert '<ns1:result>2032</ns1:result>' in body
    assert 'The service does not exist.' in body


def test_response_escapes_its_description():
    body = build_response(errors.SYNC_OK, 'a & b <c>')
    assert '&amp;' in body and '&lt;c&gt;' in body
    assert '<c>' not in body.split('resultDescription')[1][:40]


def test_every_documented_sync_error_code_is_defined():
    for code in ('1211', '2030', '2031', '2032', '2033', '2034', '2500'):
        assert code in errors.SYNC_ORDER_RELATION_ERRORS


# ---------------------------------------------------------------------------
# chargeAmount
# ---------------------------------------------------------------------------


@pytest.fixture
def charge_settings(settings):
    settings.TIMWE_CHARGE_URL = (
        'http://ma.example:8080/AmountChargingService/services/AmountCharging'
    )
    settings.TIMWE_SP_ID = '000201'
    settings.TIMWE_SP_PASSWORD = 'secret'
    settings.TIMWE_SERVICE_ID = '3500001000012'
    settings.TIMWE_CURRENCY = 'ETB'
    return settings


def test_sp_password_matches_the_documented_md5_formula(charge_settings):
    import hashlib

    from api.integrations.timwe.charge import TimweChargeService

    timestamp = '20100731064245'
    # MD5 is the MA's choice of authenticator (guide p.20), not ours.
    expected = hashlib.md5(b'000201secret20100731064245').hexdigest()  # noqa: S324
    assert TimweChargeService.build_sp_password(timestamp) == expected


def test_request_contains_every_documented_header_field(charge_settings):
    from api.integrations.timwe.charge import TimweChargeService

    xml = TimweChargeService.build_soap_request(
        msisdn='251912345678',
        amount=20,
        description='FlipStar weekly',
        reference_code='REF-1',
        timestamp='20100731064245',
    )
    for field in ('spId', 'spPassword', 'serviceId', 'timeStamp', 'OA', 'FA'):
        assert f'v2:{field}' in xml
    assert '<loc:endUserIdentifier>tel:251912345678</loc:endUserIdentifier>' in xml
    assert '<amount>2000</amount>' in xml  # 20 Birr in minor units
    assert '<currency>ETB</currency>' in xml
    assert '<loc:referenceCode>REF-1</loc:referenceCode>' in xml


def test_fa_equals_oa(charge_settings):
    # Guide p.21: "The value must be the same as the OA value."
    from api.integrations.timwe.charge import TimweChargeService

    xml = TimweChargeService.build_soap_request(
        msisdn='251912345678',
        amount=3,
        description='d',
        reference_code='R',
    )
    import re

    oa = re.search(r'<v2:OA>(.*?)</v2:OA>', xml).group(1)
    fa = re.search(r'<v2:FA>(.*?)</v2:FA>', xml).group(1)
    assert oa == fa == '251912345678'


def test_account_password_never_appears_in_the_envelope(charge_settings):
    from api.integrations.timwe.charge import TimweChargeService

    xml = TimweChargeService.build_soap_request(
        msisdn='251912345678',
        amount=3,
        description='d',
        reference_code='R',
    )
    assert 'secret' not in xml


def test_fractional_amount_is_refused(charge_settings):
    # The MA has no decimal point (guide p.21). Rounding would mis-bill.
    from api.integrations.timwe.charge import TimweChargeService

    with pytest.raises(errors.TimweAmountError, match='fractional'):
        TimweChargeService.format_amount(Decimal('3.50'))


def test_whole_decimal_amount_is_accepted(charge_settings):
    from api.integrations.timwe.charge import TimweChargeService

    # Birr in, minor units out: their gateway bills 10 Birr for 1000.
    assert TimweChargeService.format_amount(Decimal('20.00')) == '2000'


def test_amount_beyond_four_characters_is_refused(charge_settings):
    from api.integrations.timwe.charge import TimweChargeService

    with pytest.raises(errors.TimweAmountError, match='exceeds'):
        TimweChargeService.format_amount(12345)


def test_negative_amount_is_refused(charge_settings):
    from api.integrations.timwe.charge import TimweChargeService

    with pytest.raises(errors.TimweAmountError):
        TimweChargeService.format_amount(-1)


def test_missing_configuration_refuses_to_build_a_request(settings):
    from api.integrations.timwe.charge import TimweChargeService

    settings.TIMWE_CHARGE_URL = ''
    settings.TIMWE_SP_ID = ''
    settings.TIMWE_SP_PASSWORD = ''
    settings.TIMWE_SERVICE_ID = ''
    settings.TIMWE_CURRENCY = ''
    with pytest.raises(errors.TimweConfigurationError):
        TimweChargeService.build_soap_request(
            msisdn='251912345678',
            amount=3,
            description='d',
            reference_code='R',
        )


def test_overlong_reference_code_is_refused(charge_settings):
    from api.integrations.timwe.charge import TimweChargeService

    with pytest.raises(errors.TimweError, match='referenceCode'):
        TimweChargeService.build_soap_request(
            msisdn='251912345678',
            amount=3,
            description='d',
            reference_code='R' * 31,
        )


def test_empty_response_is_treated_as_success(charge_settings):
    # Guide p.22: a successful chargeAmountResponse is an empty element.
    from api.integrations.timwe.charge import TimweChargeService

    body = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
      <soapenv:Body>
        <ns1:chargeAmountResponse
          xmlns:ns1="http://www.csapi.org/schema/parlayx/payment/amount_charging/v2_1/local"/>
      </soapenv:Body>
    </soapenv:Envelope>"""
    success, code, _ = TimweChargeService.parse_soap_response(body)
    assert success is True
    assert code is None


def test_fault_response_yields_the_error_code(charge_settings):
    from api.integrations.timwe.charge import TimweChargeService

    body = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
      <soapenv:Body>
        <soapenv:Fault>
          <faultcode>SVC0901</faultcode>
          <faultstring>Sp password is not accepted!</faultstring>
        </soapenv:Fault>
      </soapenv:Body>
    </soapenv:Envelope>"""
    success, code, message = TimweChargeService.parse_soap_response(body)
    assert success is False
    assert code == errors.CHARGE_AUTH_FAILED
    assert 'password' in message


def test_retryable_and_permanent_faults_are_distinguished():
    from api.integrations.timwe.charge import TimweChargeService

    assert TimweChargeService.is_retryable(errors.CHARGE_TIMEOUT)
    assert TimweChargeService.is_retryable(errors.CHARGE_FAILED)
    assert TimweChargeService.is_permanent(errors.CHARGE_AUTH_FAILED)
    assert TimweChargeService.is_permanent(errors.CHARGE_AMOUNT_OUT_OF_RANGE)
    assert not TimweChargeService.is_retryable(errors.CHARGE_AUTH_FAILED)


def test_unparseable_response_is_not_a_success(charge_settings):
    from api.integrations.timwe.charge import TimweChargeService

    success, _, message = TimweChargeService.parse_soap_response('not xml at all <')
    assert success is False
    assert 'Malformed' in message


def test_empty_response_body_is_not_a_success(charge_settings):
    from api.integrations.timwe.charge import TimweChargeService

    success, _, _ = TimweChargeService.parse_soap_response('')
    assert success is False
