"""
Backend-driven renewal of a lapsed TIMWE short-code subscription.

The client never asks for a renewal and supplies none of its terms. When a
short-code subscriber's period has run out, the backend charges their
registered number once through TIMWE chargeAmount and renews only on a
confirmed charge. The expensive mistakes this suite exists to prevent:

* charging twice for one period -- concurrent requests, a retried task, a
  pending or ambiguous attempt followed by another;
* trying again after a refusal before the retry interval is up, or ever after
  an ambiguous attempt -- and charging anyone once the renewal window closes;
* renewing before, or without, a confirmed charge;
* charging anyone the client names, at a price the client names;
* charging while the switches are off.

TIMWE is mocked at the network boundary (``requests.post``), so every test
below runs the real SOAP client, the real charge service and the real renewal.
No test here can reach a real gateway.
"""

import json
import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, patch

import fakeredis
import pytest
import requests
import urllib3.exceptions as U
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from api.models.subscription import (
    SubscriptionHistory,
    SubscriptionPayment,
    SubscriptionPlan,
    SubscriptionTier,
)
from api.models.timwe import TimweChargeTransaction
from api.services import subscription_renewal as renewal
from api.services.timwe_charging import ChargingDisabled, request_charge
from api.tasks.subscription_renewal import renew_expired_subscription
from api.views.core import create_post
from common.security.e2e_encryption import decrypt_payload, generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db

POST = 'api.integrations.timwe.charge.requests.post'
QUEUE = 'api.tasks.subscription_renewal.renew_expired_subscription.delay'

MSISDN = '251912345678'
SERVICE_ID = '30026300007331'

CONFIG = {
    'TIMWE_CHARGE_URL': 'http://ma.test:8080/AmountChargingService/services/AmountCharging',
    'TIMWE_SP_ID': '300263',
    'TIMWE_SP_PASSWORD': 'charging-password-for-tests',
    'TIMWE_SERVICE_ID': SERVICE_ID,
    'TIMWE_CURRENCY': 'ETB',
    'TIMWE_CHARGE_TIMEOUT': 60,
    'TIMWE_CHARGING_ENABLED': True,
    'TIMWE_SUBSCRIPTION_RENEWAL_ENABLED': True,
    'SMS_SHORT_CODE': '9286',
}

SUCCESS_BODY = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <ns1:chargeAmountResponse
      xmlns:ns1="http://www.csapi.org/schema/parlayx/payment/amount_charging/v2_1/local"/>
  </soapenv:Body>
</soapenv:Envelope>"""


def fault_body(code):
    return f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soapenv:Server</faultcode>
      <faultstring>rejected</faultstring>
      <detail>
        <ns2:ServiceException xmlns:ns2="http://www.csapi.org/schema/parlayx/common/v2_1">
          <messageId>{code}</messageId>
          <text>rejected</text>
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


# ─── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def configured(settings):
    for key, value in CONFIG.items():
        setattr(settings, key, value)
    cache.clear()
    yield settings
    cache.clear()


@pytest.fixture
def user():
    u = User.objects.create_user(username='renewer', password='x')
    u.profile.phone_number = MSISDN
    u.profile.save(update_fields=['phone_number'])
    return u


@pytest.fixture
def tier():
    return SubscriptionTier.objects.create(
        name='Daily Premium Renewal',
        slug='daily-renewal-test',
        onevas_code='RNW',
        duration_type='daily',
        duration_days=1,
        price_etb=Decimal('3.00'),
        short_code='9286',
        product_id='10000302850',
        is_active=True,
    )


def lapsed_plan(user, tier, **overrides):
    """A short-code subscription whose day ran out an hour ago."""
    now = timezone.now()
    fields = {
        'user': user,
        'tier': tier,
        'status': 'active',
        'duration_type': tier.duration_type,
        'payment_method': 'timwe',
        'subscription_source': 'sms',
        'onevas_phone_number': MSISDN,
        'onevas_subscription_id': str(uuid.uuid4()),
        'start_date': now - timedelta(days=1, hours=1),
        'end_date': now - timedelta(hours=1),
        # The one-off trial must not be granted again by a renewal.
        'free_trial_days': 1,
        'metadata': {'source': 'timwe', 'service_id': SERVICE_ID},
    }
    fields.update(overrides)
    return SubscriptionPlan.objects.create(**fields)


@pytest.fixture
def plan(user, tier):
    return lapsed_plan(user, tier)


def renewal_rows():
    return TimweChargeTransaction.objects.filter(purpose=renewal.RENEWAL_PURPOSE)


def renew(user, **post_kwargs):
    with patch(POST, **post_kwargs) as posted:
        status = renewal.check_and_renew_subscription(user)
    return status, posted


# ─── which subscriptions are renewable ────────────────────────────────────────


def test_an_active_subscription_is_never_charged(user, tier):
    lapsed_plan(user, tier, end_date=timezone.now() + timedelta(hours=5))

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    assert status.state == renewal.ACTIVE
    posted.assert_not_called()


def test_no_short_code_subscription_is_inactive(user):
    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    assert status.state == renewal.INACTIVE
    posted.assert_not_called()


def test_a_cancelled_subscription_is_never_charged_again(user, tier):
    """The subscriber sent STOP. Charging them would be charging someone who left."""
    lapsed_plan(user, tier, status='cancelled')

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    assert status.state == renewal.INACTIVE
    posted.assert_not_called()


@pytest.mark.parametrize('method', ['telebirr', 'onevas', 'coins'])
def test_only_timwe_short_code_subscriptions_are_renewed(user, tier, method):
    """Those subscribers agreed to be billed somewhere else."""
    lapsed_plan(user, tier, payment_method=method)

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    assert status.state == renewal.INACTIVE
    posted.assert_not_called()


def test_a_plan_on_another_short_code_is_not_renewed(user, tier):
    SubscriptionTier.objects.filter(pk=tier.pk).update(short_code='8000')
    lapsed_plan(user, tier)

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    assert status.state == renewal.INACTIVE
    posted.assert_not_called()


def test_a_plan_for_another_service_is_not_renewed(user, tier):
    lapsed_plan(user, tier, metadata={'source': 'timwe', 'service_id': '99999999'})

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    assert status.state == renewal.INACTIVE
    posted.assert_not_called()


@pytest.mark.parametrize('flag', ['TIMWE_CHARGING_ENABLED', 'TIMWE_SUBSCRIPTION_RENEWAL_ENABLED'])
def test_nothing_is_sent_with_either_switch_off(settings, user, plan, flag):
    setattr(settings, flag, False)

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    assert status.state == renewal.EXPIRED
    assert status.reason == renewal.REASON_DISABLED
    posted.assert_not_called()
    assert not TimweChargeTransaction.objects.exists()


# ─── the charge and the renewal ───────────────────────────────────────────────


def test_an_expired_subscription_is_charged_once_and_renewed(user, tier, plan):
    old_end = plan.end_date

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    assert status.state == renewal.RENEWED
    posted.assert_called_once()

    charge = renewal_rows().get()
    assert charge.status == 'success'
    assert charge.fulfilled_at is not None
    assert charge.subscription_id == plan.pk
    assert charge.renewal_period_end == old_end
    assert int(charge.amount) == 3
    assert charge.msisdn == MSISDN
    assert charge.short_code == '9286'
    assert charge.product_id == '10000302850'
    assert charge.service_id == SERVICE_ID
    assert len(charge.reference_code) <= 30

    plan.refresh_from_db()
    assert plan.is_active
    # now + the tier's one day -- not + the one-off trial day again.
    assert timedelta(hours=23) < plan.end_date - timezone.now() <= timedelta(days=1)

    payment = SubscriptionPayment.objects.get(subscription=plan)
    assert payment.payment_method == 'timwe'
    assert payment.status == 'completed'
    assert payment.onevas_transaction_id == charge.reference_code
    assert SubscriptionHistory.objects.filter(subscription=plan, action='renewed').count() == 1


def test_the_reference_is_saved_before_timwe_is_called(user, plan):
    """If the process dies mid-call, that row is the only evidence."""
    seen = {}

    def while_timwe_is_thinking(*args, **kwargs):
        row = renewal_rows().get()
        seen['status'] = row.status
        sent = kwargs.get('data', b'')
        sent = sent.decode('utf-8') if isinstance(sent, bytes) else str(sent)
        seen['reference_in_request'] = row.reference_code in sent
        return reply(SUCCESS_BODY)

    renew(user, side_effect=while_timwe_is_thinking)

    assert seen == {'status': 'pending', 'reference_in_request': True}


def test_the_price_comes_from_the_tier(user, tier, plan):
    SubscriptionTier.objects.filter(pk=tier.pk).update(price_etb=Decimal('5.00'))

    renew(user, return_value=reply(SUCCESS_BODY))

    assert int(renewal_rows().get().amount) == 5


@pytest.mark.parametrize('stored', ['912345678', '0912345678', '+251912345678', '251912345678'])
def test_the_registered_number_is_normalised(user, plan, stored):
    """9xxxxxxxx and every other Ethiopian form reach TIMWE as 2519xxxxxxxx."""
    user.profile.phone_number = stored
    user.profile.save(update_fields=['phone_number'])

    renew(user, return_value=reply(SUCCESS_BODY))

    assert renewal_rows().get().msisdn == MSISDN


def test_a_number_other_than_the_subscribed_one_is_never_charged(user, tier):
    """The short-code subscription belongs to the number TIMWE subscribed."""
    lapsed_plan(user, tier, onevas_phone_number='251911000000')

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    assert status.reason == renewal.REASON_MSISDN_MISMATCH
    posted.assert_not_called()


def test_an_account_without_a_number_is_not_charged(user, plan):
    user.profile.phone_number = ''
    user.profile.save(update_fields=['phone_number'])

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    assert status.reason == renewal.REASON_NO_MSISDN
    posted.assert_not_called()


# ─── failure, ambiguity, and never charging twice ─────────────────────────────


def test_a_rejected_charge_leaves_the_subscription_expired(user, plan):
    old_end = plan.end_date

    status, _ = renew(user, return_value=reply(fault_body('SVC0270'), status=500))

    assert status.state == renewal.EXPIRED
    assert status.reason == renewal.REASON_FAILED
    plan.refresh_from_db()
    assert plan.end_date == old_end
    assert not plan.is_active
    assert renewal_rows().get().error_code == 'SVC0270'
    assert not SubscriptionPayment.objects.filter(subscription=plan).exists()


def test_a_refused_period_is_not_charged_again_straight_away(user, plan):
    renew(user, return_value=reply(fault_body('SVC0270'), status=500))

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    posted.assert_not_called()
    assert status.reason == renewal.REASON_FAILED
    assert renewal_rows().count() == 1


def test_a_timeout_is_ambiguous_never_renewed_and_never_charged_again(user, plan):
    status, _ = renew(user, side_effect=requests.exceptions.ReadTimeout('no answer'))

    assert status.state == renewal.PAYMENT_PENDING
    assert status.reason == renewal.REASON_AWAITING
    plan.refresh_from_db()
    assert not plan.is_active

    again, posted = renew(user, return_value=reply(SUCCESS_BODY))
    posted.assert_not_called()
    assert again.state == renewal.PAYMENT_PENDING
    assert renewal_rows().get().status == 'timeout'


def test_an_existing_pending_charge_blocks_another(user, plan):
    TimweChargeTransaction.objects.create(
        user=user,
        reference_code='FSpendingalreadyinflight00001',
        msisdn=MSISDN,
        amount=3,
        currency='ETB',
        purpose=renewal.RENEWAL_PURPOSE,
        subscription=plan,
        renewal_period_end=plan.end_date,
        idempotency_key=renewal.renewal_idempotency_key(plan),
        status='pending',
    )

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    posted.assert_not_called()
    assert status.state == renewal.PAYMENT_PENDING


def test_a_request_arriving_mid_charge_does_not_charge_again(user, plan):
    """The race: a second request lands while TIMWE is still answering the first."""
    inner = {}

    def slow_timwe(*args, **kwargs):
        inner['status'] = renewal.check_and_renew_subscription(user)
        return reply(SUCCESS_BODY)

    status, posted = renew(user, side_effect=slow_timwe)

    assert posted.call_count == 1
    assert inner['status'].state == renewal.PAYMENT_PENDING
    assert status.state == renewal.RENEWED
    assert renewal_rows().count() == 1


def test_the_database_allows_one_live_charge_per_renewal_period(user, plan):
    common = {
        'user': user,
        'msisdn': MSISDN,
        'amount': 3,
        'currency': 'ETB',
        'purpose': renewal.RENEWAL_PURPOSE,
        'subscription': plan,
        'renewal_period_end': plan.end_date,
    }
    TimweChargeTransaction.objects.create(
        reference_code='FSfirstattempt000000000000001', idempotency_key='k1', **common
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        TimweChargeTransaction.objects.create(
            reference_code='FSsecondattempt00000000000001', idempotency_key='k2', **common
        )


def test_the_next_period_can_be_renewed(user, plan):
    renew(user, return_value=reply(SUCCESS_BODY))
    plan.refresh_from_db()
    SubscriptionPlan.objects.filter(pk=plan.pk).update(
        end_date=timezone.now() - timedelta(minutes=1)
    )

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    posted.assert_called_once()
    assert status.state == renewal.RENEWED
    assert renewal_rows().count() == 2


def test_a_confirmed_charge_that_fails_to_apply_is_applied_later_without_charging(user, plan):
    """TIMWE has the money; our database hiccupped. Never charge again to recover."""
    with patch.object(SubscriptionPayment.objects, 'create', side_effect=RuntimeError('db down')):
        status, _ = renew(user, return_value=reply(SUCCESS_BODY))

    charge = renewal_rows().get()
    assert charge.status == 'success'
    assert charge.fulfilled_at is None
    assert status.state == renewal.PAYMENT_PENDING
    assert status.reason == renewal.REASON_UNAPPLIED
    plan.refresh_from_db()
    assert not plan.is_active

    again, posted = renew(user, return_value=reply(SUCCESS_BODY))

    posted.assert_not_called()
    assert again.state == renewal.RENEWED
    plan.refresh_from_db()
    assert plan.is_active


# ─── every TIMWE answer, through the whole stack ──────────────────────────────


@pytest.mark.parametrize(
    'post_kwargs,expected',
    [
        ({'return_value': reply(SUCCESS_BODY)}, renewal.RENEWED),
        ({'return_value': reply(fault_body('SVC0270'), status=500)}, renewal.EXPIRED),
        ({'return_value': reply(fault_body('POL0910'), status=200)}, renewal.EXPIRED),
        ({'return_value': reply('<html>Bad Request</html>', status=400)}, renewal.EXPIRED),
        ({'return_value': reply('Internal Server Error', status=500)}, renewal.PAYMENT_PENDING),
        ({'side_effect': requests.exceptions.ReadTimeout('slow')}, renewal.PAYMENT_PENDING),
        ({'side_effect': refused()}, renewal.EXPIRED),
        ({'side_effect': dns_failure()}, renewal.EXPIRED),
        (
            {'side_effect': requests.exceptions.SSLError('handshake failed')},
            renewal.PAYMENT_PENDING,
        ),
        ({'return_value': reply('not xml <')}, renewal.PAYMENT_PENDING),
        (
            {'return_value': reply('<html><body>Gateway maintenance</body></html>')},
            renewal.PAYMENT_PENDING,
        ),
        ({'return_value': reply('')}, renewal.PAYMENT_PENDING),
    ],
    ids=[
        'success',
        'application-error',
        'soap-fault-200',
        'http-400',
        'http-500-no-fault',
        'timeout',
        'refused',
        'dns',
        'tls',
        'malformed-xml',
        'proxy-html',
        'empty',
    ],
)
def test_every_outcome_renews_only_on_a_confirmed_charge(user, plan, post_kwargs, expected):
    status, posted = renew(user, **post_kwargs)

    assert status.state == expected
    plan.refresh_from_db()
    assert plan.is_active is (expected == renewal.RENEWED)
    # Whatever happened, a second request never sends a second charge.
    _, again = renew(user, return_value=reply(SUCCESS_BODY))
    again.assert_not_called()
    assert posted.call_count == 1


# ─── the master switch ────────────────────────────────────────────────────────


def test_the_master_switch_blocks_every_charge(settings, user):
    settings.TIMWE_CHARGING_ENABLED = False

    with patch(POST) as posted, pytest.raises(ChargingDisabled):
        request_charge(user=user, msisdn=MSISDN, amount=3, description='x', idempotency_key='any')

    posted.assert_not_called()
    assert not TimweChargeTransaction.objects.exists()


# ─── the background task ──────────────────────────────────────────────────────


def test_the_task_renews(user, plan):
    with patch(POST, return_value=reply(SUCCESS_BODY)):
        assert renew_expired_subscription(user.pk) == renewal.RENEWED


def test_the_task_redelivered_after_a_crash_does_not_charge_again(user, plan):
    """acks_late redelivers a task whose worker died mid-charge."""
    renew(user, side_effect=requests.exceptions.ReadTimeout('worker killed'))

    with patch(POST) as posted:
        assert renew_expired_subscription(user.pk) == renewal.PAYMENT_PENDING
    posted.assert_not_called()


# ─── /subscription/status/ ────────────────────────────────────────────────────


@pytest.fixture
def server_public_key(db):
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def status_of(server_public_key):
    public, private = generate_keypair()

    def _status(user, query=''):
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(
            reverse('subscription-status') + query, HTTP_X_CLIENT_PUBLIC_KEY=public
        )
        assert response.status_code == 200, response.content[:300]
        raw = json.loads(response.content)
        return json.loads(
            decrypt_payload(
                raw['encrypted'], raw['nonce'], server_public_key, raw['checksum'], private
            )
        )

    return _status


def test_status_queues_a_due_renewal_and_never_waits_for_timwe(user, plan, status_of):
    with patch(POST) as posted, patch(QUEUE) as queued:
        body = status_of(user)

    posted.assert_not_called()
    queued.assert_called_once_with(user.pk)
    assert body['has_subscription'] is False
    assert body['status'] == 'PAYMENT_PENDING'
    assert body['renewal'] == {'state': 'scheduled'}


def test_polling_does_not_queue_the_same_renewal_again(user, plan, status_of):
    with patch(QUEUE) as queued:
        status_of(user)
        status_of(user)
        status_of(user)

    queued.assert_called_once()


def test_an_ambiguous_renewal_reads_pending_never_no_subscription(user, plan, status_of):
    renew(user, side_effect=requests.exceptions.ReadTimeout('slow'))

    with patch(QUEUE) as queued:
        body = status_of(user)

    queued.assert_not_called()
    assert body['status'] == 'PAYMENT_PENDING'
    assert body['renewal'] == {'state': renewal.REASON_AWAITING}


def test_a_failed_renewal_reads_expired(user, plan, status_of):
    renew(user, return_value=reply(fault_body('SVC0270'), status=500))

    with patch(QUEUE) as queued:
        body = status_of(user)

    queued.assert_not_called()
    assert body['status'] == 'EXPIRED'
    assert body['renewal'] == {'state': renewal.REASON_FAILED}


def test_with_renewal_off_status_reads_expired_and_queues_nothing(settings, user, plan, status_of):
    settings.TIMWE_SUBSCRIPTION_RENEWAL_ENABLED = False

    with patch(QUEUE) as queued:
        body = status_of(user)

    queued.assert_not_called()
    assert body['status'] == 'EXPIRED'
    assert body['renewal'] == {'state': renewal.REASON_DISABLED}


def test_status_after_renewal_is_active(user, plan, status_of):
    renew(user, return_value=reply(SUCCESS_BODY))

    body = status_of(user)

    assert body['has_subscription'] is True
    assert body['status'] == 'ACTIVE'


def test_status_without_a_subscription_keeps_its_contract(user, status_of):
    body = status_of(user)

    assert body['has_subscription'] is False
    assert body['subscription'] is None
    assert body['status'] == 'INACTIVE'


def test_the_client_cannot_set_the_terms(user, plan, status_of):
    """Nothing the client sends reaches the charge: not the amount, the number,
    the service, the duration or whose account it is."""
    other = User.objects.create_user(username='victim', password='x')
    query = f'?amount=1&msisdn=0911111111&service_id=1&short_code=1&duration=365&user_id={other.pk}'
    with patch(QUEUE) as queued:
        status_of(user, query)
    queued.assert_called_once_with(user.pk)

    with patch(POST, return_value=reply(SUCCESS_BODY)):
        renew_expired_subscription(user.pk)

    charge = renewal_rows().get()
    assert int(charge.amount) == 3
    assert charge.msisdn == MSISDN
    assert charge.service_id == SERVICE_ID
    assert charge.user_id == user.pk
    plan.refresh_from_db()
    assert plan.end_date - timezone.now() <= timedelta(days=1)


# ─── posting a video: the subscriber-only action ──────────────────────────────


def post_video(user):
    upload = SimpleUploadedFile('clip.mp4', b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 64, 'video/mp4')
    request = APIRequestFactory().post('/posts/', {'caption': 'clip', 'file': upload})
    force_authenticate(request, user=user)
    return create_post(request)


def test_a_lapsed_subscriber_is_renewed_and_allowed_to_post(user, plan):
    with patch(POST, return_value=reply(SUCCESS_BODY)) as posted:
        response = post_video(user)

    posted.assert_called_once()
    assert (response.data or {}).get('code') not in ('SUBSCRIPTION_REQUIRED', 'PAYMENT_PENDING')
    plan.refresh_from_db()
    assert plan.is_active


def test_a_pending_renewal_holds_the_post_with_its_own_code(user, plan):
    with patch(POST, side_effect=requests.exceptions.ReadTimeout('slow')):
        response = post_video(user)

    assert response.status_code == 403
    assert response.data['code'] == 'PAYMENT_PENDING'


def test_with_renewal_off_the_post_gate_is_unchanged(settings, user, plan):
    settings.TIMWE_SUBSCRIPTION_RENEWAL_ENABLED = False

    with patch(POST) as posted:
        response = post_video(user)

    posted.assert_not_called()
    assert response.status_code == 403
    assert response.data['code'] == 'SUBSCRIPTION_REQUIRED'


# ─── reconciliation and logging ───────────────────────────────────────────────


def test_reconcile_lists_what_needs_a_human_and_charges_nothing(user, tier, plan):
    renew(user, side_effect=requests.exceptions.ReadTimeout('slow'))
    ambiguous = renewal_rows().get()

    other_plan = lapsed_plan(user, tier, onevas_subscription_id=str(uuid.uuid4()))
    unapplied = TimweChargeTransaction.objects.create(
        user=user,
        reference_code='FSpaidbutnotappliedyet0000001',
        msisdn=MSISDN,
        amount=3,
        currency='ETB',
        purpose=renewal.RENEWAL_PURPOSE,
        subscription=other_plan,
        renewal_period_end=other_plan.end_date,
        idempotency_key='unapplied',
        status='success',
        completed_at=timezone.now(),
    )

    out = StringIO()
    with patch(POST) as posted:
        call_command('timwe_charge_check', '--reconcile', stdout=out)

    posted.assert_not_called()
    report = out.getvalue()
    assert ambiguous.reference_code in report
    assert 'TIMEOUT' in report
    assert unapplied.reference_code in report
    assert 'PAID, NOT APPLIED' in report
    assert MSISDN not in report


def test_renewal_logs_never_carry_the_full_number_or_secrets(user, plan, caplog):
    caplog.set_level(logging.DEBUG)

    renew(user, return_value=reply(SUCCESS_BODY))

    renewal_records = [
        r for r in caplog.records if 'RENEWAL' in r.getMessage() or 'CHARGE' in r.getMessage()
    ]
    assert renewal_records
    for record in renewal_records:
        flat = json.dumps(record.__dict__, default=str)
        assert MSISDN not in flat
        assert CONFIG['TIMWE_SP_PASSWORD'] not in flat


# ─── a refusal is tried again; an ambiguous charge never is ───────────────────


def age(charge, minutes):
    """Pretend a charge was made this many minutes ago."""
    then = timezone.now() - timedelta(minutes=minutes)
    TimweChargeTransaction.objects.filter(pk=charge.pk).update(created_at=then, completed_at=then)


def refuse(user):
    """One renewal attempt TIMWE refuses: the subscriber is short of airtime."""
    renew(user, return_value=reply(fault_body('SVC0270'), status=500))
    return renewal_rows().order_by('-created_at').first()


def test_a_refused_renewal_is_charged_again_an_hour_later(user, plan):
    """Too little airtime at ten is not the end of it: they may have topped up by eleven."""
    period_end = plan.end_date
    age(refuse(user), 61)

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    posted.assert_called_once()
    assert status.state == renewal.RENEWED
    first, second = renewal_rows().order_by('created_at')
    assert (first.status, second.status) == ('failed', 'success')
    assert first.renewal_period_end == second.renewal_period_end == period_end
    assert second.idempotency_key.endswith(':2')
    assert first.reference_code != second.reference_code
    plan.refresh_from_db()
    assert plan.is_active


def test_a_refusal_is_not_followed_by_another_within_the_hour(user, plan):
    age(refuse(user), 30)

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    posted.assert_not_called()
    assert status.reason == renewal.REASON_FAILED


def test_a_charge_that_never_reached_timwe_is_tried_again(user, plan):
    renew(user, side_effect=refused())
    age(renewal_rows().get(), 61)

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    posted.assert_called_once()
    assert status.state == renewal.RENEWED


@pytest.mark.parametrize(
    'post_kwargs',
    [
        {'side_effect': requests.exceptions.ReadTimeout('slow')},
        {'return_value': reply('Internal Server Error', status=500)},
        {'return_value': reply('')},
    ],
    ids=['timeout', 'http-500-no-fault', 'empty'],
)
def test_an_ambiguous_charge_is_never_tried_again_however_long_ago(user, plan, post_kwargs):
    """The subscriber may have paid. Reconcile; never charge again to find out."""
    renew(user, **post_kwargs)
    age(renewal_rows().get(), 60 * 24 * 3)

    # Not due -- the rule itself, not only the database constraint behind it.
    assert renewal.subscription_status(user).state == renewal.PAYMENT_PENDING
    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    posted.assert_not_called()
    assert status.state == renewal.PAYMENT_PENDING


def test_a_retry_racing_another_never_sends_a_second_charge(user, plan):
    """A second worker past every check is stopped by the database alone."""
    age(refuse(user), 61)
    inner = {}

    def slow_timwe(*args, **kwargs):
        inner['status'] = renewal._renew(user, plan)
        return reply(SUCCESS_BODY)

    status, posted = renew(user, side_effect=slow_timwe)

    assert posted.call_count == 1
    assert inner['status'].state == renewal.PAYMENT_PENDING
    assert status.state == renewal.RENEWED
    assert renewal_rows().count() == 2


def test_the_database_allows_a_retry_after_a_refusal_but_one_live_charge(user, plan):
    common = {
        'user': user,
        'msisdn': MSISDN,
        'amount': 3,
        'currency': 'ETB',
        'purpose': renewal.RENEWAL_PURPOSE,
        'subscription': plan,
        'renewal_period_end': plan.end_date,
    }
    TimweChargeTransaction.objects.create(
        reference_code='FSrefused1', idempotency_key='k1', status='failed', **common
    )
    TimweChargeTransaction.objects.create(
        reference_code='FSretry1', idempotency_key='k2', status='pending', **common
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        TimweChargeTransaction.objects.create(
            reference_code='FSthird1', idempotency_key='k3', status='pending', **common
        )


def test_the_retry_interval_is_configurable(settings, user, plan):
    settings.TIMWE_RENEWAL_RETRY_MINUTES = 180
    charge = refuse(user)

    age(charge, 61)
    _, posted = renew(user, return_value=reply(SUCCESS_BODY))
    posted.assert_not_called()

    age(charge, 181)
    _, posted = renew(user, return_value=reply(SUCCESS_BODY))
    posted.assert_called_once()


def test_retries_are_never_closer_than_ten_minutes(settings, user, plan):
    settings.TIMWE_RENEWAL_RETRY_MINUTES = 0
    age(refuse(user), 5)

    _, posted = renew(user, return_value=reply(SUCCESS_BODY))

    posted.assert_not_called()


def test_no_one_is_charged_once_the_window_has_closed(user, tier):
    """A week after the period ended, the subscriber opts in again; nobody is billed out of the blue."""
    lapsed_plan(user, tier, end_date=timezone.now() - timedelta(days=7, hours=1))

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    assert status.state == renewal.INACTIVE
    posted.assert_not_called()


def test_the_window_is_configurable(settings, user, tier):
    settings.TIMWE_RENEWAL_WINDOW_DAYS = 30
    lapsed_plan(user, tier, end_date=timezone.now() - timedelta(days=8))

    status, posted = renew(user, return_value=reply(SUCCESS_BODY))

    posted.assert_called_once()
    assert status.state == renewal.RENEWED


def test_status_queues_the_retry_once_it_is_due(user, plan, status_of):
    age(refuse(user), 61)

    with patch(POST) as posted, patch(QUEUE) as queued:
        body = status_of(user)

    posted.assert_not_called()
    queued.assert_called_once_with(user.pk)
    assert body['status'] == 'PAYMENT_PENDING'
    assert body['renewal'] == {'state': 'scheduled'}


# ─── the hourly sweep ─────────────────────────────────────────────────────────


def subscriber(name, number, tier, **plan_overrides):
    """Another short-code subscriber, with a plan that ran out an hour ago."""
    account = User.objects.create_user(username=name, password='x')
    account.profile.phone_number = number
    account.profile.save(update_fields=['phone_number'])
    lapsed_plan(account, tier, **{'onevas_phone_number': number, **plan_overrides})
    return account


def sweep():
    with patch(POST) as posted, patch(QUEUE) as queued:
        summary = renewal.sweep_due_renewals()
    posted.assert_not_called()  # the sweep itself never charges
    return summary, sorted(call.args[0] for call in queued.call_args_list)


def test_the_sweep_queues_every_lapsed_airtime_subscriber_and_no_one_else(user, tier, plan):
    second = subscriber('second', '251911111111', tier)
    subscriber('still-active', '251911111112', tier, end_date=timezone.now() + timedelta(hours=5))
    subscriber('telebirr', '251911111113', tier, payment_method='telebirr')
    subscriber('onevas', '251911111114', tier, payment_method='onevas')
    subscriber('stopped', '251911111115', tier, status='cancelled')
    subscriber('long-gone', '251911111116', tier, end_date=timezone.now() - timedelta(days=8))
    renewed_elsewhere = subscriber('renewed-elsewhere', '251911111117', tier)
    lapsed_plan(
        renewed_elsewhere,
        tier,
        payment_method='telebirr',
        onevas_subscription_id=str(uuid.uuid4()),
        end_date=timezone.now() + timedelta(days=3),
    )

    summary, queued = sweep()

    assert queued == sorted([user.pk, second.pk])
    assert summary['queued'] == 2


@pytest.mark.parametrize('flag', ['TIMWE_CHARGING_ENABLED', 'TIMWE_SUBSCRIPTION_RENEWAL_ENABLED'])
def test_the_sweep_does_nothing_with_either_switch_off(settings, user, plan, flag):
    setattr(settings, flag, False)

    summary, queued = sweep()

    assert queued == []
    assert summary['ran'] is False


@pytest.mark.parametrize(
    'overrides',
    [
        {'TIMWE_CHARGE_URL': ''},
        {'TIMWE_SP_PASSWORD': ''},
        {
            'TIMWE_SMPP_HOST': '10.175.206.42',
            'TIMWE_SMPP_PORT': 6986,
            'TIMWE_CHARGE_URL': (
                'http://10.175.206.42:6986/AmountChargingService/services/AmountCharging'
            ),
        },
    ],
    ids=['no-url', 'no-password', 'smpp-address'],
)
def test_the_sweep_does_nothing_until_charging_is_configured(settings, user, plan, overrides):
    for key, value in overrides.items():
        setattr(settings, key, value)

    summary, queued = sweep()

    assert queued == []
    assert summary['ran'] is False


def test_the_sweep_waits_out_a_refusal_then_tries_again(user, plan):
    charge = refuse(user)

    assert sweep()[1] == []
    age(charge, 61)
    assert sweep()[1] == [user.pk]


def test_the_sweep_never_queues_a_period_with_an_ambiguous_charge(user, plan):
    renew(user, side_effect=requests.exceptions.ReadTimeout('slow'))
    age(renewal_rows().get(), 60 * 24 * 3)

    assert sweep()[1] == []


def test_the_sweep_skips_subscribers_it_may_not_charge(user, tier, plan):
    user.profile.phone_number = ''
    user.profile.save(update_fields=['phone_number'])
    subscriber('moved', '251911111118', tier, onevas_phone_number='251911000000')

    summary, queued = sweep()

    assert queued == []
    assert summary['skipped'] == 2


def test_the_sweep_sends_one_charge_while_every_recent_one_failed_on_our_side(user, tier, plan):
    """Wrong credentials would fail for everyone; one request an hour finds out, not hundreds."""
    subscriber('second', '251911111111', tier)
    subscriber('third', '251911111112', tier)
    earlier = subscriber('earlier', '251911111113', tier)
    renew(earlier, return_value=reply(fault_body('SVC0901'), status=500))

    summary, queued = sweep()

    assert summary['canary'] is True
    assert len(queued) == 1


def test_an_ma_that_never_answers_gets_one_charge_an_hour(user, tier, plan):
    """Every unanswered charge is one to reconcile by hand; do not make hundreds."""
    subscriber('second', '251911111111', tier)
    earlier = subscriber('earlier', '251911111113', tier)
    renew(earlier, side_effect=requests.exceptions.ReadTimeout('no answer'))

    summary, queued = sweep()

    assert summary['canary'] is True
    assert len(queued) == 1


def test_the_canary_ends_with_the_first_charge_that_works(user, tier, plan):
    subscriber('second', '251911111111', tier)
    broken = subscriber('broken', '251911111113', tier)
    renew(broken, return_value=reply(fault_body('SVC0901'), status=500))
    working = subscriber('working', '251911111114', tier)
    renew(working, return_value=reply(SUCCESS_BODY))

    summary, queued = sweep()

    assert summary['canary'] is False
    assert len(queued) == 2


def test_a_subscriber_short_of_airtime_does_not_slow_the_sweep(user, tier, plan):
    subscriber('second', '251911111111', tier)
    earlier = subscriber('earlier', '251911111113', tier)
    renew(earlier, return_value=reply(fault_body('SVC0270'), status=500))

    summary, queued = sweep()

    assert summary['canary'] is False
    assert len(queued) == 2


def test_the_sweep_stops_at_its_batch(user, tier, plan):
    subscriber('second', '251911111111', tier)
    subscriber('third', '251911111112', tier)

    with patch(POST), patch(QUEUE) as queued:
        summary = renewal.sweep_due_renewals(limit=2)

    assert summary['queued'] == 2
    assert queued.call_count == 2


def test_the_sweep_charges_and_renews_end_to_end(user, tier, plan):
    second = subscriber('second', '251911111111', tier)

    with (
        patch(POST, return_value=reply(SUCCESS_BODY)) as posted,
        patch(QUEUE, side_effect=renew_expired_subscription),
    ):
        summary = renewal.sweep_due_renewals()
        again = renewal.sweep_due_renewals()

    assert summary['queued'] == 2
    assert again['queued'] == 0
    assert posted.call_count == 2
    for account in (user, second):
        assert SubscriptionPlan.objects.get(user=account).is_active
    assert renewal_rows().filter(status='success').count() == 2


def test_the_sweep_is_scheduled_every_hour():
    from api.celery import app
    from api.tasks import sweep_expired_subscriptions

    entries = [
        entry
        for entry in app.conf.beat_schedule.values()
        if entry['task'] == sweep_expired_subscriptions.name
    ]
    assert len(entries) == 1
    assert entries[0]['schedule'] == 3600.0


def test_the_sweep_task_runs_the_sweep(user, plan):
    from api.tasks import sweep_expired_subscriptions

    with patch(POST), patch(QUEUE) as queued:
        summary = sweep_expired_subscriptions()

    assert summary['queued'] == 1
    queued.assert_called_once_with(user.pk)


def test_the_renewals_preview_charges_and_queues_nothing(user, tier, plan):
    subscriber('moved', '251911111118', tier, onevas_phone_number='251911000000')
    out = StringIO()

    with patch(POST) as posted, patch(QUEUE) as queued:
        call_command('timwe_charge_check', '--renewals', stdout=out)

    posted.assert_not_called()
    queued.assert_not_called()
    report = out.getvalue()
    assert 'DUE' in report
    assert renewal.REASON_MSISDN_MISMATCH in report
    assert '1 due, 1 skipped' in report
    assert MSISDN not in report
