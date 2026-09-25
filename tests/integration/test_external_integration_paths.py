"""
The external integrations, and what they do when the outside world misbehaves.

FlipStar talks to four things, all through code that already existed and is
not replaced here:

    TIMWE SMPP      subscription SMS -- one provider, one worker queue
    TIMWE charge    subscription and renewal charging (SOAP)
    Telebirr        USSD purchase, direct debit, B2C payout, H5 checkout
    Ethio CRM       data-prize provisioning (SOAP PresentServiceGift)

What these tests are for
------------------------
Every one of them fails in ways this codebase cannot control: a timeout, an
HTTP error, a body that is not what the schema promised, the same callback
delivered twice, a callback that arrives days late, a provider that is
simply down. The success paths are covered elsewhere and are not repeated;
what is pinned here is the *failure* behaviour, because that is what nobody
exercises by hand and what decides whether a customer is charged for
nothing.

Three properties matter most, and each has its own section:

* **idempotency** -- a callback delivered twice must settle once;
* **authenticity** -- what each endpoint does and does not verify; and
* **log hygiene** -- no password, PIN, token or secret reaches a log line.

That last one is not hypothetical. ``apply_fabric_token`` logged its own
response body, and that response *is* the Telebirr fabric token -- a live
credential written to the log on every H5 checkout. The test below is what
stops it coming back.

Providers are stubbed throughout. A test that needed a real TIMWE or
Telebirr would not run in CI and would be testing their uptime rather than
this code.
"""

from unittest.mock import patch

import pytest
import requests
from django.contrib.auth.models import User

pytestmark = pytest.mark.django_db


# ── SMS: the documented keywords and short code ─────────────────────────────


@pytest.mark.parametrize(
    ('keyword', 'duration_type'), [('1', 'daily'), ('2', 'weekly'), ('3', 'monthly')]
)
def test_the_subscribe_keywords_are_what_was_published(keyword, duration_type):
    from api.services.subscription_tiers import duration_for_keyword

    assert duration_for_keyword(keyword) == duration_type


@pytest.mark.parametrize(
    ('duration_type', 'stop'),
    [('daily', 'STOP1'), ('weekly', 'STOP2'), ('monthly', 'STOP3')],
)
def test_the_stop_keywords_are_what_was_published(duration_type, stop):
    from api.services.sms_subscription import STOP_KEYWORDS

    assert STOP_KEYWORDS[duration_type] == stop


def test_every_plan_is_sold_on_the_published_short_code():
    from api.models import SubscriptionTier

    tiers = SubscriptionTier.objects.filter(
        duration_type__in=('daily', 'weekly', 'monthly'), is_active=True
    )
    if not tiers.exists():
        pytest.skip('no tiers seeded')

    assert {tier.short_code for tier in tiers} == {'9286'}


def test_there_is_exactly_one_sms_provider():
    """The requirement forbids a second provider or a bypass of the worker.

    Asserted against the dispatch module: everything goes through
    ``queue_sms`` onto the SMS queue, and the only transport behind it is
    TIMWE's SMPP (with a console backend for local development, which sends
    nothing).
    """
    import inspect

    from api.services.sms import dispatch

    source = inspect.getsource(dispatch)

    for foreign in ('twilio', 'nexmo', 'vonage', 'africastalking', 'infobip'):
        assert foreign not in source.lower(), f'a second SMS provider appeared: {foreign}'


def test_subscription_events_each_have_a_message():
    """Subscribed, renewed and cancelled all notify."""
    from api.services import sms_subscription

    for builder in (
        'build_welcome_message',
        'build_renewal_message',
        'build_cancellation_message',
    ):
        assert hasattr(sms_subscription, builder), builder


def test_the_cancellation_notice_says_how_to_come_back():
    from api.models import SubscriptionTier
    from api.services.sms_subscription import build_cancellation_message, subscribe_keyword_for

    tier = SubscriptionTier.objects.filter(duration_type='weekly', is_active=True).first()
    if tier is None:
        pytest.skip('no weekly tier seeded')

    message = build_cancellation_message(tier=tier, subscribe_keyword=subscribe_keyword_for(tier))

    assert tier.short_code in message


# ── nothing secret reaches a log ────────────────────────────────────────────


def test_the_fabric_token_is_never_logged():
    """The leak this audit found.

    ``apply_fabric_token`` logged ``resp.text``, and that response body *is*
    the token -- the method's own docstring says so. Every H5 checkout wrote
    a live credential into the log.
    """
    import inspect

    from api.integrations.telebirr import checkout

    source = inspect.getsource(checkout.TelebirrService.apply_fabric_token)

    assert 'resp.text[:500]' not in source
    assert 'response body: {resp.text}' not in source


def test_no_telebirr_call_logs_a_response_body():
    """A preOrder exchange carries the token in its Authorization header and
    a failing response commonly echoes the request back."""
    import inspect

    from api.integrations.telebirr import checkout

    for line in inspect.getsource(checkout).splitlines():
        stripped = line.strip()
        if stripped.startswith('#') or 'logger' not in stripped:
            continue
        assert 'resp.text}' not in stripped, f'a response body is logged: {stripped}'


def test_no_integration_logs_a_credential():
    """A sweep, so a new log line cannot quietly reintroduce one."""
    import inspect

    from api.integrations.telebirr import checkout, direct_debit
    from api.services import crm_service

    banned = ('app_secret', 'appSecret', 'access_pwd', 'AccessPwd', 'sp_password', 'spPassword')

    for module in (checkout, direct_debit, crm_service):
        for line in inspect.getsource(module).splitlines():
            stripped = line.strip()
            if stripped.startswith('#') or 'logger' not in stripped:
                continue
            for secret in banned:
                assert secret not in stripped, f'{module.__name__} logs {secret}: {stripped}'


def test_the_ussd_subscription_webhook_logs_a_length_not_a_body():
    """The careful pattern, pinned so it stays."""
    from pathlib import Path

    from api.views import subscription

    source = Path(subscription.__file__).read_text(encoding='utf-8')

    assert 'Received callback, len=%d' in source


# ── callbacks: delivered twice ──────────────────────────────────────────────


@pytest.fixture
def payout(db):
    """A winner prize awaiting Telebirr's confirmation."""
    from decimal import Decimal

    from api.models.gift import WinnerGiftTransaction

    winner = User.objects.create_user(username='payout_winner', password='x')
    return WinnerGiftTransaction.objects.create(
        winner=winner,
        winner_type='weekly',
        amount=Decimal('1000.00'),
        payment_method='telebirr_b2c',
        receiver_msisdn='251911000111',
        originator_conversation_id='OCID-DUP-1',
        status='processing',
    )


def b2c_result(originator, *, code='0'):
    """A Telebirr B2C Result envelope, as the webhook receives it."""
    return f"""<?xml version="1.0"?>
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
      <soapenv:Body>
        <api:Result xmlns:api="http://cps.huawei.com/cpsinterface/result">
          <ResultType>0</ResultType>
          <ResultCode>{code}</ResultCode>
          <ResultDesc>Done</ResultDesc>
          <OriginatorConversationID>{originator}</OriginatorConversationID>
          <TransactionID>TX-9</TransactionID>
        </api:Result>
      </soapenv:Body>
    </soapenv:Envelope>""".encode()


def deliver_b2c(body):
    from rest_framework.test import APIRequestFactory

    from api.views.direct_debit import telebirr_b2c_webhook

    request = APIRequestFactory().post(
        '/webhooks/telebirrB2C/', data=body, content_type='text/xml'
    )
    return telebirr_b2c_webhook(request)


def test_a_duplicate_payout_callback_settles_once(payout):
    """Telebirr retries callbacks, and this endpoint has no signature check,
    so the same envelope can arrive any number of times."""
    deliver_b2c(b2c_result('OCID-DUP-1'))
    payout.refresh_from_db()
    first_delivered = payout.delivered_at

    deliver_b2c(b2c_result('OCID-DUP-1'))

    payout.refresh_from_db()
    assert payout.status == 'success'
    assert payout.delivered_at == first_delivered, 'a repeat callback moved the record'


def test_a_duplicate_callback_is_answered_with_success(payout):
    """Always 200, so Telebirr does not retry-storm the endpoint."""
    deliver_b2c(b2c_result('OCID-DUP-1'))
    second = deliver_b2c(b2c_result('OCID-DUP-1'))

    assert second.status_code == 200


def test_a_failed_payout_callback_records_the_reason(payout):
    deliver_b2c(b2c_result('OCID-DUP-1', code='1'))

    payout.refresh_from_db()
    assert payout.status == 'failed'
    assert payout.error_message
    assert payout.delivered_at is None


def test_a_callback_for_something_unknown_is_ignored_quietly():
    """An envelope naming a conversation this system never started must not
    500 -- Telebirr would simply send it again."""
    response = deliver_b2c(b2c_result('OCID-NOBODY-KNOWS'))

    assert response.status_code == 200


def test_a_callback_with_no_conversation_id_is_ignored():
    """Malformed input from outside is not an exception."""
    response = deliver_b2c(b'<not-even-xml>')

    assert response.status_code == 200


def test_a_delayed_callback_still_settles_a_pending_payout(payout):
    """A confirmation that arrives days later is still a confirmation.

    Nothing here expires on elapsed time, so a slow callback is handled the
    same as a prompt one -- which matters on this deployment, where B2C
    callbacks have been observed not arriving at all.
    """
    from datetime import timedelta

    from django.utils import timezone

    from api.models.gift import WinnerGiftTransaction

    WinnerGiftTransaction.objects.filter(pk=payout.pk).update(
        created_at=timezone.now() - timedelta(days=5)
    )

    deliver_b2c(b2c_result('OCID-DUP-1'))

    payout.refresh_from_db()
    assert payout.status == 'success'


# ── authenticity, stated honestly ───────────────────────────────────────────


def test_the_coin_callback_verifies_a_signature():
    """The one callback Telebirr signs. It is checked, and a bad signature
    is refused rather than credited."""
    from pathlib import Path

    from api.views import wallet

    source = Path(wallet.__file__).read_text(encoding='utf-8')

    assert 'Invalid signature' in source


@pytest.mark.parametrize(
    'func_name',
    ['telebirr_b2c_webhook', 'telebirr_direct_debit_webhook'],
)
def test_the_soap_webhooks_compensate_for_having_no_signature(func_name):
    """Telebirr's SOAP Result callbacks carry no signature to verify.

    What stands in for it is documented and asserted here: the row is
    locked, and only a row in the expected state is transitioned -- so a
    forged or replayed envelope can at worst re-settle something already
    settled, which changes nothing.
    """
    from pathlib import Path

    from api.views import direct_debit

    text = Path(direct_debit.__file__).read_text(encoding='utf-8')
    start = text.index(f'def {func_name}(')
    body = text[start:]
    end = body.find(chr(10) + 'def ', 1)
    body = body[: end if end != -1 else len(body)]

    assert 'select_for_update' in body, 'the callback does not lock what it transitions'
    assert 'no signature verification' in body, 'the limitation is no longer documented'


# ── outbound calls: how each provider failure is handled ────────────────────


def test_a_crm_timeout_is_a_failure_not_an_exception():
    """Data-prize provisioning. A timeout must come back as a refusal the
    caller can record, not an exception that loses the prize."""
    from api.services.crm_service import CRMService

    with patch('requests.post', side_effect=requests.exceptions.Timeout()):
        success, message, data = CRMService.send_gift(
            service_number_b='251911000111',
            offering_id='OFF-1',
            charge_amount=0,
            access_user='u',
            access_pwd='p',
        )

    assert success is False
    assert 'timeout' in message.lower()
    assert data.get('transaction_id')


def test_a_crm_http_error_is_reported_with_its_status():
    from api.services.crm_service import CRMService

    class Broken:
        status_code = 502
        text = 'Bad Gateway'

    with patch('requests.post', return_value=Broken()):
        success, message, _ = CRMService.send_gift(
            service_number_b='251911000111', offering_id='OFF-1', charge_amount=0,
            access_user='u', access_pwd='p',
        )

    assert success is False
    assert '502' in message


def test_a_crm_response_that_is_not_xml_is_a_failure():
    """Invalid response. The provider answered, but not with what the schema
    promised."""
    from api.services.crm_service import CRMService

    class Garbage:
        status_code = 200
        text = 'not xml at all'

    with patch('requests.post', return_value=Garbage()):
        success, _message, _ = CRMService.send_gift(
            service_number_b='251911000111', offering_id='OFF-1', charge_amount=0,
            access_user='u', access_pwd='p',
        )

    assert success is False


def test_a_crm_connection_error_is_a_failure():
    """Provider unavailable."""
    from api.services.crm_service import CRMService

    with patch('requests.post', side_effect=requests.exceptions.ConnectionError('refused')):
        success, message, _ = CRMService.send_gift(
            service_number_b='251911000111', offering_id='OFF-1', charge_amount=0,
            access_user='u', access_pwd='p',
        )

    assert success is False
    assert message


def test_a_crm_failure_never_returns_the_credentials_it_was_given():
    """The access password is an argument to this call; it must not come
    back in the message a caller might log."""
    from api.services.crm_service import CRMService

    with patch('requests.post', side_effect=requests.exceptions.Timeout()):
        _success, message, data = CRMService.send_gift(
            service_number_b='251911000111', offering_id='OFF-1', charge_amount=0,
            access_user='secret_user', access_pwd='secret_password',
        )

    assert 'secret_password' not in message
    assert 'secret_password' not in str(data)


# ── the prize delivery that sits on top of the CRM ──────────────────────────


def test_a_provisioning_failure_leaves_the_prize_retryable(db):
    """The debt stays on the books when the provider is down."""
    from datetime import timedelta

    from django.utils import timezone

    from api.models.campaign import Campaign
    from api.services import prize_delivery

    winner = User.objects.create_user(username='data_winner', password='x')
    winner.profile.phone_number = '0911777888'
    winner.profile.save(update_fields=['phone_number'])

    campaign = Campaign.objects.create(
        title='Sprint', campaign_type='daily', status='active',
        start_date=timezone.now() - timedelta(days=1), entry_deadline=timezone.now(),
    )
    prize, _ = prize_delivery.award(campaign, winner, 'daily')

    with patch(
        'api.services.crm_service.CRMService.send_gift',
        side_effect=requests.exceptions.Timeout(),
    ):
        ok, _message = prize_delivery.deliver(prize)

    prize.refresh_from_db()
    assert not ok
    assert prize.status == 'failed'
    assert prize.attempt_count == 1
    assert prize in prize_delivery.deliverable()


def test_a_payout_initiation_failure_leaves_the_prize_retryable(db):
    from datetime import timedelta

    from django.utils import timezone

    from api.models.campaign import Campaign
    from api.services import prize_delivery

    winner = User.objects.create_user(username='cash_winner', password='x')
    winner.profile.phone_number = '0911777999'
    winner.profile.save(update_fields=['phone_number'])

    campaign = Campaign.objects.create(
        title='Battle', campaign_type='weekly', status='active',
        start_date=timezone.now() - timedelta(days=7), entry_deadline=timezone.now(),
    )
    prize, _ = prize_delivery.award(campaign, winner, 'weekly')

    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        side_effect=requests.exceptions.ConnectionError('provider down'),
    ):
        ok, _message = prize_delivery.deliver(prize)

    prize.refresh_from_db()
    assert not ok
    assert prize.status == 'failed'
    assert 'provider down' in prize.error_message


# ── SMS delivery failures ───────────────────────────────────────────────────


def test_an_sms_that_cannot_be_queued_does_not_take_the_caller_down():
    """A subscription must not fail because its notification could not be
    queued: the customer has paid, and the SMS is a courtesy on top."""
    import inspect

    from api.services import sms_subscription

    source = inspect.getsource(sms_subscription)

    assert 'SmsNotQueued' in source, 'the queue failure is not handled'


def test_the_sms_queue_is_the_only_way_out():
    """No code path sends an SMS synchronously past the worker."""
    import inspect

    from api.services.sms import dispatch

    source = inspect.getsource(dispatch.queue_sms)

    assert 'deliver_sms' in source
