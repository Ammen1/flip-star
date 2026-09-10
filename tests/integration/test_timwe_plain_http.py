"""
TIMWE's notifications must survive arriving over plain HTTP.

The Master Aggregator POSTs syncOrderRelation in plain HTTP over the IPsec
tunnel. With SECURE_SSL_REDIRECT on, Django answers any plain-HTTP request
with a 301 to HTTPS -- and a SOAP client does not follow a redirect on a POST,
so the body is dropped. That is precisely how Telebirr's callbacks were lost
after the 29 Aug rebuild, and the fix there was SECURE_REDIRECT_EXEMPT.

These tests read the exempt list straight out of config/settings/production.py
with ``ast`` rather than importing it, because importing production settings
requires production configuration. What is asserted is the list that actually
ships.
"""

import ast
import re
from pathlib import Path

import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db

PRODUCTION = Path(__file__).resolve().parents[2] / 'config' / 'settings' / 'production.py'

ENVELOPE = b"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
<soapenv:Body><ns1:syncOrderRelation xmlns:ns1="http://www.csapi.org/schema/parlayx/data/sync/v1_0/local">
<ns1:userID><ID>251912345678</ID><type>0</type></ns1:userID>
<ns1:spID>300263</ns1:spID><ns1:productID>10000302850</ns1:productID>
<ns1:serviceID>30026300007331</ns1:serviceID><ns1:updateType>1</ns1:updateType>
<ns1:updateTime>20260910120000</ns1:updateTime>
</ns1:syncOrderRelation></soapenv:Body></soapenv:Envelope>"""


def production_exempt_list():
    tree = ast.parse(PRODUCTION.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, 'id', None) == 'SECURE_REDIRECT_EXEMPT' for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError('SECURE_REDIRECT_EXEMPT not found in production settings')


def exempt(path):
    """Django matches these against the path with its leading slash removed."""
    return any(re.search(pattern, path.lstrip('/')) for pattern in production_exempt_list())


@pytest.mark.parametrize(
    'path',
    [
        '/api/v1/timwe/sync-order-relation',  # what the MA is configured with
        '/api/v1/timwe/sync-order-relation/',
        '/api/timwe/sync-order-relation',  # the API is also served at /api/
    ],
)
def test_the_timwe_endpoint_is_exempt(path):
    assert exempt(path)


@pytest.mark.parametrize(
    'path',
    ['/api/v1/auth/login/', '/api/v1/admin/sms/health/', '/api/v1/reels/', '/'],
)
def test_nothing_else_is(path):
    """Scoped to the one endpoint; the rest of the site keeps its redirect."""
    assert not exempt(path)


def test_telebirr_is_still_exempt():
    """The existing exemption this one sits beside is untouched."""
    assert exempt('/api/v1/webhooks/telebirrUssdPurchase/')


def test_a_plain_http_notification_is_not_redirected(client):
    """
    End to end through SecurityMiddleware, with the redirect switched on.

    A 301 here is the failure: TIMWE's SOAP client would drop the body and a
    subscriber it had charged would never be activated.
    """
    with override_settings(
        SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=production_exempt_list()
    ):
        response = client.post(
            '/api/v1/timwe/sync-order-relation',
            data=ENVELOPE,
            content_type='text/xml; charset=utf-8',
            secure=False,
        )

    assert response.status_code != 301
    assert response.status_code == 200
    assert b'syncOrderRelationResponse' in response.content


def test_other_plain_http_requests_are_still_redirected(client):
    """The exemption must not quietly disable HTTPS for everything."""
    with override_settings(
        SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=production_exempt_list()
    ):
        response = client.get('/api/v1/health/', secure=False)

    assert response.status_code == 301
