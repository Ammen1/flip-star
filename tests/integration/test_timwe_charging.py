"""
chargeAmount: the client, the transaction lifecycle, and the purchase flow.

What these tests prove, and what they do not
--------------------------------------------
They prove the request we build matches the integration guide (pp.17-24), that
every kind of reply and network failure is classified correctly, that each
charge is recorded and fulfilled exactly once, and that nothing retries an
ambiguous charge.

They do NOT prove TIMWE accepts any of it. The MA is mocked at
``requests.post`` throughout; nothing here reaches a real gateway, and a green
run is not evidence that the integration works against TIMWE. That needs the
real endpoint, which has not been supplied.

No real subscriber numbers appear here. MSISDNs are the reserved-looking test
values the rest of the suite already uses.
"""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import fakeredis
import pytest
import requests
import urllib3.exceptions as U
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from api.integrations.timwe import errors
from api.integrations.timwe.charge import (
    CURRENCY_PATTERN,
    OUTCOME_REJECTED,
    OUTCOME_SUCCESS,
    OUTCOME_TIMEOUT,
    OUTCOME_UNKNOWN,
    OUTCOME_UNREACHABLE,
    TimweChargeService,
)
from api.integrations.timwe.errors import TimweAmountError, TimweConfigurationError, TimweError
from api.models.subscription import SubscriptionPayment
from api.models.timwe import TimweChargeTransaction
from api.services.timwe_charging import (
    AirtimePurchaseRefused,
    ChargeRefused,
    fulfil_coin_purchase,
    new_reference_code,
    purchase_coins_with_airtime,
    request_charge,
    user_message,
)

pytestmark = pytest.mark.django_db

MSISDN = '251912345678'
POST = 'api.integrations.timwe.charge.requests.post'

CONFIG = {
    'TIMWE_CHARGE_URL': 'http://ma.test:8080/AmountChargingService/services/AmountCharging',
    'TIMWE_SP_ID': '000201',
    'TIMWE_SP_PASSWORD': 'account-password-for-tests',
    'TIMWE_SERVICE_ID': '3500001000012',
    'TIMWE_CURRENCY': 'ETB',
    'TIMWE_CHARGE_TIMEOUT': 60,
    # The master switch. Off in every deployment until TIMWE confirms the
    # charging details; these tests exercise the path behind it.
    'TIMWE_CHARGING_ENABLED': True,
}

SUCCESS_BODY = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <ns1:chargeAmountResponse
      xmlns:ns1="http://www.csapi.org/schema/parlayx/payment/amount_charging/v2_1/local"/>
  </soapenv:Body>
</soapenv:Envelope>"""


def fault_body(code, text='The MA rejected it', faultcode='soapenv:Server'):
    """A Parlay X fault: SOAP's classification in faultcode, the MA's in messageId."""
    return f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>{faultcode}</faultcode>
      <faultstring>{text}</faultstring>
      <detail>
        <ns2:ServiceException xmlns:ns2="http://www.csapi.org/schema/parlayx/common/v2_1">
          <messageId>{code}</messageId>
          <text>{text}</text>
        </ns2:ServiceException>
      </detail>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>"""


def reply(body, status=200):
    response = MagicMock()
    response.text = body
    response.status_code = status
    return response


def refused():
    return requests.exceptions.ConnectionError(
        U.MaxRetryError(None, '/x', reason=U.NewConnectionError(None, 'refused'))
    )


def dns_failure():
    return requests.exceptions.ConnectionError(
        U.MaxRetryError(None, '/x', reason=U.NameResolutionError('ma.test', None, OSError('no')))
    )


def reset_after_send():
    return requests.exceptions.ConnectionError(
        U.ProtocolError('Connection aborted.', ConnectionResetError())
    )


@pytest.fixture(autouse=True)
def configured(settings):
    for key, value in CONFIG.items():
        setattr(settings, key, value)
    return settings


@pytest.fixture
def user():
    """A customer who can buy coins: phone on file, and active access.

    The access is not incidental. Coins are a subscriber benefit, and every
    purchase endpoint now refuses a caller without a live plan (see
    api/services/subscription_access.coin_purchase_refusal). A fixture without
    one is refused 403 before reaching any of the charging behaviour these
    tests are about.
    """
    from datetime import timedelta

    from django.utils import timezone

    from api.models import SubscriptionTier
    from api.models.subscription import SubscriptionPlan

    u = User.objects.create_user(username='payer', password='x')
    u.profile.phone_number = MSISDN
    u.profile.save(update_fields=['phone_number'])

    SubscriptionPlan.objects.create(
        user=u,
        tier=SubscriptionTier.objects.filter(duration_type='monthly').first(),
        status='active',
        start_date=timezone.now() - timedelta(days=1),
        end_date=timezone.now() + timedelta(days=30),
    )
    return u


@pytest.fixture
def airtime_package():
    """The 10 ETB package -- the only price airtime is permitted at."""
    from api.models.contest import CoinPackage

    package, _ = CoinPackage.objects.get_or_create(
        price_etb=Decimal('10'),
        defaults={'name': 'Starter', 'coin_amount': 100, 'bonus_coins': 0, 'is_active': True},
    )
    CoinPackage.objects.filter(pk=package.pk).update(is_active=True)
    package.refresh_from_db()
    return package


def charge(user, key='purchase-1', amount=10, msisdn=MSISDN):
    return request_charge(
        user=user, msisdn=msisdn, amount=amount, description='FlipStar test', idempotency_key=key
    )


# ===========================================================================
# Configuration
# ===========================================================================


def test_fully_configured():
    assert TimweChargeService.is_configured() is True
    assert TimweChargeService.missing_configuration() == []


@pytest.mark.parametrize(
    'key',
    ['TIMWE_CHARGE_URL', 'TIMWE_SP_ID', 'TIMWE_SP_PASSWORD', 'TIMWE_SERVICE_ID', 'TIMWE_CURRENCY'],
)
def test_each_missing_value_is_named(settings, key):
    setattr(settings, key, '')

    assert TimweChargeService.is_configured() is False
    assert TimweChargeService.missing_configuration() == [key]
    with pytest.raises(TimweConfigurationError, match=key):
        TimweChargeService.ensure_configured()


def test_the_error_names_the_setting_never_its_value(settings):
    settings.TIMWE_CHARGE_URL = ''

    with pytest.raises(TimweConfigurationError) as info:
        TimweChargeService.ensure_configured()

    assert 'account-password-for-tests' not in str(info.value)
    assert '000201' not in str(info.value)


def test_the_error_says_the_smpp_host_is_not_the_charge_url(settings):
    """The confusion this integration is most at risk of."""
    settings.TIMWE_CHARGE_URL = ''

    with pytest.raises(TimweConfigurationError, match='SMPP'):
        TimweChargeService.ensure_configured()


@pytest.mark.parametrize('bad', ['abc', 0, -5, ''])
def test_an_invalid_timeout_is_refused(settings, bad):
    settings.TIMWE_CHARGE_TIMEOUT = bad

    with pytest.raises(TimweConfigurationError, match='TIMWE_CHARGE_TIMEOUT'):
        TimweChargeService.get_timeout()


def test_the_timeout_defaults_to_the_guides_sixty_seconds(settings):
    del settings.TIMWE_CHARGE_TIMEOUT

    assert TimweChargeService.get_timeout() == 60


def test_nothing_is_recorded_when_unconfigured(settings, user):
    settings.TIMWE_SERVICE_ID = ''

    with pytest.raises(TimweConfigurationError), patch(POST) as post:
        charge(user)

    post.assert_not_called()
    assert TimweChargeTransaction.objects.count() == 0


# ===========================================================================
# Authentication
# ===========================================================================


def test_the_digest_matches_the_documented_formula():
    """spPassword = MD5(spId + Password + timeStamp), guide p.20."""
    expected = hashlib.md5(  # noqa: S324 - the MA's authenticator, not ours
        b'000201account-password-for-tests20100731064245'
    ).hexdigest()

    assert TimweChargeService.build_sp_password('20100731064245') == expected


def test_the_password_is_hashed_exactly_once():
    """Hashing an already-hashed password is a classic way to fail SVC0901."""
    once = hashlib.md5(b'000201account-password-for-tests20100731064245').hexdigest()  # noqa: S324
    twice = hashlib.md5(once.encode()).hexdigest()  # noqa: S324

    digest = TimweChargeService.build_sp_password('20100731064245')
    assert digest == once
    assert digest != twice


def test_the_timestamp_is_fourteen_digits():
    assert re.fullmatch(r'\d{14}', TimweChargeService.build_timestamp())


def test_the_timestamp_is_utc_whatever_the_local_zone():
    """A +03:00 wall clock must still produce the UTC time (guide p.20)."""
    addis = timezone(timedelta(hours=3))
    moment = datetime(2026, 9, 10, 15, 30, 45, tzinfo=addis)

    with patch('api.integrations.timwe.charge.timezone.now', return_value=moment):
        stamp = TimweChargeService.build_timestamp()

    assert stamp == '20260910123045'


def test_the_digest_changes_with_the_timestamp():
    assert TimweChargeService.build_sp_password('20260910000000') != (
        TimweChargeService.build_sp_password('20260910000001')
    )


def test_the_header_timestamp_is_the_one_that_was_hashed():
    """
    One clock read, used twice.

    Two separate reads can straddle a second boundary, and the MA then
    recomputes a different digest and refuses the charge as SVC0901.
    """
    xml = TimweChargeService.build_soap_request(
        msisdn=MSISDN, amount=10, description='d', reference_code='R1'
    )
    stamp = re.search(r'<v2:timeStamp>(\d{14})</v2:timeStamp>', xml).group(1)
    digest = re.search(r'<v2:spPassword>([0-9a-f]{32})</v2:spPassword>', xml).group(1)

    assert digest == TimweChargeService.build_sp_password(stamp)


def test_the_account_password_never_reaches_the_wire():
    xml = TimweChargeService.build_soap_request(
        msisdn=MSISDN, amount=10, description='d', reference_code='R1'
    )

    assert 'account-password-for-tests' not in xml


# ===========================================================================
# SOAP request
# ===========================================================================


def build(**overrides):
    kwargs = {
        'msisdn': MSISDN,
        'amount': 10,
        'description': 'FlipStar Starter',
        'reference_code': 'FSREF0001',
        'timestamp': '20260910123045',
    }
    kwargs.update(overrides)
    return TimweChargeService.build_soap_request(**kwargs)


def test_the_namespaces_are_the_guides():
    """Exactly those of the guide's request example, p.19."""
    xml = build()

    assert 'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"' in xml
    assert 'xmlns:v2="http://www.huawei.com.cn/schema/common/v2_1"' in xml
    assert (
        'xmlns:loc="http://www.csapi.org/schema/parlayx/payment/amount_charging/v3_1/local"'
    ) in xml


def test_every_header_field_is_present():
    xml = build()

    for field in ('spId', 'spPassword', 'serviceId', 'timeStamp', 'OA', 'FA'):
        assert re.search(rf'<v2:{field}>[^<]+</v2:{field}>', xml), field
    assert '<v2:spId>000201</v2:spId>' in xml
    assert '<v2:serviceId>3500001000012</v2:serviceId>' in xml


def test_the_header_is_shaped_like_the_request_timwe_accept():
    """Their gateway's shape, not the guide's.

    The guide's example puts serviceId before timeStamp and carries an empty
    <token/>. TIMWE's own working request -- the one their endpoint answers
    200 to -- has timeStamp first and no token. A SOAP sequence is
    order-sensitive and an undeclared element fails validation, so building
    it the guide's way was refused SVC0901.

    Pinned as an ordered list rather than a set: "all six are present" was
    true of the refused envelope too.
    """
    xml = build()

    assert re.findall(r'<v2:(\w+)[/>]', xml)[:7] == [
        'RequestSOAPHeader',
        'spId',
        'spPassword',
        'timeStamp',
        'serviceId',
        'OA',
        'FA',
    ]
    assert 'token' not in xml, "the guide's empty <token/> is not in their accepted request"


def test_every_body_field_is_present():
    xml = build()

    assert f'<loc:endUserIdentifier>tel:{MSISDN}</loc:endUserIdentifier>' in xml
    assert '<description>FlipStar Starter</description>' in xml
    assert '<currency>ETB</currency>' in xml
    assert '<amount>10</amount>' in xml
    assert '<loc:referenceCode>FSREF0001</loc:referenceCode>' in xml


def test_the_charge_code_appears_only_when_given():
    assert '<code>' not in build()
    assert '<code>4523</code>' in build(charge_code='4523')


def test_oa_equals_fa():
    """Guide p.21: 'The value must be the same as the OA value.'"""
    xml = build()
    oa = re.search(r'<v2:OA>([^<]+)</v2:OA>', xml).group(1)
    fa = re.search(r'<v2:FA>([^<]+)</v2:FA>', xml).group(1)

    assert oa == fa == MSISDN


def test_the_request_parses_as_xml():
    import xml.etree.ElementTree as ET

    ET.fromstring(build())  # noqa: S314 - our own output


def test_the_description_is_escaped():
    xml = build(description='Coins & <more>')

    assert '<description>Coins &amp; &lt;more&gt;</description>' in xml


def test_an_empty_description_is_refused():
    with pytest.raises(TimweError, match='description'):
        build(description='   ')


def test_an_overlong_description_is_refused():
    with pytest.raises(TimweError, match='255'):
        build(description='x' * 256)


@pytest.mark.parametrize('bad', ['', 'R' * 31])
def test_a_reference_code_outside_one_to_thirty_is_refused(bad):
    with pytest.raises(TimweError, match='referenceCode'):
        build(reference_code=bad)


def test_the_currency_is_sent_as_the_ma_spells_it(settings):
    """The guide promised ISO 4217. TIMWE's own working example sends 'Birr',
    and their gateway accepted it, so the configured spelling goes on the wire
    untouched rather than being corrected into something they refuse."""
    settings.TIMWE_CURRENCY = 'Birr'

    assert '<currency>Birr</currency>' in build()


@pytest.mark.parametrize('bad', ['', 'ET B', 'ETB1', 'B' * 11])
def test_a_currency_that_is_not_letters_is_refused(settings, bad):
    settings.TIMWE_CURRENCY = bad

    with pytest.raises(TimweConfigurationError):
        build()


def test_the_identifier_can_drop_the_tel_prefix(settings):
    """The guide's field table shows tel:; TIMWE's working example omits it."""
    settings.TIMWE_CHARGE_TEL_PREFIX = False

    assert f'<loc:endUserIdentifier>{MSISDN}</loc:endUserIdentifier>' in build()


def test_charging_can_use_its_own_service_and_code(settings):
    """TIMWE's charge example quotes a different service than their
    subscription notifications, and a charging code the guide calls optional."""
    settings.TIMWE_CHARGE_SERVICE_ID = '30026300007334'
    settings.TIMWE_CHARGE_CODE = '255'

    xml = build()

    assert '<v2:serviceId>30026300007334</v2:serviceId>' in xml
    assert '<code>255</code>' in xml


def test_the_subscription_service_is_used_when_charging_has_no_service_of_its_own(settings):
    settings.TIMWE_CHARGE_SERVICE_ID = ''

    assert f'<v2:serviceId>{settings.TIMWE_SERVICE_ID}</v2:serviceId>' in build()


# ===========================================================================
# The MA's dialect: how the password travels, and whether the endpoint is proven
# ===========================================================================


def test_the_password_is_hashed_and_never_sent_by_default(settings):
    """The guide's rule, and the default: the account password stays here."""
    xml = build()

    assert settings.TIMWE_SP_PASSWORD not in xml
    assert TimweChargeService.build_sp_password('20260910123045') in xml


def test_plain_mode_sends_the_password_as_timwe_s_own_example_does(settings):
    settings.TIMWE_CHARGE_URL = 'https://ma.test/soap-payment-api/ws/x/services/chargeAmount'
    settings.TIMWE_CHARGE_AUTH_MODE = 'plain'

    assert f'<v2:spPassword>{settings.TIMWE_SP_PASSWORD}</v2:spPassword>' in build()


def test_plain_mode_is_refused_over_an_unencrypted_endpoint(settings):
    """Plain mode puts the password in the request; http would publish it."""
    settings.TIMWE_CHARGE_AUTH_MODE = 'plain'  # CONFIG's URL is http

    assert 'must be encrypted' in TimweChargeService.endpoint_problem()
    with pytest.raises(TimweConfigurationError, match='encrypted'):
        build()


def test_an_unknown_password_mode_is_refused(settings):
    settings.TIMWE_CHARGE_AUTH_MODE = 'sha256'

    assert 'TIMWE_CHARGE_AUTH_MODE' in TimweChargeService.endpoint_problem()
    with pytest.raises(TimweConfigurationError, match='TIMWE_CHARGE_AUTH_MODE'):
        build()


def test_the_certificate_is_verified_by_default(settings, user):
    with patch(POST, return_value=reply(SUCCESS_BODY)) as posted:
        TimweChargeService.execute(
            msisdn=MSISDN, amount=1, description='x', reference_code='FSVERIFY1'
        )

    assert posted.call_args.kwargs['verify'] is True


def test_a_certificate_file_is_used_when_one_is_configured(settings):
    settings.TIMWE_CHARGE_CA_BUNDLE = '/etc/ssl/timwe.pem'

    with patch(POST, return_value=reply(SUCCESS_BODY)) as posted:
        TimweChargeService.execute(
            msisdn=MSISDN, amount=1, description='x', reference_code='FSVERIFY2'
        )

    assert posted.call_args.kwargs['verify'] == '/etc/ssl/timwe.pem'


def test_every_unverified_charge_says_so_in_the_log(settings, caplog):
    """An unverified connection proves nothing about who is being paid, so the
    record of the charge says it was sent that way."""
    settings.TIMWE_CHARGE_VERIFY_TLS = False
    caplog.set_level('WARNING')

    with patch(POST, return_value=reply(SUCCESS_BODY)) as posted:
        TimweChargeService.execute(
            msisdn=MSISDN, amount=1, description='x', reference_code='FSVERIFY3'
        )

    assert posted.call_args.kwargs['verify'] is False
    warned = [r for r in caplog.records if r.getMessage() == 'TIMWE_CHARGE_TLS_UNVERIFIED']
    assert len(warned) == 1
    assert warned[0].reference_code == 'FSVERIFY3'


def test_no_password_reaches_the_logs_in_either_mode(settings, caplog):
    settings.TIMWE_CHARGE_URL = 'https://ma.test/soap-payment-api/ws/x/services/chargeAmount'
    settings.TIMWE_CHARGE_AUTH_MODE = 'plain'
    settings.TIMWE_CHARGE_VERIFY_TLS = False
    caplog.set_level('DEBUG')

    with patch(POST, return_value=reply(SUCCESS_BODY)):
        TimweChargeService.execute(
            msisdn=MSISDN, amount=1, description='x', reference_code='FSVERIFY4'
        )

    flat = json.dumps([r.__dict__ for r in caplog.records], default=str)
    assert settings.TIMWE_SP_PASSWORD not in flat


def test_generated_references_fill_the_thirty_character_limit():
    ref = new_reference_code()

    assert len(ref) == 30
    assert ref.startswith('FS')
    assert new_reference_code() != ref


# ===========================================================================
# MSISDN
# ===========================================================================


@pytest.mark.parametrize('given', ['0912345678', '+251912345678', '251912345678', '912345678'])
def test_every_ethiopian_format_reaches_the_ma_with_its_country_code(given):
    """
    The guide requires the country code in OA, FA and endUserIdentifier.

    Previously the client just stripped non-digits, so a local 0912... number
    went out as OA=0912... -- missing the country code the MA needs.
    """
    xml = build(msisdn=given)

    assert f'<v2:OA>{MSISDN}</v2:OA>' in xml
    assert f'<loc:endUserIdentifier>tel:{MSISDN}</loc:endUserIdentifier>' in xml


@pytest.mark.parametrize('bad', ['', 'not-a-number', '12345', '+1 555 010 0000'])
def test_an_unusable_number_is_refused(bad):
    with pytest.raises(TimweError):
        build(msisdn=bad)


def test_the_transaction_stores_the_normalised_number(user):
    with patch(POST, return_value=reply(SUCCESS_BODY)):
        result = charge(user, msisdn='0912345678')

    assert result.transaction.msisdn == MSISDN


# ===========================================================================
# Amount
# ===========================================================================


@pytest.mark.parametrize('amount', [1, 10, '10', Decimal('10'), Decimal('10.00'), 9999])
def test_a_valid_whole_amount_is_accepted(amount):
    assert TimweChargeService.format_amount(amount) == str(int(Decimal(str(amount))))


@pytest.mark.parametrize(
    'amount',
    [
        0,  # a charge of nothing is a caller bug (SVC0002 treats it as blank)
        -1,
        Decimal('10.50'),  # the MA has no decimal point (p.21)
        '9.99',
        10000,  # five characters; the field holds four
        'abc',
        '',
        1.0,  # floats cannot hold money exactly and are refused outright
        True,  # bool is an int subclass
        Decimal('NaN'),
        Decimal('Infinity'),
    ],
)
def test_an_invalid_amount_is_refused(amount):
    with pytest.raises(TimweAmountError):
        TimweChargeService.format_amount(amount)


def test_a_fractional_amount_is_never_rounded():
    """3.50 sent as 3 under-bills; sent as 4 over-bills. Neither is acceptable."""
    with pytest.raises(TimweAmountError, match='fractional'):
        TimweChargeService.format_amount(Decimal('3.50'))


def test_an_invalid_amount_records_nothing(user):
    with pytest.raises(ChargeRefused), patch(POST) as post:
        charge(user, amount=Decimal('2.5'))

    post.assert_not_called()
    assert TimweChargeTransaction.objects.count() == 0


# ===========================================================================
# Response parsing
# ===========================================================================


def test_an_empty_charge_amount_response_is_success():
    """Guide p.22: success is an empty chargeAmountResponse element."""
    assert TimweChargeService._interpret(SUCCESS_BODY)[0] == OUTCOME_SUCCESS


def test_the_ma_code_is_read_from_message_id_not_faultcode():
    """
    Parlay X puts the MA's code in <detail><messageId>.

    faultcode is SOAP's own classification -- soapenv:Server -- and the old
    parser stored "Server" as the error code, losing the SVC/POL code entirely.
    """
    outcome, code, _ = TimweChargeService._interpret(fault_body('SVC0270'))

    assert outcome == OUTCOME_REJECTED
    assert code == 'SVC0270'


def test_an_ma_code_in_faultcode_is_still_read():
    """Some MAs put the code there directly; the existing tests assume so."""
    body = fault_body('ignored', faultcode='SVC0901').replace('<messageId>ignored</messageId>', '')

    assert TimweChargeService._interpret(body)[1] == 'SVC0901'


def test_a_soap_classification_is_never_stored_as_the_code():
    body = fault_body('x', faultcode='soapenv:Server').replace('<messageId>x</messageId>', '')

    outcome, code, _ = TimweChargeService._interpret(body)
    assert outcome == OUTCOME_REJECTED
    assert code is None


@pytest.mark.parametrize(
    'code',
    ['SVC0001', 'SVC0002', 'SVC0901', 'SVC0270', 'POL0910'],
)
def test_every_documented_code_is_recognised(code):
    assert TimweChargeService._interpret(fault_body(code))[1] == code


def test_xml_without_a_charge_response_is_not_a_success():
    """
    A proxy's XML error page is well-formed and has no Fault.

    The old rule -- no Fault means success -- would have credited coins for it.
    """
    body = '<html><body><h1>Gateway maintenance</h1></body></html>'

    assert TimweChargeService._interpret(body)[0] == OUTCOME_UNKNOWN


@pytest.mark.parametrize('body', ['', '   ', 'not xml <', '<unclosed>'])
def test_an_unreadable_reply_is_unknown_not_rejected(body):
    """We cannot tell what happened, so this must not claim nothing was charged."""
    assert TimweChargeService._interpret(body)[0] == OUTCOME_UNKNOWN


# ===========================================================================
# Transport classification
# ===========================================================================


def run(**post_kwargs):
    with patch(POST, **post_kwargs):
        return TimweChargeService.execute(
            msisdn=MSISDN, amount=10, description='d', reference_code='R1'
        )


def test_success():
    outcome = run(return_value=reply(SUCCESS_BODY))

    assert outcome.outcome == OUTCOME_SUCCESS
    assert outcome.http_status == 200
    assert outcome.duration_ms is not None


def test_a_fault_is_a_definite_rejection():
    outcome = run(return_value=reply(fault_body('SVC0270'), status=500))

    assert outcome.outcome == OUTCOME_REJECTED
    assert outcome.definitely_not_charged


@pytest.mark.parametrize('failure', [refused, dns_failure])
def test_a_connection_that_never_opened_is_unreachable(failure):
    outcome = run(side_effect=failure())

    assert outcome.outcome == OUTCOME_UNREACHABLE
    assert outcome.definitely_not_charged


def test_a_connect_timeout_is_unreachable_not_ambiguous():
    """ConnectTimeout subclasses Timeout too; it must not be read as a read timeout."""
    outcome = run(side_effect=requests.exceptions.ConnectTimeout())

    assert outcome.outcome == OUTCOME_UNREACHABLE


def test_a_read_timeout_is_ambiguous():
    """Sent, no answer: the MA may have charged. Never 'failed'."""
    outcome = run(side_effect=requests.exceptions.ReadTimeout())

    assert outcome.outcome == OUTCOME_TIMEOUT
    assert outcome.is_ambiguous
    assert not outcome.definitely_not_charged


def test_our_timeout_is_not_reported_as_the_mas_svc0001():
    """
    The old client mapped our read timeout to SVC0001.

    SVC0001 is the MA's own code for its internal timeout, a definite fault.
    Ours is ambiguous. Conflating them loses exactly the distinction that
    decides whether a retry is safe.
    """
    outcome = run(side_effect=requests.exceptions.ReadTimeout())

    assert outcome.error_code is None


def test_a_reset_after_sending_is_ambiguous():
    outcome = run(side_effect=reset_after_send())

    assert outcome.outcome == OUTCOME_UNKNOWN
    assert outcome.is_ambiguous


def test_a_4xx_without_soap_is_a_definite_non_charge():
    """A wrong path never reached the charge handler."""
    outcome = run(return_value=reply('Not Found', status=404))

    assert outcome.outcome == OUTCOME_REJECTED
    assert outcome.http_status == 404


def test_a_5xx_without_a_fault_is_ambiguous():
    """The server may have got partway into the charge."""
    outcome = run(return_value=reply('Internal Server Error', status=502))

    assert outcome.outcome == OUTCOME_UNKNOWN


def test_a_success_body_under_an_error_status_is_not_trusted():
    outcome = run(return_value=reply(SUCCESS_BODY, status=500))

    assert outcome.outcome == OUTCOME_UNKNOWN


def test_the_request_carries_connect_and_read_timeouts():
    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        TimweChargeService.execute(msisdn=MSISDN, amount=10, description='d', reference_code='R1')

    connect, read = post.call_args.kwargs['timeout']
    assert read == 60
    assert connect < read


def test_it_posts_soap_to_the_configured_endpoint():
    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        TimweChargeService.execute(msisdn=MSISDN, amount=10, description='d', reference_code='R1')

    assert post.call_args.args[0] == CONFIG['TIMWE_CHARGE_URL']
    assert post.call_args.kwargs['headers']['Content-Type'].startswith('text/xml')


# ===========================================================================
# The transaction lifecycle
# ===========================================================================


def test_a_success_is_recorded(user):
    with patch(POST, return_value=reply(SUCCESS_BODY)):
        result = charge(user)

    row = result.transaction
    assert result.succeeded and result.created
    assert row.status == 'success'
    assert row.outcome == OUTCOME_SUCCESS
    assert row.http_status == 200
    assert row.completed_at is not None
    assert row.amount == 10
    assert row.currency == 'ETB'
    assert len(row.reference_code) == 30


def test_the_row_is_pending_while_the_ma_is_thinking(user):
    """Committed before the call, so a crash mid-charge leaves evidence."""
    seen = {}

    def slow_ma(*args, **kwargs):
        seen['status'] = TimweChargeTransaction.objects.get().status
        return reply(SUCCESS_BODY)

    with patch(POST, side_effect=slow_ma):
        charge(user)

    assert seen['status'] == 'pending'


def test_a_rejection_is_recorded_with_its_code(user):
    with patch(POST, return_value=reply(fault_body('SVC0270', 'MDSP charge failed'))):
        result = charge(user)

    row = result.transaction
    assert row.status == 'failed'
    assert row.outcome == OUTCOME_REJECTED
    assert row.error_code == 'SVC0270'
    assert row.retryable is True  # MA-side fault; a new attempt may succeed


def test_a_permanent_rejection_is_not_retryable(user):
    with patch(POST, return_value=reply(fault_body('SVC0901'))):
        result = charge(user)

    assert result.transaction.retryable is False
    assert result.can_retry_with_new_key is False


def test_unreachable_is_recorded_as_a_safe_retry(user):
    with patch(POST, side_effect=refused()):
        result = charge(user)

    row = result.transaction
    assert row.status == 'failed'
    assert row.outcome == OUTCOME_UNREACHABLE
    assert result.can_retry_with_new_key is True


def test_a_timeout_is_recorded_as_timeout_not_failure(user):
    with patch(POST, side_effect=requests.exceptions.ReadTimeout()):
        result = charge(user)

    row = result.transaction
    assert row.status == 'timeout'
    assert row.status != 'failed'
    assert result.is_ambiguous
    assert result.can_retry_with_new_key is False


def test_a_crash_inside_the_client_is_ambiguous_not_failed(user):
    """Something of ours broke after the row was committed. Unknown, not failed."""
    with patch(POST, side_effect=RuntimeError('boom')):
        result = charge(user)

    assert result.transaction.status == 'unknown'
    assert result.is_ambiguous


def test_no_secrets_are_stored(user):
    with patch(POST, return_value=reply(fault_body('SVC0901'))):
        row = charge(user).transaction

    stored = json.dumps({f.name: str(getattr(row, f.name)) for f in row._meta.concrete_fields})
    assert 'account-password-for-tests' not in stored
    assert TimweChargeService.build_sp_password('20260910123045') not in stored


# ===========================================================================
# Idempotency
# ===========================================================================


def test_the_same_key_charges_once(user):
    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        first = charge(user, key='tap')
        second = charge(user, key='tap')

    assert post.call_count == 1
    assert first.transaction.pk == second.transaction.pk
    assert second.created is False
    assert TimweChargeTransaction.objects.count() == 1


def test_a_repeat_after_a_timeout_does_not_charge_again(user):
    """The case that costs real money: the client retries an ambiguous charge."""
    with patch(POST, side_effect=requests.exceptions.ReadTimeout()) as post:
        charge(user, key='tap')
        again = charge(user, key='tap')

    assert post.call_count == 1
    assert again.transaction.status == 'timeout'


def test_a_repeat_after_a_failure_does_not_charge_again(user):
    """One row is at most one MA call. A retry takes a new key."""
    with patch(POST, side_effect=refused()) as post:
        charge(user, key='tap')
        charge(user, key='tap')

    assert post.call_count == 1


def test_a_key_reused_for_a_different_charge_is_refused(user):
    with patch(POST, return_value=reply(SUCCESS_BODY)):
        charge(user, key='tap', amount=10)

        with pytest.raises(ChargeRefused, match='different charge'):
            charge(user, key='tap', amount=20)


def test_a_race_on_the_same_key_yields_one_charge(user, monkeypatch):
    """Two requests pass the existence check together; the unique key decides."""
    with patch(POST, return_value=reply(SUCCESS_BODY)):
        winner = charge(user, key='race')

    real_filter = TimweChargeTransaction.objects.filter

    def blind_filter(*args, **kwargs):
        # Simulate losing the race: the existence check sees nothing.
        if kwargs.keys() == {'idempotency_key'}:
            return real_filter(pk=None)
        return real_filter(*args, **kwargs)

    monkeypatch.setattr(TimweChargeTransaction.objects, 'filter', blind_filter)

    with patch(POST) as post:
        loser = charge(user, key='race')

    post.assert_not_called()
    assert loser.transaction.pk == winner.transaction.pk
    assert loser.created is False


def test_a_key_is_required(user):
    with pytest.raises(ChargeRefused, match='idempotency'):
        request_charge(user=user, msisdn=MSISDN, amount=10, description='d', idempotency_key='')


def test_reference_codes_are_unique_per_charge(user):
    with patch(POST, return_value=reply(SUCCESS_BODY)):
        a = charge(user, key='one').transaction
        b = charge(user, key='two').transaction

    assert a.reference_code != b.reference_code


# ===========================================================================
# What the user is told
# ===========================================================================


@pytest.mark.parametrize(
    ('side_effect', 'value', 'needle'),
    [
        (None, reply(SUCCESS_BODY), 'successful'),
        (requests.exceptions.ReadTimeout(), None, 'not be charged twice'),
        (refused(), None, 'not been charged'),
    ],
)
def test_the_user_message(user, side_effect, value, needle):
    with patch(POST, side_effect=side_effect, return_value=value):
        result = charge(user)

    assert needle in user_message(result)


def test_the_mas_own_text_never_reaches_the_user(user):
    leaky = 'Sp password is not accepted! internal-host-10.1.2.3'
    with patch(POST, return_value=reply(fault_body('SVC0901', leaky))):
        result = charge(user)

    assert leaky not in user_message(result)
    assert '10.1.2.3' not in user_message(result)


# ===========================================================================
# The purchase flow
# ===========================================================================


def test_a_successful_purchase_credits_the_package(user, airtime_package):
    from api.models.contest import UserCoinBalance

    with patch(POST, return_value=reply(SUCCESS_BODY)):
        result, coin_tx = purchase_coins_with_airtime(
            user=user, package=airtime_package, idempotency_key='buy-1'
        )

    assert result.succeeded
    assert coin_tx.coins == airtime_package.get_total_coins()
    assert coin_tx.payment_method == 'airtime'
    # Traceable back to the exact charge TIMWE records.
    assert coin_tx.payment_reference == result.transaction.reference_code
    balance = UserCoinBalance.objects.get(user=user)
    assert balance.airtime_purchased_balance == airtime_package.get_total_coins()


def test_the_price_comes_from_the_package(user, airtime_package):
    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        purchase_coins_with_airtime(user=user, package=airtime_package, idempotency_key='buy-1')

    assert '<amount>10</amount>' in post.call_args.kwargs['data'].decode()


def test_the_accounts_own_number_is_charged(user, airtime_package):
    """Never a client-supplied number -- that would let anyone bill anyone."""
    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        purchase_coins_with_airtime(user=user, package=airtime_package, idempotency_key='buy-1')

    assert f'<v2:OA>{MSISDN}</v2:OA>' in post.call_args.kwargs['data'].decode()


def test_a_user_without_a_phone_is_refused_before_charging(airtime_package):
    nobody = User.objects.create_user(username='nophone', password='x')

    with pytest.raises(AirtimePurchaseRefused), patch(POST) as post:
        purchase_coins_with_airtime(user=nobody, package=airtime_package, idempotency_key='k')

    post.assert_not_called()


def test_a_package_at_the_wrong_price_is_refused_before_charging(user):
    """Airtime is permitted only at 10 ETB (common/validators/payment.py)."""
    from django.core.exceptions import ValidationError

    from api.models.contest import CoinPackage

    big, _ = CoinPackage.objects.get_or_create(
        price_etb=Decimal('50'),
        defaults={'name': 'Big', 'coin_amount': 500, 'bonus_coins': 0, 'is_active': True},
    )

    with pytest.raises((ValidationError, Exception)), patch(POST) as post:
        purchase_coins_with_airtime(user=user, package=big, idempotency_key='k')

    post.assert_not_called()
    assert TimweChargeTransaction.objects.count() == 0


def test_an_inactive_package_is_refused(user, airtime_package):
    type(airtime_package).objects.filter(pk=airtime_package.pk).update(is_active=False)
    airtime_package.refresh_from_db()

    with pytest.raises(AirtimePurchaseRefused), patch(POST) as post:
        purchase_coins_with_airtime(user=user, package=airtime_package, idempotency_key='k')

    post.assert_not_called()


@pytest.mark.parametrize(
    'side_effect',
    [requests.exceptions.ReadTimeout(), reset_after_send(), refused()],
)
def test_no_coins_without_a_confirmed_charge(user, airtime_package, side_effect):
    from api.models.contest import CoinTransaction

    with patch(POST, side_effect=side_effect):
        result, coin_tx = purchase_coins_with_airtime(
            user=user, package=airtime_package, idempotency_key='buy-1'
        )

    assert coin_tx is None
    assert not CoinTransaction.objects.filter(user=user, payment_method='airtime').exists()
    assert result.transaction.fulfilled_at is None


def test_a_rejected_charge_credits_nothing(user, airtime_package):
    from api.models.contest import CoinTransaction

    with patch(POST, return_value=reply(fault_body('SVC0270'))):
        _, coin_tx = purchase_coins_with_airtime(
            user=user, package=airtime_package, idempotency_key='buy-1'
        )

    assert coin_tx is None
    assert not CoinTransaction.objects.filter(user=user, payment_method='airtime').exists()


def test_fulfilment_happens_exactly_once(user, airtime_package):
    from api.models.contest import CoinTransaction

    with patch(POST, return_value=reply(SUCCESS_BODY)):
        result, _ = purchase_coins_with_airtime(
            user=user, package=airtime_package, idempotency_key='buy-1'
        )

    assert fulfil_coin_purchase(result.transaction) is None
    assert fulfil_coin_purchase(result.transaction) is None
    assert CoinTransaction.objects.filter(user=user, payment_method='airtime').count() == 1


def test_a_repeated_purchase_credits_once(user, airtime_package):
    from api.models.contest import CoinTransaction

    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        purchase_coins_with_airtime(user=user, package=airtime_package, idempotency_key='buy-1')
        purchase_coins_with_airtime(user=user, package=airtime_package, idempotency_key='buy-1')

    assert post.call_count == 1
    assert CoinTransaction.objects.filter(user=user, payment_method='airtime').count() == 1


def test_a_failed_credit_does_not_mark_the_charge_fulfilled(user, airtime_package):
    """The claim and the credit commit together, or not at all."""
    with patch(POST, return_value=reply(SUCCESS_BODY)):
        result = charge(user, key='buy-1')
    TimweChargeTransaction.objects.filter(pk=result.transaction.pk).update(
        coin_package=airtime_package
    )
    row = TimweChargeTransaction.objects.get(pk=result.transaction.pk)

    with (
        patch(
            'api.models.contest.UserCoinBalance.add_purchased',
            side_effect=RuntimeError('db down'),
        ),
        pytest.raises(RuntimeError),
    ):
        fulfil_coin_purchase(row)

    assert TimweChargeTransaction.objects.get(pk=row.pk).fulfilled_at is None


# ===========================================================================
# The view
# ===========================================================================


@pytest.fixture
def server_keys():
    from infrastructure.keys import key_manager, redis_store

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def buy(server_keys):
    """POST to the real view over its encrypted transport."""
    from api.views.charging import purchase_coins_on_demand
    from common.security.e2e_encryption import decrypt_payload, encrypt_payload, generate_keypair

    client_public, client_private = generate_keypair()

    def _buy(user, body, headers=None):
        envelope = encrypt_payload(
            body, receiver_public_key_b64=server_keys, sender_private_key_b64=client_private
        ).to_dict()
        request = APIRequestFactory().post(
            '/charging/coin-purchase/',
            data=json.dumps(envelope),
            content_type='application/json',
            HTTP_X_CLIENT_PUBLIC_KEY=client_public,
            **(headers or {}),
        )
        force_authenticate(request, user=user)
        response = purchase_coins_on_demand(request)
        response.render()
        payload = json.loads(response.content)
        if 'encrypted' in payload:
            payload = json.loads(
                decrypt_payload(
                    payload['encrypted'],
                    payload['nonce'],
                    server_keys,
                    payload['checksum'],
                    client_private,
                )
            )
        return response.status_code, payload

    return _buy


def test_with_the_flag_off_the_legacy_refusal_is_unchanged(user, airtime_package, buy):
    with patch(POST) as post:
        status_code, body = buy(user, {'package_id': airtime_package.pk})

    assert status_code == 403
    assert body['error'] == (
        'Coin purchase via airtime charging is disabled. '
        'Ethio Telecom SIM cards are only accessible for SMS OTP verification.'
    )
    post.assert_not_called()


def test_with_the_flag_off_the_price_rule_still_applies(user, buy):
    """Enforced before the flag on purpose, so it holds either way."""
    status_code, _ = buy(user, {'price_etb': '50'})

    assert status_code == 400


@override_settings(TIMWE_AIRTIME_PURCHASE_ENABLED=True)
def test_a_purchase_succeeds(user, airtime_package, buy):
    with patch(POST, return_value=reply(SUCCESS_BODY)):
        status_code, body = buy(
            user, {'package_id': airtime_package.pk}, {'HTTP_IDEMPOTENCY_KEY': 'buy-1'}
        )

    assert status_code == 200
    assert body['success'] is True
    assert body['coins_credited'] == airtime_package.get_total_coins()
    assert len(body['reference_code']) == 30


@override_settings(TIMWE_AIRTIME_PURCHASE_ENABLED=True)
def test_the_idempotency_key_is_required(user, airtime_package, buy):
    with patch(POST) as post:
        status_code, body = buy(user, {'package_id': airtime_package.pk})

    assert status_code == 400
    assert body['code'] == 'IDEMPOTENCY_KEY_REQUIRED'
    post.assert_not_called()


@override_settings(TIMWE_AIRTIME_PURCHASE_ENABLED=True)
def test_an_ambiguous_charge_is_202_not_an_error(user, airtime_package, buy):
    """A client that sees an error retries; one that sees 202 waits."""
    with patch(POST, side_effect=requests.exceptions.ReadTimeout()):
        status_code, body = buy(
            user, {'package_id': airtime_package.pk}, {'HTTP_IDEMPOTENCY_KEY': 'buy-1'}
        )

    assert status_code == 202
    assert body['code'] == 'PAYMENT_CONFIRMING'


@override_settings(TIMWE_AIRTIME_PURCHASE_ENABLED=True)
def test_an_unreachable_ma_is_503_and_retryable(user, airtime_package, buy):
    with patch(POST, side_effect=refused()):
        status_code, body = buy(
            user, {'package_id': airtime_package.pk}, {'HTTP_IDEMPOTENCY_KEY': 'buy-1'}
        )

    assert status_code == 503
    assert body['can_retry'] is True


@override_settings(TIMWE_AIRTIME_PURCHASE_ENABLED=True)
def test_a_declined_charge_is_402(user, airtime_package, buy):
    with patch(POST, return_value=reply(fault_body('SVC0270'))):
        status_code, _ = buy(
            user, {'package_id': airtime_package.pk}, {'HTTP_IDEMPOTENCY_KEY': 'buy-1'}
        )

    assert status_code == 402


@override_settings(TIMWE_AIRTIME_PURCHASE_ENABLED=True, TIMWE_CHARGE_URL='')
def test_missing_configuration_is_503_without_naming_settings(user, airtime_package, buy):
    status_code, body = buy(
        user, {'package_id': airtime_package.pk}, {'HTTP_IDEMPOTENCY_KEY': 'buy-1'}
    )

    assert status_code == 503
    assert 'TIMWE_CHARGE_URL' not in json.dumps(body)


@override_settings(TIMWE_AIRTIME_PURCHASE_ENABLED=True)
def test_a_client_supplied_price_and_number_are_ignored(user, airtime_package, buy):
    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        buy(
            user,
            {'package_id': airtime_package.pk, 'msisdn': '251900000000', 'coins': 99999},
            {'HTTP_IDEMPOTENCY_KEY': 'buy-1'},
        )

    sent = post.call_args.kwargs['data'].decode()
    assert '251900000000' not in sent
    assert f'<v2:OA>{MSISDN}</v2:OA>' in sent


def test_the_view_accepts_only_post(user):
    """Charging is never reachable from a read."""
    from api.views.charging import purchase_coins_on_demand

    request = APIRequestFactory().get('/charging/coin-purchase/')
    force_authenticate(request, user=user)

    assert purchase_coins_on_demand(request).status_code == 405


# ===========================================================================
# Logging
# ===========================================================================


def test_no_credential_or_full_number_is_logged(user, caplog):
    with caplog.at_level('DEBUG'), patch(POST, return_value=reply(SUCCESS_BODY)):
        charge(user)

    everything = caplog.text + ' '.join(str(r.__dict__) for r in caplog.records)
    assert 'account-password-for-tests' not in everything
    assert not re.search(r'[0-9a-f]{32}', everything), 'an MD5 digest was logged'
    assert MSISDN not in everything
    assert '25191****678' in everything


def completed_record(caplog):
    return next(r for r in caplog.records if r.getMessage().startswith('TIMWE_CHARGE_COMPLETED'))


def rendered(record):
    """The line as it actually reaches a log, through the real formatter.

    This matters more than the LogRecord. common/middleware/logging.py emits a
    fixed whitelist of extra keys and silently drops the rest, so a detail
    passed in extra={} can be asserted on here and still be invisible in
    production. Rendering it is the only assertion that means anything.
    """
    from common.middleware.logging import JsonFormatter

    return JsonFormatter().format(record)


def test_the_lifecycle_is_logged_with_safe_identifiers(user, caplog):
    with caplog.at_level('INFO'), patch(POST, return_value=reply(SUCCESS_BODY)):
        charge(user)

    completed = completed_record(caplog)
    assert completed.operation == 'timwe_charge'
    assert completed.result == OUTCOME_SUCCESS
    assert completed.duration_ms is not None

    line = rendered(completed)
    assert OUTCOME_SUCCESS in line
    assert '10' in line
    assert 'ETB' in line
    assert '25191****678' in line
    assert MSISDN not in line, 'the full number reached the log'


def test_a_rejection_says_why_in_the_line_itself(user, caplog):
    """Without the code, "rejected" is unactionable.

    This line reported result=rejected and nothing else for every failed
    charge: the MA's error code went into extra={}, which the formatter drops.
    Telling a declined payment from a malformed request meant opening a Django
    shell against production.
    """
    with caplog.at_level('INFO'), patch(POST, return_value=reply(fault_body('SVC0270'))):
        charge(user)

    line = rendered(completed_record(caplog))

    assert 'SVC0270' in line, f'no error code in the log line: {line}'
    assert OUTCOME_REJECTED in line


def test_the_mas_own_text_stays_out_of_the_log(user, caplog):
    """It echoes request fields back, which can include the full MSISDN."""
    with (
        caplog.at_level('INFO'),
        patch(POST, return_value=reply(fault_body('SVC0270', text=f'No such subscriber {MSISDN}'))),
    ):
        charge(user)

    line = rendered(completed_record(caplog))

    assert MSISDN not in line
    assert 'No such subscriber' not in line
    # ...but it is kept where one charge can be investigated.
    assert MSISDN in TimweChargeTransaction.objects.get().error_message


# ===========================================================================
# One service per product
# ===========================================================================
#
# TIMWE provision a price point per product, not per account: 3 Birr daily,
# 20 weekly, 70 monthly, 10 on demand. A charge names the service its product
# belongs to, so a renewal for the weekly plan and a one-off coin purchase are
# different services -- and charging an amount under a service with no price
# point for it is what SVC0901 / INVALID_PRICEPOINT_ID means.
#
# Empty means "use the deployment default", so an environment that has not
# filled SubscriptionTier.service_id in behaves exactly as it did before.


def tier_with_service(service_id, *, duration='weekly', price=20):
    from api.models import SubscriptionTier

    return SubscriptionTier.objects.create(
        name=f'{duration.title()} {service_id or "default"}',
        slug=f'{duration}-{service_id or "default"}',
        duration_type=duration,
        duration_days=None if duration == 'ondemand' else 7,
        price_etb=Decimal(price),
        onevas_code=service_id[-1:] or 'Z',
        spid='300263',
        service_id=service_id,
        product_id=f'P{service_id}',
        is_active=True,
    )


def test_a_charge_names_the_service_it_is_given(user):
    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        request_charge(
            user=user,
            msisdn=MSISDN,
            amount=20,
            description='weekly renewal',
            idempotency_key='svc-weekly',
            service_id='30026300007331',
        )

    assert '<v2:serviceId>30026300007331</v2:serviceId>' in charge_body(post)


def test_no_service_given_falls_back_to_the_configured_one(user, settings):
    """So a deployment that has set nothing keeps working unchanged."""
    settings.TIMWE_CHARGE_SERVICE_ID = '30026300007334'

    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        charge(user)

    assert '<v2:serviceId>30026300007334</v2:serviceId>' in charge_body(post)


def test_the_service_used_is_recorded_on_the_charge(user):
    """Not the configured default -- what this charge actually named."""
    with patch(POST, return_value=reply(SUCCESS_BODY)):
        result = request_charge(
            user=user,
            msisdn=MSISDN,
            amount=20,
            description='weekly renewal',
            idempotency_key='svc-recorded',
            service_id='30026300007331',
        )

    assert result.transaction.service_id == '30026300007331'


def test_a_renewal_charges_under_its_own_tiers_service(user):
    from api.services.subscription_tiers import charging_service_id

    weekly = tier_with_service('30026300007331')

    assert charging_service_id(weekly) == '30026300007331'


def test_a_tier_with_no_service_asks_for_the_default(user):
    from api.services.subscription_tiers import charging_service_id

    plain = tier_with_service('')

    assert charging_service_id(plain) == ''


def test_a_coin_purchase_charges_under_the_ondemand_service(user, airtime_package):
    """10 Birr is the on-demand product, not any subscription's."""
    from api.services.subscription_tiers import ondemand_service_id

    tier_with_service('30026300007334', duration='ondemand', price=10)

    assert ondemand_service_id() == '30026300007334'

    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        purchase_coins_with_airtime(user=user, package=airtime_package, idempotency_key='svc-coins')

    assert '<v2:serviceId>30026300007334</v2:serviceId>' in charge_body(post)


def test_no_ondemand_tier_falls_back_to_the_default(user, airtime_package, settings):
    from api.models import SubscriptionTier
    from api.services.subscription_tiers import ondemand_service_id

    SubscriptionTier.objects.filter(duration_type='ondemand').delete()
    settings.TIMWE_CHARGE_SERVICE_ID = '30026300007334'

    assert ondemand_service_id() == ''

    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        purchase_coins_with_airtime(
            user=user, package=airtime_package, idempotency_key='svc-coins-default'
        )

    assert '<v2:serviceId>30026300007334</v2:serviceId>' in charge_body(post)


def test_two_products_do_not_share_one_service(user):
    """The whole point: each charge names its own product's service."""
    daily = tier_with_service('30026300007330', duration='daily', price=3)
    weekly = tier_with_service('30026300007331')

    from api.services.subscription_tiers import charging_service_id

    assert charging_service_id(daily) != charging_service_id(weekly)


# ===========================================================================
# The charging identifiers, and SVC0901 / INVALID_PRICEPOINT_ID
# ===========================================================================
#
# chargeAmount carries NO price point field. Nothing in this codebase sends
# one, and the guide defines none: TIMWE resolve a price point on their side
# from the serviceId, the amount and the charging code. So when staging saw
#
#     outcome=rejected error_code='SVC0901'
#     error_message='INVALID_PRICEPOINT_ID' http_status=500
#
# the request was well-formed and the credentials were accepted. What is not
# provisioned is the combination TIMWE were asked to bill under.
#
# These pin the three values that make up that combination, so a change to any
# of them is deliberate, and pin that the MA's own code and message survive
# into the transaction rather than being flattened into a generic failure.


def charge_body(post):
    """The SOAP envelope actually sent, as text. It goes out as UTF-8 bytes."""
    sent = post.call_args.kwargs.get('data')
    if sent is None:
        sent = post.call_args.args[1]
    return sent.decode('utf-8') if isinstance(sent, bytes) else sent


def test_the_configured_service_id_is_in_the_request(user, settings):
    settings.TIMWE_CHARGE_SERVICE_ID = '30026300007334'

    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        charge(user)

    assert '<v2:serviceId>30026300007334</v2:serviceId>' in charge_body(post)


def test_charging_falls_back_to_the_subscription_service_id(user, settings):
    """Documented fallback -- and a thing to check when TIMWE reject an id.

    TIMWE's charge example quotes ...7334 where subscriptions carry ...7331.
    If TIMWE_CHARGE_SERVICE_ID is unset, charges go out under the
    subscription service, which is a different thing to be provisioned for.
    """
    settings.TIMWE_CHARGE_SERVICE_ID = ''
    settings.TIMWE_SERVICE_ID = '30026300007331'

    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        charge(user)

    assert '<v2:serviceId>30026300007331</v2:serviceId>' in charge_body(post)


def test_the_configured_charge_code_is_in_the_request(user, settings):
    settings.TIMWE_CHARGE_CODE = '255'

    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        charge(user)

    assert '<code>255</code>' in charge_body(post)


def test_no_charge_code_sends_no_code_element(user, settings):
    """Optional per the guide (p.21): absent, not empty."""
    settings.TIMWE_CHARGE_CODE = ''

    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        charge(user)

    assert '<code>' not in charge_body(post)


def test_the_request_carries_no_price_point_field(user):
    """There is none to carry. Pinned so a guessed one cannot be slipped in.

    If TIMWE ever supply a price point identifier and a field to put it in,
    this test should fail and be rewritten deliberately -- not deleted to make
    room for a value nobody confirmed.
    """
    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        charge(user)

    body = charge_body(post).lower()
    assert 'pricepoint' not in body
    assert 'price_point' not in body


def test_ten_birr_is_sent_as_ten(user, settings):
    """The business rule, unchanged by any of this."""
    settings.TIMWE_CURRENCY = 'Birr'

    with patch(POST, return_value=reply(SUCCESS_BODY)) as post:
        charge(user, amount=10)

    body = charge_body(post)
    assert '<amount>10</amount>' in body
    assert '<currency>Birr</currency>' in body


def test_the_mas_price_point_code_and_message_are_kept(user):
    """The row must say what TIMWE said, not a paraphrase of it."""
    with patch(
        POST, return_value=reply(fault_body('SVC0901', text='INVALID_PRICEPOINT_ID'), status=500)
    ):
        result = charge(user)

    row = result.transaction
    assert row.outcome == OUTCOME_REJECTED
    assert row.error_code == 'SVC0901'
    assert 'INVALID_PRICEPOINT_ID' in row.error_message
    assert row.http_status == 500


def test_an_unprovisioned_price_point_is_not_retried(user):
    """SVC0901 is permanent: retrying cannot provision anything."""
    with patch(POST, return_value=reply(fault_body('SVC0901', text='INVALID_PRICEPOINT_ID'))):
        result = charge(user)

    assert result.transaction.retryable is False


def test_the_subscriber_is_not_told_the_mas_text(user):
    """INVALID_PRICEPOINT_ID is our configuration problem, not theirs."""
    with patch(POST, return_value=reply(fault_body('SVC0901', text='INVALID_PRICEPOINT_ID'))):
        result = charge(user)

    shown = user_message(result)
    assert 'INVALID_PRICEPOINT_ID' not in shown
    assert 'SVC0901' not in shown


def test_the_request_log_names_the_identifiers_a_price_point_comes_from(user, settings, caplog):
    """So INVALID_PRICEPOINT_ID can be diagnosed from the log alone."""
    settings.TIMWE_CHARGE_SERVICE_ID = '30026300007334'
    settings.TIMWE_CHARGE_CODE = '255'

    with caplog.at_level('INFO'), patch(POST, return_value=reply(SUCCESS_BODY)):
        charge(user)

    requested = next(
        r for r in caplog.records if r.getMessage().startswith('TIMWE_CHARGE_REQUESTED')
    )
    line = rendered(requested)

    assert '30026300007334' in line
    assert 'code=255' in line
    assert 'amount=10' in line
    assert '25191****678' in line


def test_the_request_log_carries_no_credentials(user, settings, caplog):
    # 'plain' is the mode staging runs in, and the worst case for this: the
    # account password is inside the envelope being sent. It is refused over
    # http, so the https endpoint goes with it.
    settings.TIMWE_CHARGE_AUTH_MODE = 'plain'
    settings.TIMWE_CHARGE_URL = (
        'https://ma.test:443/soap-payment-api/ws/AmountChargingService/services/chargeAmount'
    )

    with caplog.at_level('INFO'), patch(POST, return_value=reply(SUCCESS_BODY)):
        charge(user)

    everything = ' '.join(rendered(r) for r in caplog.records)

    assert CONFIG['TIMWE_SP_PASSWORD'] not in everything
    assert CONFIG['TIMWE_SP_ID'] not in everything
    assert MSISDN not in everything


def test_a_rejected_price_point_does_not_disturb_idempotency(user):
    """The same key still returns the same row rather than charging again."""
    with patch(POST, return_value=reply(fault_body('SVC0901', text='INVALID_PRICEPOINT_ID'))):
        first = charge(user, key='pricepoint-1')

    with patch(POST, return_value=reply(SUCCESS_BODY)) as second_post:
        second = charge(user, key='pricepoint-1')

    assert second.transaction.pk == first.transaction.pk
    assert TimweChargeTransaction.objects.count() == 1
    second_post.assert_not_called(), 'a replay reached the MA'


def test_a_success_still_completes_after_all_this(user):
    with patch(POST, return_value=reply(SUCCESS_BODY)):
        result = charge(user, key='still-works')

    assert result.transaction.outcome == OUTCOME_SUCCESS
    assert result.transaction.status == 'success'


# Keep the module's reference to UTC honest -- it documents the guide's zone.
assert UTC is not None
assert errors.CHARGE_FAILED == 'SVC0270'


# ===========================================================================
# The staging check command
# ===========================================================================


def run_command(*args):
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command('timwe_charge_check', *args, stdout=out)
    return out.getvalue()


def test_the_check_never_prints_the_password():
    with patch('socket.create_connection'):
        output = run_command()

    assert 'account-password-for-tests' not in output
    assert '000201' not in output  # half of the digest input
    assert 'No charge made' in output


def test_the_check_charges_nothing_by_default(user):
    with patch('socket.create_connection'), patch(POST) as post:
        run_command()

    post.assert_not_called()
    assert TimweChargeTransaction.objects.count() == 0


def test_the_check_fails_when_unconfigured(settings):
    from django.core.management import CommandError

    settings.TIMWE_CHARGE_URL = ''

    with pytest.raises(CommandError, match='Checks failed'):
        run_command()


def test_the_check_reports_an_unreachable_endpoint():
    from django.core.management import CommandError

    with (
        patch('socket.create_connection', side_effect=OSError('refused')),
        pytest.raises(CommandError),
    ):
        run_command()


def test_a_real_charge_requires_confirm(user):
    from django.core.management import CommandError

    with (
        patch('socket.create_connection'),
        patch(POST) as post,
        pytest.raises(CommandError, match='--confirm'),
    ):
        run_command('--charge', '--msisdn', MSISDN, '--amount', '1', '--username', user.username)

    post.assert_not_called()


@pytest.mark.parametrize('missing', ['--msisdn', '--amount', '--username'])
def test_a_real_charge_requires_every_flag(user, missing):
    from django.core.management import CommandError

    flags = {'--msisdn': MSISDN, '--amount': '1', '--username': user.username}
    del flags[missing]
    args = ['--charge', '--confirm'] + [x for pair in flags.items() for x in pair]

    with patch('socket.create_connection'), patch(POST) as post, pytest.raises(CommandError):
        run_command(*args)

    post.assert_not_called()


def test_a_confirmed_charge_is_recorded_and_masked(user):
    with patch('socket.create_connection'), patch(POST, return_value=reply(SUCCESS_BODY)):
        output = run_command(
            '--charge',
            '--msisdn',
            MSISDN,
            '--amount',
            '1',
            '--username',
            user.username,
            '--confirm',
        )

    row = TimweChargeTransaction.objects.get()
    assert row.status == 'success'
    assert row.idempotency_key.startswith('staging-check-')
    assert MSISDN not in output
    assert '25191****678' in output


def test_an_ambiguous_staging_charge_warns_not_to_retry(user):
    with (
        patch('socket.create_connection'),
        patch(POST, side_effect=requests.exceptions.ReadTimeout()),
    ):
        output = run_command(
            '--charge',
            '--msisdn',
            MSISDN,
            '--amount',
            '1',
            '--username',
            user.username,
            '--confirm',
        )

    assert 'do not charge again' in output


# ===========================================================================
# The currency, spelled as TIMWE spell it
# ===========================================================================
#
# Staging is configured TIMWE_CURRENCY='Birr' -- four letters, which is what
# TIMWE's gateway accepted where the guide promised 'ETB', and which
# validate_currency deliberately passes through unchanged rather than
# normalising to ISO 4217. TimweChargeTransaction.currency was varchar(3).
#
# So a 10 ETB airtime purchase validated, reached the INSERT, and raised
# DataError: value too long -- an unhandled 500 on
# POST /charging/coin-purchase/, thrown before anything reached the MA.
#
# Two things had to line up for this to reach staging. CONFIG at the top of
# this file spells the currency 'ETB', so no test ever inserted anything
# longer; and these tests run on SQLite by default, which ignores a CharField's
# width entirely. Staging runs Postgres, which does not.
#
# That makes the two insert tests below weaker than they look: on SQLite they
# would pass against the varchar(3) column too. Run them against Postgres
# (TEST_DB_ENGINE=postgresql, see config/settings/testing.py) to get the real
# assurance. The column-width test underneath is the one that holds either
# way, because it reads max_length rather than trusting the database.


def test_a_charge_records_the_currency_as_configured(user):
    with override_settings(TIMWE_CURRENCY='Birr'), patch(POST, return_value=reply(SUCCESS_BODY)):
        result = charge(user, key='birr-1')

    assert result.transaction.currency == 'Birr'


@pytest.mark.parametrize('spelling', ['ETB', 'Birr', 'A' * 10])
def test_any_accepted_spelling_survives_the_insert(user, spelling):
    with override_settings(TIMWE_CURRENCY=spelling), patch(POST, return_value=reply(SUCCESS_BODY)):
        result = charge(user, key=f'spelling-{spelling}')

    assert result.transaction.currency == spelling


def test_the_columns_hold_every_currency_the_client_accepts():
    """The validator and the columns must agree, whatever is configured.

    SubscriptionPayment is in here because a renewal copies the charge's
    currency into it verbatim, and that row is written *after* the subscriber
    has been charged -- a value that did not fit would lose the record of
    money that had already moved.
    """
    longest = 'A' * 10
    assert CURRENCY_PATTERN.match(longest), 'the client no longer accepts 10 letters'
    assert not CURRENCY_PATTERN.match('A' * 11), 'the client widened past these columns'

    for model in (TimweChargeTransaction, SubscriptionPayment):
        width = model._meta.get_field('currency').max_length
        assert width >= len(longest), f'{model.__name__}.currency holds only {width}'
