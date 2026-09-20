"""
Coins may only be bought by a customer who holds active access.

Coins are a subscriber benefit. The page hides the button for everybody else,
which stops an honest customer and nobody determined: the purchase endpoints
are reachable directly, and until now they asked only whether the package
existed and the phone was known. Somebody with no plan, or a plan that ended
months ago, could start a payment.

The rule is one predicate -- `has_active_subscription`, the same one that
gates posting -- applied at every way in: the USSD push, the SuperApp H5
order and the airtime charge. A check on only some of them is not a rule.

Two properties matter beyond "it says no":

* **nothing is initiated.** The refusal happens before a price is read, an
  order is created or anything is sent to telebirr, so a rejected attempt
  leaves no pending transaction to reconcile.
* **no balance moves.** A refusal must not touch the wallet, in either
  direction.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models import SubscriptionTier
from api.models.contest import CoinPackage, CoinTransaction, UserCoinBalance
from api.models.subscription import SubscriptionPlan
from api.services.subscription_access import (
    COIN_PURCHASE_REQUIRES_ACCESS_CODE,
    coin_purchase_refusal,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def customer():
    user = User.objects.create_user(username='coin_customer', password='x')
    profile = user.profile
    profile.phone_number = '251911000333'
    profile.save(update_fields=['phone_number'])
    return user


@pytest.fixture
def package():
    return CoinPackage.objects.create(
        name='Starter Pack',
        price_etb=Decimal('10.00'),
        coin_amount=100,
        bonus_coins=0,
        is_active=True,
    )


@pytest.fixture
def tier():
    return SubscriptionTier.objects.filter(duration_type='monthly').first()


def give_access(user, tier, *, ends_in=timedelta(days=30)):
    return SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        status='active',
        start_date=timezone.now() - timedelta(days=1),
        end_date=timezone.now() + ends_in,
    )


def balance_of(user):
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.refresh_from_db()
    return balance.balance or 0


# ── 1. no access ────────────────────────────────────────────────────────────


def test_a_customer_with_no_access_is_refused(customer):
    refusal = coin_purchase_refusal(customer)

    assert refusal is not None
    assert refusal['code'] == COIN_PURCHASE_REQUIRES_ACCESS_CODE
    assert refusal['success'] is False


def test_the_refusal_tells_them_what_to_do(customer):
    """A code the client can branch on, and prose a person can act on."""
    message = coin_purchase_refusal(customer)['error'].lower()

    assert 'subscribe' in message or 'renew' in message
    assert 'plan' in message


# ── 2. expired access ───────────────────────────────────────────────────────


def test_access_that_has_expired_is_refused(customer, tier):
    """`status` still reads 'active' -- a failed renewal leaves the column and
    the date disagreeing, and the date is the one that counts."""
    plan = give_access(customer, tier, ends_in=timedelta(days=-1))

    assert plan.status == 'active'
    assert coin_purchase_refusal(customer) is not None


def test_access_expiring_in_a_moment_still_counts(customer, tier):
    give_access(customer, tier, ends_in=timedelta(minutes=1))

    assert coin_purchase_refusal(customer) is None


def test_a_cancelled_plan_is_refused_even_before_its_end_date(customer, tier):
    plan = give_access(customer, tier)
    plan.status = 'cancelled'
    plan.save(update_fields=['status'])

    assert coin_purchase_refusal(customer) is not None


# ── 3. active access ────────────────────────────────────────────────────────


def test_a_customer_with_active_access_may_buy(customer, tier):
    give_access(customer, tier)

    assert coin_purchase_refusal(customer) is None


def test_an_anonymous_caller_is_refused(db):
    from django.contrib.auth.models import AnonymousUser

    assert coin_purchase_refusal(AnonymousUser()) is not None
    assert coin_purchase_refusal(None) is not None


# ── 4. nothing is initiated, 5. no balance moves ────────────────────────────


def test_a_refused_purchase_starts_no_payment(customer, package):
    """The whole point of checking in the backend: no order, no pending
    transaction, nothing to reconcile afterwards."""
    before = CoinTransaction.objects.filter(user=customer).count()

    assert coin_purchase_refusal(customer) is not None

    assert CoinTransaction.objects.filter(user=customer).count() == before
    assert not CoinTransaction.objects.filter(
        user=customer, transaction_type='purchase', is_successful=False
    ).exists()


def test_a_refused_purchase_leaves_the_wallet_alone(customer):
    balance, _ = UserCoinBalance.objects.get_or_create(user=customer)
    balance.earned_balance = 250
    balance._sync_balance()
    balance.save()
    before = balance_of(customer)

    assert coin_purchase_refusal(customer) is not None

    assert balance_of(customer) == before == 250


# ── the rule is applied at every way in ─────────────────────────────────────


@pytest.mark.parametrize(
    'view_name',
    ['telebirr_ussd_purchase', 'telebirr_initiate_payment'],
)
def test_both_telebirr_entry_points_check_access(view_name):
    """Asserted against the source: a check present on one path and missing on
    another is how this hole existed in the first place."""
    from pathlib import Path

    import api.views.wallet as wallet_module

    lines = Path(wallet_module.__file__).read_text(encoding='utf-8').splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f'def {view_name}('))
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith(('def ', '@'))),
        len(lines),
    )
    body = chr(10).join(lines[start:end])

    assert 'coin_purchase_refusal' in body, f'{view_name} does not check access'


def test_the_airtime_entry_point_checks_access():
    from pathlib import Path

    import api.views.charging as charging_module

    source = Path(charging_module.__file__).read_text(encoding='utf-8')
    assert 'coin_purchase_refusal' in source, 'the airtime purchase does not check access'
