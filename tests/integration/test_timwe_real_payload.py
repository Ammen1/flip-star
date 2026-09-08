"""
The syncOrderRelation the MA actually sends, verbatim.

This envelope was captured from live Ethio Telecom / TIMWE traffic for the SMS
opt-in flow -- a subscriber texts a keyword to the short code, the MA charges
them and then tells us. Everything here runs that exact bytes-on-the-wire
payload rather than a hand-written approximation, because the differences are
the whole point: a `<soapenv:Header/>`, empty `<value/>` elements, a
`serviceList`, and a product id that need not match anything we hold.

Tier resolution mirrors the OneVAS webhook -- product id first, then the
subscriber's SMS keyword. TIMWE and OneVAS front the same products but have
not always quoted the same ids for them.
"""

import pytest
from django.test import override_settings

from api.integrations.timwe.datasync import parse_sync_order_relation
from api.models import SubscriptionPlan, SubscriptionTier, TimweSyncOrderLog

pytestmark = pytest.mark.django_db

URL = '/api/v1/timwe/sync-order-relation'
SOAP_CONTENT_TYPE = 'text/xml; charset=utf-8'

# Captured verbatim from the MA. Do not tidy it.
REAL_ENVELOPE = (
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
    '<soapenv:Header/><soapenv:Body>'
    '<ns1:syncOrderRelation'
    ' xmlns:ns1="http://www.csapi.org/schema/parlayx/data/sync/v1_0/local">'
    '<ns1:userID><ID>251925873168</ID><type>0</type></ns1:userID>'
    '<ns1:spID>015164</ns1:spID>'
    '<ns1:productID>1000030022</ns1:productID>'
    '<ns1:serviceID>015164200007015</ns1:serviceID>'
    '<ns1:serviceList>015164200007015</ns1:serviceList>'
    '<ns1:updateType>1</ns1:updateType>'
    '<ns1:updateTime>20240906140318</ns1:updateTime>'
    '<ns1:updateDesc>Addition</ns1:updateDesc>'
    '<ns1:effectiveTime>20240906140318</ns1:effectiveTime>'
    '<ns1:expiryTime>20240907140318</ns1:expiryTime>'
    '<ns1:extensionInfo>'
    '<item><key>accessCode</key><value>8589</value></item>'
    '<item><key>chargeMode</key><value>18</value></item>'
    '<item><key>MDSPSUBEXPMODE</key><value>1</value></item>'
    '<item><key>objectType</key><value>1</value></item>'
    '<item><key>isFreePeriod</key><value>true</value></item>'
    '<item><key>shortCode</key><value>8589</value></item>'
    '<item><key>payType</key><value>0</value></item>'
    '<item><key>servicePayType</key><value>0</value></item>'
    '<item><key>languageId</key><value>2</value></item>'
    '<item><key>startTime</key><value>20240906140318</value></item>'
    '<item><key>saveNotifyFlag</key><value>1</value></item>'
    '<item><key>messageId</key><value>0-9346-10.244.16.108-436608-1725620598865-cbfc38d5'
    '-b073-4a2b-ae08-dcd5b5fc3ac0</value></item>'
    '<item><key>deviceNameFromTask</key><value>SAG</value></item>'
    '<item><key>transactionID</key><value>0-9346-10.244.16.108-436608-1725620598865-cbfc38d5'
    '-b073-4a2b-ae08-dcd5b5fc3ac0</value></item>'
    '<item><key>orderKey</key><value>138213342</value></item>'
    '<item><key>keyword</key><value>Ok</value></item>'
    '<item><key>cycleEndTime</key><value>20240909000000</value></item>'
    '<item><key>durationOfGracePeriod</key><value>60</value></item>'
    '<item><key>serviceAvailability</key><value>1</value></item>'
    '<item><key>channelID</key><value>2</value></item>'
    '<item><key>TraceUniqueID</key><value>0-9346-10.244.16.108-436608-1725620598865-cbfc38d5'
    '-b073-4a2b-ae08-dcd5b5fc3ac0</value></item>'
    '<item><key>operCode</key><value>en</value></item>'
    '<item><key>rentSuccess</key><value>false</value></item>'
    '<item><key>try</key><value>false</value></item>'
    '<item><key>shortMessage</key><value/></item>'
    '<item><key>correlatorId</key><value/></item>'
    '</ns1:extensionInfo>'
    '</ns1:syncOrderRelation>'
    '</soapenv:Body></soapenv:Envelope>'
)

MSISDN = '251925873168'

#: The same envelope with a productID the seeded catalogue actually holds.
#: Migration 0057 sets daily=10000302850, which is what the live partner log
#: quoted -- so this is the realistic shape for the subscribe path.
SEEDED_ENVELOPE = REAL_ENVELOPE.replace(
    '<ns1:productID>1000030022</ns1:productID>',
    '<ns1:productID>10000302850</ns1:productID>',
)


def post(client, body=REAL_ENVELOPE):
    return client.post(URL, data=body.encode('utf-8'), content_type=SOAP_CONTENT_TYPE)


def make_tier(**overrides):
    defaults = {
        'name': 'Daily Premium',
        'slug': 'daily-premium',
        'duration_type': 'daily',
        'duration_days': 1,
        'price_etb': 5,
        'onevas_code': 'TDAILY',
        'product_id': '1000030022',
    }
    return SubscriptionTier.objects.create(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# It parses
# ---------------------------------------------------------------------------


def test_the_real_envelope_parses():
    relation = parse_sync_order_relation(REAL_ENVELOPE)

    assert relation.msisdn == MSISDN
    assert relation.sp_id == '015164'
    assert relation.product_id == '1000030022'
    assert relation.service_id == '015164200007015'
    assert relation.is_subscribe


def test_a_soap_header_element_is_tolerated():
    """The MA sends <soapenv:Header/>; the hand-written test envelope did not."""
    assert parse_sync_order_relation(REAL_ENVELOPE).update_type == 1


def test_empty_value_elements_do_not_crash():
    """`<value/>` has text None -- .strip() on it would raise."""
    relation = parse_sync_order_relation(REAL_ENVELOPE)

    assert relation.extensions['shortMessage'] == ''
    assert relation.extensions['correlatorId'] == ''


def test_the_extensions_are_captured():
    relation = parse_sync_order_relation(REAL_ENVELOPE)

    assert relation.keyword == 'Ok'
    assert relation.order_key == '138213342'
    assert relation.transaction_id.startswith('0-9346-')
    assert relation.is_free_period is True


def test_the_service_list_is_used_for_subservices():
    relation = parse_sync_order_relation(REAL_ENVELOPE)

    assert relation.service_ids == ['015164200007015']


# ---------------------------------------------------------------------------
# Tier resolution, the OneVAS way
# ---------------------------------------------------------------------------


def test_the_product_id_resolves_when_it_is_configured(client):
    make_tier(product_id='1000030022')

    response = post(client)

    assert response.status_code == 200
    assert b'<ns1:result>0</ns1:result>' in response.content


def test_an_unknown_product_with_no_usable_keyword_is_2032(client):
    """`Ok` names no plan, so there is nothing to fall back to."""
    make_tier(product_id='SOMETHING-ELSE')

    response = post(client)

    assert b'<ns1:result>2032</ns1:result>' in response.content


def test_the_keyword_resolves_when_the_product_id_does_not(client):
    """
    The case that was failing.

    A subscriber texting '1' to the short code has said which plan they want.
    Before this, an id we did not hold meant 2032 and no subscription, however
    clear their intent.
    """
    make_tier(product_id='A-DIFFERENT-ID', duration_type='daily')
    body = REAL_ENVELOPE.replace(
        '<key>keyword</key><value>Ok</value>', '<key>keyword</key><value>1</value>'
    )

    response = post(client, body)

    assert b'<ns1:result>0</ns1:result>' in response.content


@override_settings(TIMWE_INTEGRATION_ENABLED=True)
def test_the_keyword_picks_the_right_duration(client):
    """2 is weekly, not daily -- checked on the plan, not just the result code.

    Uses the catalogue migration 0057 already seeds rather than inventing one,
    so this asks the question against the tiers that actually exist.
    """
    body = REAL_ENVELOPE.replace(
        '<key>keyword</key><value>Ok</value>', '<key>keyword</key><value>2</value>'
    )

    post(client, body)

    assert SubscriptionPlan.objects.get().tier.duration_type == 'weekly'


@override_settings(TIMWE_INTEGRATION_ENABLED=True)
def test_the_seeded_onevas_product_id_resolves_without_any_keyword(client):
    """
    The id from the live partner log, against the seeded catalogue.

    Migration 0057 sets daily=10000302850, weekly=...51, monthly=...52,
    ondemand=...53 -- the OneVAS ids. The MSISDN opt-in captured in the MA log
    quoted 10000302850, so it maps to Daily on product id alone and never
    needed the keyword fallback.
    """
    body = REAL_ENVELOPE.replace(
        '<ns1:productID>1000030022</ns1:productID>',
        '<ns1:productID>10000302850</ns1:productID>',
    )

    response = post(client, body)

    assert b'<ns1:result>0</ns1:result>' in response.content
    assert SubscriptionPlan.objects.get().tier.duration_type == 'daily'


@override_settings(TIMWE_INTEGRATION_ENABLED=True)
def test_a_correct_product_id_is_never_overridden_by_the_keyword(client):
    """
    The id is exact when it is right; the keyword only fills a gap.

    The payload here carries a product id we hold that maps to monthly, and a
    keyword that says daily. The id must win, or a stale keyword could
    downgrade a subscriber's plan.
    """
    make_tier(
        product_id='1000030022',
        duration_type='monthly',
        name='M',
        slug='m',
        onevas_code='TM',
        duration_days=30,
    )
    make_tier(product_id='OTHER', duration_type='daily')
    body = REAL_ENVELOPE.replace(
        '<key>keyword</key><value>Ok</value>', '<key>keyword</key><value>1</value>'
    )

    post(client, body)

    assert SubscriptionPlan.objects.get().tier.duration_type == 'monthly'


# ---------------------------------------------------------------------------
# What the SMS opt-in flow actually produces
# ---------------------------------------------------------------------------


def test_it_is_recorded_but_grants_nothing_while_disabled(client):
    """TIMWE_INTEGRATION_ENABLED is unset in k8s, so this is today's behaviour."""
    make_tier()

    response = post(client)

    assert b'<ns1:result>0</ns1:result>' in response.content
    assert TimweSyncOrderLog.objects.count() == 1
    assert SubscriptionPlan.objects.count() == 0


@override_settings(TIMWE_INTEGRATION_ENABLED=True)
def test_enabling_it_creates_a_subscription_against_the_msisdn(client):
    """
    The SMS-first case: no account exists yet, so the plan carries the number.

    _resolve_user finds nobody, and the plan is keyed on the phone instead --
    which is how it attaches when they later register.
    """
    make_tier()

    response = post(client)

    assert b'<ns1:result>0</ns1:result>' in response.content
    plan = SubscriptionPlan.objects.get()
    assert plan.user is None
    assert plan.onevas_phone_number == MSISDN
    assert plan.subscription_source == 'sms'
    assert plan.status == 'active'


@override_settings(TIMWE_INTEGRATION_ENABLED=True)
def test_a_retried_notification_does_not_subscribe_twice(client):
    """The MA retries anything that is not result 0; transactionID is the key."""
    make_tier()

    post(client)
    post(client)

    assert SubscriptionPlan.objects.count() == 1


# ---------------------------------------------------------------------------
# The rest of the OneVAS business logic, which TIMWE was missing
# ---------------------------------------------------------------------------


@override_settings(TIMWE_INTEGRATION_ENABLED=True)
def test_the_payment_is_recorded(client, monkeypatch):
    """Revenue was not being recorded at all for TIMWE subscribers."""
    from api.models import SubscriptionPayment

    sent = []
    monkeypatch.setattr(
        'api.services.sms_subscription.send_subscription_sms',
        lambda phone, message, tier: sent.append((phone, message)),
    )

    post(client, SEEDED_ENVELOPE)

    payment = SubscriptionPayment.objects.get()
    assert payment.payment_method == 'timwe'
    assert payment.status == 'completed'
    assert payment.duration_type == 'daily'


@override_settings(TIMWE_INTEGRATION_ENABLED=True)
def test_the_subscriber_is_texted_the_otp(client, monkeypatch):
    """
    The point of the SMS channel.

    Without this the subscriber is charged and has no way into the service --
    no link, no OTP. It was missing entirely.
    """
    sent = []
    monkeypatch.setattr(
        'api.services.sms_subscription.send_subscription_sms',
        lambda phone, message, tier: sent.append((phone, message)),
    )

    post(client, SEEDED_ENVELOPE)

    assert len(sent) == 1
    phone, message = sent[0]
    assert phone == MSISDN
    plan = SubscriptionPlan.objects.get()
    assert plan.setup_otp
    assert plan.setup_otp in message
    assert 'STOP1' in message  # how to cancel a daily plan
    assert 'Flipstar' in message


@override_settings(TIMWE_INTEGRATION_ENABLED=True)
def test_a_failed_sms_does_not_fail_the_request(client, monkeypatch):
    """
    A non-zero result makes the MA retry a charge we have already applied.

    So a gateway outage must not turn one subscription into several.
    """

    def boom(*args, **kwargs):
        raise RuntimeError('sms gateway down')

    monkeypatch.setattr('api.services.sms_subscription.send_subscription_sms', boom)

    response = post(client, SEEDED_ENVELOPE)

    assert b'<ns1:result>0</ns1:result>' in response.content
    assert SubscriptionPlan.objects.count() == 1


@override_settings(TIMWE_INTEGRATION_ENABLED=True)
def test_a_first_time_subscriber_gets_a_free_trial_day(client, monkeypatch):
    monkeypatch.setattr('api.services.sms_subscription.send_subscription_sms', lambda *a, **k: None)

    post(client, SEEDED_ENVELOPE)

    assert SubscriptionPlan.objects.get().free_trial_days == 1


@override_settings(TIMWE_INTEGRATION_ENABLED=True)
def test_a_returning_subscriber_gets_no_second_free_trial(client, monkeypatch):
    """Judged on the phone number, so unsubscribing cannot earn a fresh trial."""
    monkeypatch.setattr('api.services.sms_subscription.send_subscription_sms', lambda *a, **k: None)
    SubscriptionPlan.objects.create(
        user=None,
        tier=SubscriptionTier.objects.get(duration_type='daily'),
        duration_type='daily',
        onevas_phone_number=MSISDN,
        status='cancelled',
    )

    post(client, SEEDED_ENVELOPE)

    created = SubscriptionPlan.objects.filter(status='active').get()
    assert created.free_trial_days == 0


@override_settings(TIMWE_INTEGRATION_ENABLED=True)
def test_switching_plan_cancels_the_previous_one(client, monkeypatch):
    """One subscriber, one plan -- otherwise they are billed for both."""
    monkeypatch.setattr('api.services.sms_subscription.send_subscription_sms', lambda *a, **k: None)
    weekly = SubscriptionTier.objects.get(duration_type='weekly')
    SubscriptionPlan.objects.create(
        user=None,
        tier=weekly,
        duration_type='weekly',
        onevas_phone_number=MSISDN,
        status='active',
    )

    post(client, SEEDED_ENVELOPE)

    assert SubscriptionPlan.objects.filter(status='active').count() == 1
    assert SubscriptionPlan.objects.get(status='active').duration_type == 'daily'
    assert SubscriptionPlan.objects.get(duration_type='weekly').status == 'cancelled'
