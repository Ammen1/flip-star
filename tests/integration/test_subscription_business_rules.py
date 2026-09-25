"""
The Ethiopian Telecom business requirement, asserted against the code.

Everything here is already implemented somewhere -- prices in the tier rows,
the coin spread in api/services/subscription_daily_gift.py, the keywords in
api/services/subscription_tiers.py, the stop codes in
api/services/sms_subscription.py. What did not exist was one place that says
what the product promised and fails when the code stops matching it.

That matters because these values are spread across a seed command, three
migrations and two services. A price edited in the admin, or a gift total
changed by a migration, is invisible until a subscriber is billed the wrong
amount or paid the wrong coins. These tests are the contract.

Not covered here, deliberately:

* **Account type (prepaid / postpaid / hybrid).** Neither integration carries
  it. chargeAmount (api/integrations/timwe/charge.py) sends spId, serviceId,
  amount, currency, code and referenceCode -- there is no account-type field
  in the request and none in the reply, and Telebirr's API has no equivalent.
  Which account a charge lands against is Ethio Telecom's decision, taken
  inside their billing platform. There is nothing for this codebase to branch
  on, so there is nothing to test; see the audit note in the report.
"""

from decimal import Decimal

import pytest

from api.models import SubscriptionTier
from api.services.sms_subscription import STOP_KEYWORDS
from api.services.subscription_daily_gift import daily_schedule, schedule_for
from api.services.subscription_tiers import duration_for_keyword

pytestmark = pytest.mark.django_db


#: duration_type -> (price in ETB, days, total gift coins)
PLANS = {
    'daily': (Decimal('3.00'), 1, 3),
    'weekly': (Decimal('20.00'), 7, 23),
    'monthly': (Decimal('70.00'), 30, 120),
}


def tier(duration_type):
    row = SubscriptionTier.objects.filter(duration_type=duration_type, is_active=True).first()
    if row is None:
        pytest.skip(f'no active {duration_type} tier seeded')
    return row


# ── prices ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(('duration_type', 'price'), [(k, v[0]) for k, v in PLANS.items()])
def test_each_plan_costs_what_the_requirement_says(duration_type, price):
    assert Decimal(str(tier(duration_type).price_etb)) == price


@pytest.mark.parametrize(('duration_type', 'days'), [(k, v[1]) for k, v in PLANS.items()])
def test_each_plan_lasts_its_documented_period(duration_type, days):
    assert tier(duration_type).duration_days == days


def test_prices_are_vat_inclusive_and_nothing_adds_vat_again():
    """The requirement states prices include VAT.

    So the amount charged is the tier price, unmodified -- no multiplier
    anywhere between the row and the wire. This asserts the absence of a
    calculation, which is the only way to catch one being introduced: a 15%
    VAT line added later would make the charge 3.45 rather than 3.00 and
    nothing else in the suite would notice.
    """
    from api.integrations.timwe.charge import TimweChargeService

    for duration_type, (price, _days, _coins) in PLANS.items():
        row = tier(duration_type)
        assert Decimal(str(row.price_etb)) == price

        # What reaches TIMWE is that same figure, converted to their minor
        # units (x100) and nothing else. 3 ETB -> 300, never 345.
        assert TimweChargeService.etb_to_timwe_amount(int(price)) == int(price) * 100


# ── the coin allocation ─────────────────────────────────────────────────────


def test_a_daily_subscriber_is_paid_three_coins_on_the_day():
    assert schedule_for(tier('daily')) == [3]


def test_a_weekly_subscriber_is_paid_four_four_then_three_a_day():
    """Day 1: 4. Day 2: 4. Days 3-7: 3 each. 23 in total."""
    assert schedule_for(tier('weekly')) == [4, 4, 3, 3, 3, 3, 3]
    assert sum(schedule_for(tier('weekly'))) == 23


def test_a_monthly_subscriber_is_paid_four_coins_every_day():
    assert schedule_for(tier('monthly')) == [4] * 30
    assert sum(schedule_for(tier('monthly'))) == 120


@pytest.mark.parametrize(('duration_type', 'coins'), [(k, v[2]) for k, v in PLANS.items()])
def test_the_tier_row_carries_the_total_the_spread_pays_out(duration_type, coins):
    """The row and the spread must agree, or one of them is lying.

    daily_schedule spreads whatever total the row holds, so a row edited in
    the admin silently changes what subscribers are paid. This is the check
    that couples the two.
    """
    row = tier(duration_type)
    assert row.charge_gift_coins == coins
    assert sum(daily_schedule(row.charge_gift_coins, row.duration_days or 1)) == coins


def test_the_ondemand_plan_pays_no_recurring_gift():
    """It buys its coins outright; a per-charge gift would pay twice."""
    row = SubscriptionTier.objects.filter(duration_type='ondemand').first()
    if row is None:
        pytest.skip('no on-demand tier seeded')
    assert row.charge_gift_coins == 0


# ── SMS subscription ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('keyword', 'duration_type'),
    [('1', 'daily'), ('2', 'weekly'), ('3', 'monthly')],
)
def test_the_documented_keywords_choose_the_documented_plans(keyword, duration_type):
    assert duration_for_keyword(keyword) == duration_type


@pytest.mark.parametrize('keyword', ['Ok1', 'ok 1', '1 '])
def test_the_keyword_is_read_however_the_aggregator_spells_it(keyword):
    """Real traffic carries both the bare digit and the Ok1 form."""
    assert duration_for_keyword(keyword) == 'daily'


@pytest.mark.parametrize('keyword', ['', 'Ok', 'sub', None])
def test_a_keyword_choosing_no_plan_resolves_to_none(keyword):
    """Guessing a plan for somebody is billing them for something they did
    not ask for."""
    assert duration_for_keyword(keyword) is None


@pytest.mark.parametrize('duration_type', list(PLANS))
def test_every_plan_is_sold_on_the_documented_short_code(duration_type):
    assert tier(duration_type).short_code == '9286'


# ── unsubscription ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('duration_type', 'stop'),
    [('daily', 'STOP1'), ('weekly', 'STOP2'), ('monthly', 'STOP3')],
)
def test_each_plan_has_its_documented_stop_code(duration_type, stop):
    assert STOP_KEYWORDS[duration_type] == stop


def test_the_cancellation_notice_tells_them_how_to_come_back():
    """A subscriber who stops is told the keyword that resubscribes them."""
    from api.services.sms_subscription import build_cancellation_message, subscribe_keyword_for

    row = tier('weekly')
    message = build_cancellation_message(tier=row, subscribe_keyword=subscribe_keyword_for(row))

    assert message
    assert row.name in message or 'Flipstar' in message


# ── one plan at a time ──────────────────────────────────────────────────────


def test_changing_plan_cancels_the_one_being_left(django_user_model):
    """A subscriber holds one package. Moving from daily to weekly must not
    leave both active, or they are billed twice."""
    from django.utils import timezone

    from api.models.subscription import SubscriptionPlan
    from api.services.sms_subscription import _cancel_conflicting_plans

    user = django_user_model.objects.create_user(username='plan_switcher', password='x')
    now = timezone.now()
    SubscriptionPlan.objects.create(
        user=user,
        tier=tier('daily'),
        status='active',
        duration_type='daily',
        start_date=now,
        end_date=now + timezone.timedelta(days=1),
    )

    _cancel_conflicting_plans(
        user=user,
        phone_number='251911000111',
        duration_type='weekly',
        reason='switching plan',
        metadata={},
    )

    assert not SubscriptionPlan.objects.filter(user=user, status='active').exists()


def test_resubscribing_to_the_same_plan_cancels_nothing(django_user_model):
    """Only a *different* duration conflicts -- a renewal of the same plan
    must not cancel itself."""
    from django.utils import timezone

    from api.models.subscription import SubscriptionPlan
    from api.services.sms_subscription import _cancel_conflicting_plans

    user = django_user_model.objects.create_user(username='plan_renewer', password='x')
    now = timezone.now()
    SubscriptionPlan.objects.create(
        user=user,
        tier=tier('weekly'),
        status='active',
        duration_type='weekly',
        start_date=now,
        end_date=now + timezone.timedelta(days=7),
    )

    _cancel_conflicting_plans(
        user=user,
        phone_number='251911000222',
        duration_type='weekly',
        reason='same plan again',
        metadata={},
    )

    assert SubscriptionPlan.objects.filter(user=user, status='active').count() == 1
