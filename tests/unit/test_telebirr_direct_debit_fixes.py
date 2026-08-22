"""
Regression tests for three bugs fixed in api/integrations/telebirr/direct_debit.py
by porting behaviour already fixed on the `master` branch:

1. initiate_debit() never sent MandateID, so Telebirr couldn't tie a debit to
   a specific mandate when a payer has more than one.
2. query_mandate_by_payer() only returned raw response_text, with no
   structured way to tell which mandate matched when a payer has several.
3. create_one_off_payment() only special-cased datetime instances when
   formatting dates; a plain date object silently fell through unformatted
   and was embedded in the SOAP request as "2026-08-16" instead of the
   "20260816" Telebirr requires.

No live network call is made -- requests.post is mocked and its call
arguments inspected. No database is used (see tests/conftest.py); this
service class doesn't need one.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from api.integrations.telebirr.direct_debit import TelebirrDirectDebitService

pytestmark = pytest.mark.unit

_POST = 'api.integrations.telebirr.direct_debit.requests.post'
_OK_RESPONSE = MagicMock(
    status_code=200,
    text='<res:ResponseCode>0</res:ResponseCode><res:ResponseDesc>OK</res:ResponseDesc>',
)


@pytest.fixture
def service():
    return TelebirrDirectDebitService()


# ---------------------------------------------------------------------------
# Fix 1: initiate_debit() MandateID parameter
# ---------------------------------------------------------------------------

def test_initiate_debit_includes_mandate_id_when_provided(service):
    with patch(_POST, return_value=_OK_RESPONSE) as mock_post:
        service.initiate_debit('payer-ref-1', 100, mandate_id='MANDATE123')

    sent_body = mock_post.call_args.kwargs['data']
    assert '<com:Key>MandateID</com:Key>' in sent_body
    assert '<com:Value>MANDATE123</com:Value>' in sent_body


def test_initiate_debit_omits_mandate_id_when_not_provided(service):
    with patch(_POST, return_value=_OK_RESPONSE) as mock_post:
        service.initiate_debit('payer-ref-1', 100)

    sent_body = mock_post.call_args.kwargs['data']
    assert 'MandateID' not in sent_body


def test_initiate_debit_still_succeeds_without_mandate_id(service):
    """The parameter is optional -- existing callers that don't pass it must
    keep working exactly as before."""
    with patch(_POST, return_value=_OK_RESPONSE):
        result = service.initiate_debit('payer-ref-1', 100)

    assert result['success'] is True


# ---------------------------------------------------------------------------
# Fix 2: query_mandate_by_payer() structured multi-mandate parsing
# ---------------------------------------------------------------------------

_MULTI_MANDATE_RESPONSE = """<?xml version="1.0"?>
<soapenv:Envelope>
<res:ResponseCode>0</res:ResponseCode>
<res:ResponseDesc>Success</res:ResponseDesc>
<res:DirectDebitMandateInfo>
  <com:MandateID>MID001</com:MandateID>
  <com:PayerReferenceNumber>REF001</com:PayerReferenceNumber>
  <com:MandateStatus>03</com:MandateStatus>
</res:DirectDebitMandateInfo>
<res:DirectDebitMandateInfo>
  <com:MandateID>MID002</com:MandateID>
  <com:PayerReferenceNumber>REF002</com:PayerReferenceNumber>
  <com:MandateStatus>01</com:MandateStatus>
</res:DirectDebitMandateInfo>
</soapenv:Envelope>"""

_SINGLE_MANDATE_RESPONSE = """<?xml version="1.0"?>
<soapenv:Envelope>
<res:ResponseCode>0</res:ResponseCode>
<res:ResponseDesc>OK</res:ResponseDesc>
<res:DirectDebitMandateInfo>
  <com:MandateID>MID099</com:MandateID>
  <com:PayerReferenceNumber>REF099</com:PayerReferenceNumber>
  <com:MandateStatus>03</com:MandateStatus>
</res:DirectDebitMandateInfo>
</soapenv:Envelope>"""


def test_query_mandate_parses_every_mandate_block(service):
    with patch(_POST, return_value=MagicMock(status_code=200, text=_MULTI_MANDATE_RESPONSE)):
        result = service.query_mandate_by_payer('251911223344')

    assert result['success'] is True
    assert len(result['mandates']) == 2
    assert result['mandates'][0] == {
        'mandate_id': 'MID001', 'payer_reference_number': 'REF001', 'mandate_status': '03',
    }
    assert result['mandates'][1] == {
        'mandate_id': 'MID002', 'payer_reference_number': 'REF002', 'mandate_status': '01',
    }


def test_query_mandate_still_returns_raw_response_text(service):
    """response_text is preserved for any existing caller that parses it itself."""
    with patch(_POST, return_value=MagicMock(status_code=200, text=_MULTI_MANDATE_RESPONSE)):
        result = service.query_mandate_by_payer('251911223344')

    assert result['response_text'] == _MULTI_MANDATE_RESPONSE


def test_query_mandate_single_result_populates_top_level_convenience_fields(service):
    with patch(_POST, return_value=MagicMock(status_code=200, text=_SINGLE_MANDATE_RESPONSE)):
        result = service.query_mandate_by_payer('251911223344')

    assert result['mandate_id'] == 'MID099'
    assert result['mandate_status'] == '03'
    assert result['payer_reference_number'] == 'REF099'
    assert result['mandates'] == [
        {'mandate_id': 'MID099', 'payer_reference_number': 'REF099', 'mandate_status': '03'},
    ]


def test_query_mandate_with_no_mandates_returns_empty_list(service):
    no_mandate_response = MagicMock(
        status_code=200,
        text='<res:ResponseCode>0</res:ResponseCode><res:ResponseDesc>None found</res:ResponseDesc>',
    )
    with patch(_POST, return_value=no_mandate_response):
        result = service.query_mandate_by_payer('251911223344')

    assert result['success'] is True
    assert result['mandates'] == []


# ---------------------------------------------------------------------------
# Fix 3: create_one_off_payment() date (not just datetime) formatting
# ---------------------------------------------------------------------------

def test_plain_date_object_is_formatted_to_yyyymmdd(service):
    plain_date = date(2026, 8, 16)  # datetime.date -- NOT a datetime.datetime

    with patch(_POST, return_value=_OK_RESPONSE) as mock_post:
        service.create_one_off_payment('251911223344', 'ref-1', first_payment_date=plain_date)

    sent_body = mock_post.call_args.kwargs['data']
    assert '<com:FirstPaymentDate>20260816</com:FirstPaymentDate>' in sent_body
    assert '2026-08-16' not in sent_body


def test_datetime_object_still_formats_correctly(service):
    dt = datetime(2026, 8, 16, 14, 30, 0)

    with patch(_POST, return_value=_OK_RESPONSE) as mock_post:
        service.create_one_off_payment('251911223344', 'ref-1', first_payment_date=dt)

    sent_body = mock_post.call_args.kwargs['data']
    assert '<com:FirstPaymentDate>20260816</com:FirstPaymentDate>' in sent_body


def test_string_date_passes_through_unformatted(service):
    """A caller that already sends YYYYMMDD as a plain string is unaffected --
    strings don't have strftime, so they hit neither branch, same as before."""
    with patch(_POST, return_value=_OK_RESPONSE) as mock_post:
        service.create_one_off_payment('251911223344', 'ref-1', first_payment_date='20260816')

    sent_body = mock_post.call_args.kwargs['data']
    assert '<com:FirstPaymentDate>20260816</com:FirstPaymentDate>' in sent_body


def test_expiry_date_as_plain_date_object_is_also_formatted(service):
    with patch(_POST, return_value=_OK_RESPONSE) as mock_post:
        service.create_one_off_payment(
            '251911223344', 'ref-1',
            first_payment_date=date(2026, 8, 16),
            expiry_date=date(2026, 9, 16),
        )

    sent_body = mock_post.call_args.kwargs['data']
    assert '<com:ExpiryDate>20260916</com:ExpiryDate>' in sent_body


def test_none_dates_still_default_to_today(service):
    """No regression on the already-working None-defaults-to-today path."""
    with patch(_POST, return_value=_OK_RESPONSE) as mock_post:
        result = service.create_one_off_payment('251911223344', 'ref-1')

    assert result['success'] is True
    sent_body = mock_post.call_args.kwargs['data']
    today = datetime.now().strftime('%Y%m%d')
    assert f'<com:FirstPaymentDate>{today}</com:FirstPaymentDate>' in sent_body
