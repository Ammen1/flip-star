"""
Which short code a withdrawal is paid from.

telebirr issues one short code per direction -- 53906 for B2C, money going
out, and 53599 for C2B, money coming in. Both directions read a single
`TELEBIRR_SHORTCODE` until now, and on staging that setting was never set at
all. `initiate_b2c_payment` renders `<req:ShortCode>` unconditionally, so
every payout left with an empty element and came back refused with a generic
error: the withdrawal was marked failed, the points were returned, and nothing
said why.

These pin the two things that stops recurring: the directions read different
settings, and a payout with no short code is refused here rather than by the
gateway.
"""

import pytest
from django.test import override_settings

from api.integrations.telebirr.direct_debit import TelebirrDirectDebitService

B2C = '53906'
C2B = '53599'


def service():
    """A fresh instance: the settings are read in __init__."""
    return TelebirrDirectDebitService()


@override_settings(TELEBIRR_B2C_SHORTCODE=B2C, TELEBIRR_SHORTCODE=C2B)
def test_the_two_directions_use_different_codes():
    svc = service()

    assert svc.b2c_shortcode == B2C, 'payouts must leave from the B2C code'
    assert svc.shortcode == C2B, 'money in still arrives at the C2B code'


@override_settings(TELEBIRR_B2C_SHORTCODE='', TELEBIRR_SHORTCODE=C2B)
def test_one_code_deployments_still_work():
    """A deployment given only one code keeps working: B2C falls back to it
    rather than refusing."""
    assert service().b2c_shortcode == C2B


@override_settings(TELEBIRR_B2C_SHORTCODE='', TELEBIRR_SHORTCODE='')
def test_a_payout_with_no_short_code_is_refused_before_it_is_sent():
    """The failure that cost real withdrawals. An unset code produced an empty
    XML element, a generic refusal, and no way to tell misconfiguration from
    an outage -- so it is caught here, named, and never reaches telebirr."""
    result = service().initiate_b2c_payment(receiver_msisdn='251911000111', amount='10.00')

    assert result['success'] is False
    assert result['code'] == 'b2c_shortcode_missing'
    # The buyer-facing text must not name internal settings.
    assert 'TELEBIRR' not in result['error']


@override_settings(TELEBIRR_B2C_SHORTCODE=B2C, TELEBIRR_SHORTCODE=C2B)
def test_the_b2c_code_is_the_one_that_reaches_the_envelope(monkeypatch):
    """Reading the setting is not the same as sending it. This captures the
    SOAP body actually built and checks which code is in it."""
    svc = service()
    sent = {}

    class _Response:
        status_code = 200
        text = '<Response><ResponseCode>0</ResponseCode></Response>'

    def _capture(url, data=None, headers=None, timeout=None, verify=None, **kwargs):
        sent['body'] = data
        return _Response()

    monkeypatch.setattr('api.integrations.telebirr.direct_debit.requests.post', _capture)
    svc.initiate_b2c_payment(receiver_msisdn='251911000111', amount='10.00')

    body = sent.get('body') or ''
    assert f'<req:ShortCode>{B2C}</req:ShortCode>' in body, body[:400]
    assert f'<req:ShortCode>{C2B}</req:ShortCode>' not in body, 'sent the C2B code on a payout'


@pytest.mark.django_db
@override_settings(TELEBIRR_B2C_SHORTCODE=B2C, TELEBIRR_SHORTCODE=C2B)
def test_money_coming_in_still_uses_the_c2b_code():
    """The mandate and debit paths must be untouched by the split."""
    svc = service()

    assert svc.shortcode == C2B
    assert svc.b2c_shortcode != svc.shortcode
