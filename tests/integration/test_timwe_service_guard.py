"""Audit findings R-01 and R-02 -- the renewal service guard and Deletion parsing.

R-01. ``_for_this_service`` compared a plan's recorded MA service against the
deployment-wide ``TIMWE_SERVICE_ID``. TIMWE provision a price point per
product, so the four tiers live under four services -- 7331/7332/7333/7334 for
daily/weekly/monthly/ondemand (migration 0143 records these as the live staging
values) -- while that setting names only one of them. Every plan whose tier was
not the configured one was therefore rejected. Measured on production data: 6
daily plans renewable, and all 2 weekly + 1 monthly active subscribers silently
excluded, 17 of 39 plans in total on tiers that could never renew.

The rejection happened in ``due_renewals`` *before* the caller's skip tally, so
``timwe_charge_check --renewals`` reported "1 due, 0 skipped" while discarding
candidates. That is why the defect survived: the diagnostic built to find it
could not see it.

R-02. ``productID`` was unconditionally mandatory, but the MA's real Deletion
notifications carry ``serviceID``/``serviceList`` and no ``productID``. Three
genuine STOPs were answered 1211 and never applied. Accepting them also needs
the tier to resolve from the *service*: a real rejected payload carried
serviceID 7332 (weekly) with keyword ``1``, which reads as daily -- so resolving
by keyword would have cancelled the wrong tier.

Every fixture here is synthetic. No live credential, MSISDN or payload is used.
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone

from api.integrations.timwe.datasync import (
    SyncOrderRelationParseError,
    parse_sync_order_relation,
)
from api.models.subscription import SubscriptionPlan, SubscriptionTier
from api.models.timwe import TimweChargeTransaction
from api.services import subscription_renewal as renewal
from api.services.subscription_tiers import resolve_tier

pytestmark = pytest.mark.django_db

QUEUE = 'api.tasks.subscription_renewal.renew_expired_subscription.delay'

MSISDN = '251900000001'

# The four real staging services, per migration 0143's recorded values.
DAILY_SVC = '30026300007331'
WEEKLY_SVC = '30026300007332'
MONTHLY_SVC = '30026300007333'
ONDEMAND_SVC = '30026300007334'
FOREIGN_SVC = '30026399999999'

TIERS = {
    'daily': (DAILY_SVC, 1, '3.00'),
    'weekly': (WEEKLY_SVC, 7, '20.00'),
    'monthly': (MONTHLY_SVC, 30, '70.00'),
    # OnDemand carries no duration_days: SubscriptionTier.clean refuses it, and
    # _renewable_plans requires duration_days > 0 -- a one-off purchase is never
    # renewed. Included so the guard itself is proven against all four services.
    'ondemand': (ONDEMAND_SVC, None, '10.00'),
}

# Production's own shape: the deployment-wide setting names the DAILY service,
# which is exactly the configuration under which weekly and monthly vanished.
CONFIG = {
    'TIMWE_CHARGE_URL': 'http://ma.test:8080/AmountChargingService/services/AmountCharging',
    'TIMWE_SP_ID': '300263',
    'TIMWE_SP_PASSWORD': 'charging-password-for-tests',
    'TIMWE_SERVICE_ID': DAILY_SVC,
    'TIMWE_CURRENCY': 'ETB',
    'TIMWE_CHARGE_TIMEOUT': 60,
    'TIMWE_CHARGING_ENABLED': True,
    'TIMWE_SUBSCRIPTION_RENEWAL_ENABLED': True,
    'SMS_SHORT_CODE': '9286',
}


@pytest.fixture(autouse=True)
def configured(settings):
    for key, value in CONFIG.items():
        setattr(settings, key, value)
    cache.clear()
    yield settings
    cache.clear()


@pytest.fixture
def user():
    u = User.objects.create_user(username='guard-subscriber', password='x')
    u.profile.phone_number = MSISDN
    u.profile.save(update_fields=['phone_number'])
    return u


def make_tier(duration_type, service_id=None, **overrides):
    default_svc, days, price = TIERS[duration_type]
    fields = {
        'name': f'{duration_type.title()} Guard',
        'slug': f'{duration_type}-guard',
        'onevas_code': duration_type[:9].upper(),
        'duration_type': duration_type,
        'duration_days': days,
        'price_etb': Decimal(price),
        'short_code': '9286',
        'service_id': default_svc if service_id is None else service_id,
        'product_id': f'prod-{duration_type}',
        'is_active': True,
    }
    fields.update(overrides)
    return SubscriptionTier.objects.create(**fields)


def make_plan(user, tier, plan_service=None, **overrides):
    """A short-code plan whose period ran out an hour ago."""
    now = timezone.now()
    fields = {
        'user': user,
        'tier': tier,
        'status': 'active',
        'duration_type': tier.duration_type,
        'payment_method': 'timwe',
        'subscription_source': 'sms',
        # The number TIMWE subscribed on, which _charge_number requires to
        # equal the account's registered one.
        'onevas_phone_number': (
            getattr(getattr(user, 'profile', None), 'phone_number', '') or MSISDN
        ),
        'onevas_subscription_id': str(uuid.uuid4()),
        'start_date': now - timedelta(days=tier.duration_days or 1, hours=1),
        'end_date': now - timedelta(hours=1),
        'metadata': {
            'source': 'timwe',
            'service_id': tier.service_id if plan_service is None else plan_service,
        },
    }
    fields.update(overrides)
    return SubscriptionPlan.objects.create(**fields)


# ── R-01: the guard, per tier ───────────────────────────────────────────────


class TestServiceGuardPerTier:
    @pytest.mark.parametrize('duration_type', ['daily', 'weekly', 'monthly', 'ondemand'])
    def test_plan_matching_its_own_tier_service_is_eligible(self, user, duration_type):
        """Every tier passes, not just the one TIMWE_SERVICE_ID happens to name."""
        plan = make_plan(user, make_tier(duration_type))
        assert renewal._for_this_service(plan) is True

    @pytest.mark.parametrize('duration_type', ['daily', 'weekly', 'monthly', 'ondemand'])
    def test_cross_service_mismatch_is_still_rejected(self, user, duration_type):
        """The guard's original safety intent survives the fix."""
        plan = make_plan(user, make_tier(duration_type), plan_service=FOREIGN_SVC)
        assert renewal._for_this_service(plan) is False

    def test_weekly_plan_carrying_the_daily_service_is_rejected(self, user):
        """A mismatch between two *real* services is a mismatch like any other."""
        plan = make_plan(user, make_tier('weekly'), plan_service=DAILY_SVC)
        assert renewal._for_this_service(plan) is False

    def test_blank_tier_service_still_passes(self, user):
        """'' means 'charge against the deployment default' -- unchanged behaviour."""
        plan = make_plan(user, make_tier('weekly', service_id=''))
        assert renewal._for_this_service(plan) is True

    def test_blank_plan_service_still_passes(self, user):
        """A plan recorded before notifications carried a serviceID has nothing to check."""
        plan = make_plan(user, make_tier('weekly'), plan_service='')
        assert renewal._for_this_service(plan) is True

    def test_unprovisioned_tier_falls_back_to_the_deployment_service(self, user):
        """A tier with no service of its own is still judged, as it always was.

        '' from charging_service_id means "charge against the deployment
        default", so a plan naming some other service is a real mismatch. An
        earlier draft of this fix made that case permissive; the pre-existing
        test_a_plan_for_another_service_is_not_renewed caught it.
        """
        plan = make_plan(user, make_tier('daily', service_id=''), plan_service=FOREIGN_SVC)
        assert renewal._for_this_service(plan) is False

    def test_unprovisioned_tier_accepts_the_deployment_service(self, user):
        plan = make_plan(user, make_tier('daily', service_id=''), plan_service=DAILY_SVC)
        assert renewal._for_this_service(plan) is True

    @pytest.mark.parametrize(
        'deployment_service', [DAILY_SVC, WEEKLY_SVC, MONTHLY_SVC, ONDEMAND_SVC, '']
    )
    def test_guard_no_longer_consults_the_deployment_setting(
        self, user, settings, deployment_service
    ):
        """The regression proper: a weekly plan is eligible whatever the setting says.

        Before the fix this passed only when TIMWE_SERVICE_ID was the weekly
        service, which no deployment sets.
        """
        settings.TIMWE_SERVICE_ID = deployment_service
        plan = make_plan(user, make_tier('weekly'))
        assert renewal._for_this_service(plan) is True


# ── R-01: the exact production failure, end to end ──────────────────────────


class TestProductionConfiguration:
    def test_all_three_subscribed_tiers_reach_the_funnel(self, django_user_model):
        """TIMWE_SERVICE_ID = daily, one subscriber per tier: all three are due.

        This is the configuration that produced "1 due, 0 skipped" while two
        weekly and one monthly subscriber were discarded.
        """
        due = {}
        due_numbers: list[int] = []
        for duration_type in ('daily', 'weekly', 'monthly'):
            u = django_user_model.objects.create_user(username=f'u-{duration_type}', password='x')
            # UserProfile.phone_number is unique -- one number per subscriber.
            u.profile.phone_number = f'2519000001{len(due_numbers)}0'
            due_numbers.append(u.pk)
            u.profile.save(update_fields=['phone_number'])
            make_plan(u, make_tier(duration_type))

        for plan, skip in renewal.due_renewals():
            due[plan.tier.duration_type] = skip

        assert set(due) == {'daily', 'weekly', 'monthly'}
        assert all(skip == '' for skip in due.values()), due

    def test_mismatched_weekly_is_reported_not_silently_dropped(self, user):
        """The drop that hid the bug now arrives with a reason attached."""
        make_plan(user, make_tier('weekly'), plan_service=FOREIGN_SVC)
        results = list(renewal.due_renewals())
        assert len(results) == 1
        assert results[0][1] == renewal.REASON_WRONG_SERVICE


# ── §4: observability of every discarded candidate ──────────────────────────


class TestDiagnosticObservability:
    def test_superseded_plan_is_reported(self, user):
        """A user's older plan is named rather than vanishing from the count."""
        tier = make_tier('daily')
        now = timezone.now()
        make_plan(user, tier, end_date=now - timedelta(hours=1))
        make_plan(user, tier, end_date=now - timedelta(hours=5))
        reasons = sorted(skip for _plan, skip in renewal.due_renewals())
        assert reasons == ['', renewal.REASON_SUPERSEDED]

    def test_command_prints_the_skip_reason_breakdown(self, user):
        out = StringIO()
        make_plan(user, make_tier('weekly'), plan_service=FOREIGN_SVC)
        call_command('timwe_charge_check', '--renewals', stdout=out)
        printed = out.getvalue()
        assert f'skipped_{renewal.REASON_WRONG_SERVICE}=1' in printed
        assert '0 due, 1 skipped' in printed

    def test_command_reports_candidates_by_tier(self, user):
        out = StringIO()
        make_plan(user, make_tier('monthly'))
        call_command('timwe_charge_check', '--renewals', stdout=out)
        assert 'candidates by tier: monthly=1' in out.getvalue()


# ── §9: billing safety -- the fix must not widen what gets charged ──────────


class TestBillingSafety:
    def test_wrong_service_plan_is_never_queued(self, user):
        make_plan(user, make_tier('weekly'), plan_service=FOREIGN_SVC)
        with patch(QUEUE) as delay:
            summary = renewal.sweep_due_renewals()
        delay.assert_not_called()
        assert summary['queued'] == 0
        assert summary['skipped'] == 1

    def test_weekly_plan_is_queued_now(self, user):
        """The revenue the bug was costing: a weekly subscriber reaches charging."""
        make_plan(user, make_tier('weekly'))
        with patch(QUEUE) as delay:
            summary = renewal.sweep_due_renewals()
        assert summary['queued'] == 1
        delay.assert_called_once_with(user.pk)

    def test_two_sweeps_queue_one_renewal_for_the_same_period(self, user):
        """Idempotency is untouched: the queue marker still suppresses the second."""
        make_plan(user, make_tier('weekly'))
        with patch(QUEUE) as delay:
            renewal.sweep_due_renewals()
            renewal.sweep_due_renewals()
        delay.assert_called_once_with(user.pk)

    def test_plan_with_a_live_charge_for_the_period_is_not_a_candidate(self, user):
        """Duplicate-charge protection still excludes a period already in flight."""
        plan = make_plan(user, make_tier('weekly'))
        TimweChargeTransaction.objects.create(
            user=user,
            reference_code='FSguardinflight0000000000001',
            msisdn=MSISDN,
            amount=20,
            currency='ETB',
            purpose=renewal.RENEWAL_PURPOSE,
            subscription=plan,
            renewal_period_end=plan.end_date,
            idempotency_key=renewal.renewal_idempotency_key(plan),
            status='pending',
        )
        assert list(renewal.due_renewals()) == []

    def test_cancelled_plan_is_not_a_candidate(self, user):
        make_plan(user, make_tier('weekly'), status='cancelled')
        assert list(renewal.due_renewals()) == []

    def test_plan_outside_the_renewal_window_is_not_a_candidate(self, user):
        window = renewal.renewal_window()
        make_plan(
            user,
            make_tier('weekly'),
            end_date=timezone.now() - window - timedelta(days=1),
        )
        assert list(renewal.due_renewals()) == []

    def test_still_active_plan_is_not_a_candidate(self, user):
        make_plan(user, make_tier('weekly'), end_date=timezone.now() + timedelta(days=1))
        assert list(renewal.due_renewals()) == []

    def test_idempotency_key_is_stable_per_period(self, user):
        plan = make_plan(user, make_tier('weekly'))
        assert renewal.renewal_idempotency_key(plan) == renewal.renewal_idempotency_key(plan)
        assert renewal.renewal_idempotency_key(plan, 2) != renewal.renewal_idempotency_key(plan)


# ── R-02: Deletion notifications without productID ──────────────────────────


def envelope(*, product_id=None, service_id=None, service_list=None, keyword=None, sp_id='300263'):
    """A syncOrderRelation Deletion envelope, shaped like the MA's real traffic."""
    parts = ['<ns1:userID><ID>251900000009</ID><type>0</type></ns1:userID>']
    if sp_id is not None:
        parts.append(f'<ns1:spID>{sp_id}</ns1:spID>')
    if product_id is not None:
        parts.append(f'<ns1:productID>{product_id}</ns1:productID>')
    if service_id is not None:
        parts.append(f'<ns1:serviceID>{service_id}</ns1:serviceID>')
    if service_list is not None:
        parts.append(f'<ns1:serviceList>{service_list}</ns1:serviceList>')
    parts.append('<ns1:updateType>2</ns1:updateType>')
    parts.append('<ns1:updateTime>20260925162334</ns1:updateTime>')
    parts.append('<ns1:updateDesc>Deletion</ns1:updateDesc>')
    if keyword is not None:
        parts.append(
            '<ns1:extensionInfo><item><key>keyword</key>'
            f'<value>{keyword}</value></item></ns1:extensionInfo>'
        )
    inner = ''.join(parts)
    return (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        '<soapenv:Header/><soapenv:Body>'
        '<ns1:syncOrderRelation '
        'xmlns:ns1="http://www.csapi.org/schema/parlayx/data/sync/v1_0/local">'
        f'{inner}'
        '</ns1:syncOrderRelation></soapenv:Body></soapenv:Envelope>'
    )


class TestDeletionParsing:
    def test_product_id_present_is_unchanged(self):
        rel = parse_sync_order_relation(envelope(product_id='prod-weekly', service_id=WEEKLY_SVC))
        assert rel.product_id == 'prod-weekly'
        assert rel.service_id == WEEKLY_SVC
        assert rel.is_unsubscribe is True

    def test_product_id_absent_with_service_id_is_accepted(self):
        """The shape of the three real rejected STOPs."""
        rel = parse_sync_order_relation(
            envelope(service_id=WEEKLY_SVC, service_list=WEEKLY_SVC, keyword='1')
        )
        assert rel.product_id == ''
        assert rel.service_ids == [WEEKLY_SVC]

    def test_product_id_absent_with_service_list_only_is_accepted(self):
        rel = parse_sync_order_relation(envelope(service_list=MONTHLY_SVC))
        assert rel.service_ids == [MONTHLY_SVC]

    def test_bundle_service_list_yields_every_service(self):
        rel = parse_sync_order_relation(envelope(service_list=f'{DAILY_SVC}|{WEEKLY_SVC}'))
        assert rel.service_ids == [DAILY_SVC, WEEKLY_SVC]

    def test_malformed_service_list_is_rejected(self):
        """Present but naming nothing is not an identifier."""
        with pytest.raises(SyncOrderRelationParseError, match='productID is mandatory'):
            parse_sync_order_relation(envelope(service_list='|||'))

    def test_no_product_and_no_service_is_rejected(self):
        with pytest.raises(SyncOrderRelationParseError, match='productID is mandatory'):
            parse_sync_order_relation(envelope())

    def test_sp_id_is_still_mandatory(self):
        with pytest.raises(SyncOrderRelationParseError, match='spID is mandatory'):
            parse_sync_order_relation(envelope(service_id=WEEKLY_SVC, sp_id=None))


class TestTierResolution:
    def test_service_id_resolves_the_tier_when_product_id_is_absent(self):
        weekly = make_tier('weekly')
        assert resolve_tier(service_id=WEEKLY_SVC) == weekly

    def test_service_id_beats_a_contradicting_keyword(self):
        """The real payload: serviceID weekly, keyword '1' (daily).

        Resolving by keyword would cancel the wrong tier, which is worse than
        refusing the request -- so the exact identifier wins.
        """
        weekly = make_tier('weekly')
        make_tier('daily')
        assert resolve_tier(keyword='1', service_id=WEEKLY_SVC) == weekly

    def test_product_id_still_wins_over_service_id(self):
        daily = make_tier('daily')
        make_tier('weekly')
        assert resolve_tier(product_id='prod-daily', service_id=WEEKLY_SVC) == daily

    def test_keyword_still_resolves_when_no_exact_identifier_is_given(self):
        weekly = make_tier('weekly')
        assert resolve_tier(keyword='Stop2') == weekly

    def test_unknown_service_id_falls_through_to_none(self):
        make_tier('weekly')
        assert resolve_tier(service_id=FOREIGN_SVC) is None


# ── §6: the operator cancellation path ──────────────────────────────────────


class TestOperatorCancellation:
    """The path an authorized operator uses to apply a STOP that was rejected.

    ``sms_subscription.unsubscribe`` is the existing domain function; nothing
    new is introduced for this. It filters on ``status='active'``, which is what
    makes it idempotent, and 'cancelled' is outside RENEWABLE_STATUSES, which is
    what stops a later sweep from charging the subscriber anyway.
    """

    def test_unsubscribe_cancels_the_plan(self, user):
        from api.services import sms_subscription

        plan = make_plan(user, make_tier('weekly'))
        cancelled = sms_subscription.unsubscribe(
            phone_number=user.profile.phone_number,
            duration_type='weekly',
            reason='Operator applying a STOP the MA reported',
            user=user,
        )
        plan.refresh_from_db()
        assert len(cancelled) == 1
        assert plan.status == 'cancelled'

    def test_unsubscribe_is_idempotent(self, user):
        from api.services import sms_subscription

        make_plan(user, make_tier('weekly'))
        kwargs = {
            'phone_number': user.profile.phone_number,
            'duration_type': 'weekly',
            'reason': 'Operator applying a STOP the MA reported',
            'user': user,
        }
        first = sms_subscription.unsubscribe(**kwargs)
        second = sms_subscription.unsubscribe(**kwargs)
        assert len(first) == 1
        assert second == []

    def test_a_cancelled_subscriber_is_never_renewed_afterwards(self, user):
        from api.services import sms_subscription

        make_plan(user, make_tier('weekly'))
        sms_subscription.unsubscribe(
            phone_number=user.profile.phone_number,
            duration_type='weekly',
            reason='Operator applying a STOP the MA reported',
            user=user,
        )
        with patch(QUEUE) as delay:
            summary = renewal.sweep_due_renewals()
        assert list(renewal.due_renewals()) == []
        delay.assert_not_called()
        assert summary['queued'] == 0


# ── §8: the sweep is actually scheduled ─────────────────────────────────────


def test_beat_registers_the_hourly_renewal_sweep():
    """CODE VERIFIED only -- that beat is running is infrastructure, not code."""
    from api.celery import app

    entry = app.conf.beat_schedule['renew-expired-airtime-subscriptions']
    assert entry['task'] == 'api.tasks.subscription_renewal.sweep_expired_subscriptions'
    from celery.schedules import crontab

    # crontab(minute=0) rather than a 3600s interval: an interval is phased
    # from beat's last start, so a restart at :06 pinned every sweep to :06.
    assert entry['schedule'] == crontab(minute=0)
    # Expiring inside the hour is what keeps a backlog after an outage to one
    # sweep rather than one per missed hour.
    assert entry['options']['expires'] < 3600
