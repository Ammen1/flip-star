"""
Console visibility for the TIMWE datasync endpoint.

The endpoint already wrote a TimweSyncOrderLog row per event, but nothing
reached the log stream: the raw request was only ever stored in the database,
and the SOAP response body was not recorded anywhere at all. During onboarding
the MA's traffic is the only evidence of what it actually sends, and a database
row cannot be watched live.

Both directions are logged at INFO, gated on TIMWE_LOG_PAYLOADS.
"""

import pytest
from django.test import override_settings

from api.models import SubscriptionTier

pytestmark = pytest.mark.django_db

URL = '/api/v1/timwe/sync-order-relation/'
SOAP_CONTENT_TYPE = 'text/xml; charset=utf-8'

ENVELOPE = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <ns1:syncOrderRelation xmlns:ns1="http://www.csapi.org/schema/parlayx/data/sync/v1_0/local">
      <ns1:userID><ID>251912345678</ID><type>0</type></ns1:userID>
      <ns1:spID>001100</ns1:spID>
      <ns1:productID>1000000423</ns1:productID>
      <ns1:serviceID>0011002000001100</ns1:serviceID>
      <ns1:updateType>1</ns1:updateType>
      <ns1:updateTime>20260830120000</ns1:updateTime>
    </ns1:syncOrderRelation>
  </soapenv:Body>
</soapenv:Envelope>"""


def post(client, body=ENVELOPE):
    return client.post(URL, data=body.encode('utf-8'), content_type=SOAP_CONTENT_TYPE)


@pytest.fixture
def tier():
    """So the request reaches observation mode rather than 'unmapped product'."""
    return SubscriptionTier.objects.create(
        name='Daily Premium',
        slug='daily-premium',
        duration_type='daily',
        duration_days=1,
        price_etb=5,
        # Matches the productID in the envelope above.
        product_id='1000000423',
        # slug and onevas_code are both unique; two tiers defaulting to ''
        # collide on insert.
        onevas_code='TDAILY',
    )


@override_settings(TIMWE_LOG_PAYLOADS=True)
def test_the_request_body_is_logged(client, tier, caplog):
    with caplog.at_level('INFO', logger='api.views.timwe'):
        post(client)

    assert any('--> request' in r.message for r in caplog.records)
    assert any('251912345678' in r.getMessage() for r in caplog.records)


@override_settings(TIMWE_LOG_PAYLOADS=True)
def test_the_response_body_is_logged(client, tier, caplog):
    with caplog.at_level('INFO', logger='api.views.timwe'):
        post(client)

    logged = ' '.join(r.getMessage() for r in caplog.records)
    assert '<-- response' in logged
    assert 'syncOrderRelationResponse' in logged or 'result' in logged.lower()


@override_settings(TIMWE_LOG_PAYLOADS=True)
def test_the_source_and_size_are_logged(client, tier, caplog):
    """Enough context to tell one caller's traffic from another's."""
    with caplog.at_level('INFO', logger='api.views.timwe'):
        post(client)

    request_log = next(r.getMessage() for r in caplog.records if '--> request' in r.message)
    assert 'text/xml' in request_log
    assert 'bytes' in request_log


@override_settings(TIMWE_LOG_PAYLOADS=True)
def test_a_malformed_request_is_still_logged(client, caplog):
    """The case you most need to see."""
    with caplog.at_level('INFO', logger='api.views.timwe'):
        post(client, '<not-soap/>')

    logged = ' '.join(r.getMessage() for r in caplog.records)
    assert '--> request' in logged
    assert '<-- response' in logged


@override_settings(TIMWE_LOG_PAYLOADS=True, TIMWE_ALLOWED_IPS=['203.0.113.9'])
def test_a_rejected_source_is_still_logged(client, caplog):
    """
    Logged before the allowlist check, deliberately.

    A request refused by source IP would otherwise leave no trace, which is
    the opposite of what an allowlist rollout needs.
    """
    with caplog.at_level('INFO', logger='api.views.timwe'):
        response = post(client)

    assert response.status_code == 403
    logged = ' '.join(r.getMessage() for r in caplog.records)
    assert '--> request' in logged
    assert '<-- response 403' in logged


@override_settings(TIMWE_LOG_PAYLOADS=False)
def test_logging_can_be_turned_off(client, tier, caplog):
    """The payload carries a subscriber MSISDN, so this has to be switchable."""
    with caplog.at_level('INFO', logger='api.views.timwe'):
        post(client)

    logged = ' '.join(r.getMessage() for r in caplog.records)
    assert '--> request' not in logged
    assert '<-- response' not in logged
    assert '251912345678' not in logged


@override_settings(TIMWE_LOG_PAYLOADS=True)
def test_logging_does_not_change_the_response(client, tier):
    """Observation only -- the endpoint's behaviour is untouched."""
    response = post(client)

    assert response.status_code == 200
    assert response['Content-Type'] == SOAP_CONTENT_TYPE
    assert b'syncOrderRelation' in response.content


@override_settings(TIMWE_LOG_PAYLOADS=True)
def test_an_oversized_payload_is_truncated_in_the_log(client, tier, caplog):
    """A log line is not a place to put an unbounded payload."""
    from api.views.timwe import LOG_PAYLOAD_LIMIT

    with caplog.at_level('INFO', logger='api.views.timwe'):
        post(client, '<x>' + ('A' * (LOG_PAYLOAD_LIMIT + 5000)) + '</x>')

    request_log = next(r.getMessage() for r in caplog.records if '--> request' in r.message)
    assert 'more chars]' in request_log
    assert len(request_log) < LOG_PAYLOAD_LIMIT + 500
