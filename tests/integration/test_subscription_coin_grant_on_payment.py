"""
Coin grant on subscription payment confirmation.

When a subscription payment succeeds (Telebirr one-time or USSD push), the
customer must immediately receive the coins configured for the purchased tier:
- bonus_coins (from SubscriptionTier) via SubscriptionPlan.activate()
- charge_gift_coins (from SubscriptionTier) via grant_for_payment() signal

Both must be granted atomically with the payment confirmation, never by a
daily job, and exactly once even if the webhook is delivered multiple times.
"""

import json
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.utils import timezone

from api.models.contest import UserCoinBalance, CoinTransaction
from api.models.subscription import (
    SubscriptionPayment,
    SubscriptionPlan,
    SubscriptionTier,
)
from api.models.wallet import WalletConfig
from api.views.subscription import (
    _activate_ussd_subscription_payment,
    telebirr_one_time_callback,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

_tier_seq = 0


@pytest.fixture(autouse=True)
def disable_welcome_bonus():
    """Disable welcome bonus for all tests to ensure clean balance assertions."""
    config = WalletConfig.get_config()
    config.welcome_bonus = 0
    config.save()


def make_tier(bonus_coins=0, charge_gift_coins=0, duration_type='monthly', duration_days=30, price_etb=100):
    global _tier_seq
    _tier_seq += 1
    n = _tier_seq
    return SubscriptionTier.objects.create(
        name=f'TestTier{n}',
        slug=f'test-tier-{n}',
        duration_type=duration_type,
        duration_days=duration_days,
        price_etb=price_etb,
        bonus_coins=bonus_coins,
        charge_gift_coins=charge_gift_coins,
        onevas_code=f'T{n}',
        spid='SP1',
        service_id='SV1',
    )


def make_user(username=None):
    if username is None:
        global _tier_seq
        _tier_seq += 1
        username = f'testuser{_tier_seq}'
    return User.objects.create_user(username=username, password='123456')


def bonus_balance(user):
    try:
        return UserCoinBalance.objects.get(user=user).bonus_balance
    except UserCoinBalance.DoesNotExist:
        return 0


def earned_balance(user):
    try:
        return UserCoinBalance.objects.get(user=user).earned_balance
    except UserCoinBalance.DoesNotExist:
        return 0


def total_balance(user):
    try:
        return UserCoinBalance.objects.get(user=user).balance
    except UserCoinBalance.DoesNotExist:
        return 0


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def user():
    return make_user()


@pytest.fixture
def tier():
    return make_tier(bonus_coins=500, charge_gift_coins=100)


# ---------------------------------------------------------------------------
# Telebirr one-time callback tests
# ---------------------------------------------------------------------------


def test_telebirr_one_time_callback_grants_bonus_coins_immediately(rf, user, tier):
    """
    Successful one-time Telebirr payment must grant the tier's bonus_coins
    immediately via SubscriptionPlan.activate().
    """
    sub = SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        status='pending',
        duration_type='monthly',
        payment_reference='merch-123',
    )

    request = rf.post(
        '/api/telebirr/one-time/callback/',
        data=json.dumps({
            'merch_order_id': 'merch-123',
            'trade_status': 'Completed',
            'payment_order_id': 'order-456',
        }),
        content_type='application/json',
    )

    from unittest.mock import patch
    with patch('api.views.subscription.telebirr_service.verify_notify') as mock_verify:
        mock_verify.return_value = {
            'verified': True,
            'merch_order_id': 'merch-123',
            'trade_status': 'Completed',
            'payment_order_id': 'order-456',
        }

        response = telebirr_one_time_callback(request)

    assert response.status_code == 200

    sub.refresh_from_db()
    assert sub.status == 'active'
    assert sub.bonus_coins_granted_at is not None

    # Bonus coins granted
    assert bonus_balance(user) == 500


def test_telebirr_one_time_callback_grants_charge_gift_coins_immediately(rf, user, tier):
    """
    Successful one-time Telebirr payment must create a completed
    SubscriptionPayment which triggers charge_gift_coins grant via signal.
    """
    sub = SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        status='pending',
        duration_type='monthly',
        payment_reference='merch-456',
    )

    request = rf.post(
        '/api/telebirr/one-time/callback/',
        data=json.dumps({
            'merch_order_id': 'merch-456',
            'trade_status': 'Completed',
            'payment_order_id': 'order-789',
        }),
        content_type='application/json',
    )

    from unittest.mock import patch
    with patch('api.views.subscription.telebirr_service.verify_notify') as mock_verify:
        mock_verify.return_value = {
            'verified': True,
            'merch_order_id': 'merch-456',
            'trade_status': 'Completed',
            'payment_order_id': 'order-789',
        }

        response = telebirr_one_time_callback(request)

    assert response.status_code == 200

    sub.refresh_from_db()
    assert sub.status == 'active'

    # charge_gift_coins should be in earned balance (giftable)
    assert earned_balance(user) == 100
    assert total_balance(user) == 600  # bonus + earned


def test_telebirr_one_time_callback_failed_payment_grants_no_coins(rf, user, tier):
    """
    Failed or cancelled payments must not grant any coins.
    """
    sub = SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        status='pending',
        duration_type='monthly',
        payment_reference='merch-789',
    )

    request = rf.post(
        '/api/telebirr/one-time/callback/',
        data=json.dumps({
            'merch_order_id': 'merch-789',
            'trade_status': 'FAILED',
            'payment_order_id': 'order-999',
        }),
        content_type='application/json',
    )

    from unittest.mock import patch
    with patch('api.views.subscription.telebirr_service.verify_notify') as mock_verify:
        mock_verify.return_value = {
            'verified': True,
            'merch_order_id': 'merch-789',
            'trade_status': 'FAILED',
            'payment_order_id': 'order-999',
        }

        response = telebirr_one_time_callback(request)

    assert response.status_code == 200

    sub.refresh_from_db()
    assert sub.status == 'failed'

    # No coins should be granted
    assert bonus_balance(user) == 0
    assert earned_balance(user) == 0
    assert total_balance(user) == 0


def test_telebirr_one_time_callback_duplicate_grants_only_once(rf, user, tier):
    """
    Duplicate webhook deliveries must not grant coins twice.
    """
    sub = SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        status='pending',
        duration_type='monthly',
        payment_reference='merch-dup',
    )

    request_data = json.dumps({
        'merch_order_id': 'merch-dup',
        'trade_status': 'Completed',
        'payment_order_id': 'order-dup',
    })

    from unittest.mock import patch
    with patch('api.views.subscription.telebirr_service.verify_notify') as mock_verify:
        mock_verify.return_value = {
            'verified': True,
            'merch_order_id': 'merch-dup',
            'trade_status': 'Completed',
            'payment_order_id': 'order-dup',
        }

        # First callback
        request1 = rf.post(
            '/api/telebirr/one-time/callback/',
            data=json.dumps({
                'merch_order_id': 'merch-dup',
                'trade_status': 'Completed',
                'payment_order_id': 'order-dup',
            }),
            content_type='application/json',
        )
        response1 = telebirr_one_time_callback(request1)
        assert response1.status_code == 200

        # Second callback (duplicate) - create fresh request
        request2 = rf.post(
            '/api/telebirr/one-time/callback/',
            data=json.dumps({
                'merch_order_id': 'merch-dup',
                'trade_status': 'Completed',
                'payment_order_id': 'order-dup',
            }),
            content_type='application/json',
        )
        response2 = telebirr_one_time_callback(request2)
        assert response2.status_code == 200

    sub.refresh_from_db()
    assert sub.status == 'active'

    # Coins granted only once
    assert bonus_balance(user) == 500
    assert earned_balance(user) == 100
    assert total_balance(user) == 600


def test_different_durations_receive_configured_allocation(rf):
    """
    Different access durations (daily, weekly, monthly) must receive their
    configured bonus_coins and charge_gift_coins allocation.
    """
    daily_tier = make_tier(bonus_coins=50, charge_gift_coins=10, duration_type='daily', duration_days=1)
    weekly_tier = make_tier(bonus_coins=200, charge_gift_coins=50, duration_type='weekly', duration_days=7)
    monthly_tier = make_tier(bonus_coins=500, charge_gift_coins=100, duration_type='monthly', duration_days=30)

    for tier in [daily_tier, weekly_tier, monthly_tier]:
        # Create fresh user and subscription for each tier for isolation
        user = make_user(f'duration_user_{tier.slug}')
        sub = SubscriptionPlan.objects.create(
            user=user,
            tier=tier,
            status='pending',
            duration_type=tier.duration_type,
            payment_reference=f'merch-{tier.slug}',
        )

        request = rf.post(
            '/api/telebirr/one-time/callback/',
            data=json.dumps({
                'merch_order_id': f'merch-{tier.slug}',
                'trade_status': 'Completed',
                'payment_order_id': f'order-{tier.slug}',
            }),
            content_type='application/json',
        )

        from unittest.mock import patch
        with patch('api.views.subscription.telebirr_service.verify_notify') as mock_verify:
            mock_verify.return_value = {
                'verified': True,
                'merch_order_id': f'merch-{tier.slug}',
                'trade_status': 'Completed',
                'payment_order_id': f'order-{tier.slug}',
            }

            response = telebirr_one_time_callback(request)

        assert response.status_code == 200

        # Check configured allocation for this tier
        assert bonus_balance(user) == tier.bonus_coins
        assert earned_balance(user) == tier.charge_gift_coins


def test_wallet_balance_updated_atomically(rf, user, tier):
    """
    Coin grant and subscription activation must happen in the same atomic
    transaction so balance is always consistent.
    """
    sub = SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        status='pending',
        duration_type='monthly',
        payment_reference='merch-atomic',
    )

    request = rf.post(
        '/api/telebirr/one-time/callback/',
        data=json.dumps({
            'merch_order_id': 'merch-atomic',
            'trade_status': 'Completed',
            'payment_order_id': 'order-atomic',
        }),
        content_type='application/json',
    )

    from unittest.mock import patch
    with patch('api.views.subscription.telebirr_service.verify_notify') as mock_verify:
        mock_verify.return_value = {
            'verified': True,
            'merch_order_id': 'merch-atomic',
            'trade_status': 'Completed',
            'payment_order_id': 'order-atomic',
        }

        response = telebirr_one_time_callback(request)

    assert response.status_code == 200

    sub.refresh_from_db()
    assert sub.status == 'active'

    # Balance must reflect both grants atomically
    balance = UserCoinBalance.objects.get(user=user)
    assert balance.bonus_balance == 500
    assert balance.earned_balance == 100
    assert balance.balance == 600


# ---------------------------------------------------------------------------
# USSD Push payment tests
# ---------------------------------------------------------------------------


def test_ussd_subscription_webhook_grants_bonus_coins(user):
    """
    Successful USSD push subscription payment must grant bonus_coins
    via activate().
    """
    tier = make_tier(bonus_coins=300, charge_gift_coins=50)

    start_date = timezone.now()
    end_date = start_date + timezone.timedelta(days=30)
    sub = SubscriptionPlan.objects.create(
        user=user,
        tier=None,  # will be set on activation
        status='pending',
        duration_type='monthly',
        start_date=start_date,
        end_date=end_date,
    )
    payment = SubscriptionPayment.objects.create(
        user=user,
        subscription=sub,
        amount=tier.price_etb,
        currency='ETB',
        status='pending',
        payment_method='telebirr',
        onevas_transaction_id='ocid-123',
        duration_type='monthly',
        period_start=start_date,
        period_end=end_date,
    )

    _activate_ussd_subscription_payment(payment, tier)

    sub.refresh_from_db()
    assert sub.status == 'active'
    assert sub.bonus_coins_granted_at is not None

    # Bonus coins granted
    assert bonus_balance(user) == 300


def test_ussd_subscription_webhook_grants_charge_gift_coins_via_signal(user):
    """
    Successful USSD push subscription payment must have charge_gift_coins
    granted via the post_save signal on SubscriptionPayment.
    """
    tier = make_tier(bonus_coins=300, charge_gift_coins=50)

    start_date = timezone.now()
    end_date = start_date + timezone.timedelta(days=30)
    sub = SubscriptionPlan.objects.create(
        user=user,
        tier=None,
        status='pending',
        duration_type='monthly',
        start_date=start_date,
        end_date=end_date,
    )
    payment = SubscriptionPayment.objects.create(
        user=user,
        subscription=sub,
        amount=tier.price_etb,
        currency='ETB',
        status='pending',
        payment_method='telebirr',
        onevas_transaction_id='ocid-456',
        duration_type='monthly',
        period_start=start_date,
        period_end=end_date,
    )

    _activate_ussd_subscription_payment(payment, tier)

    payment.refresh_from_db()
    assert payment.status == 'completed'

    # charge_gift_coins granted via signal
    assert earned_balance(user) == 50


def test_ussd_subscription_webhook_failed_payment_grants_no_coins(user):
    """
    Failed USSD push payment must not grant coins.
    """
    tier = make_tier(bonus_coins=300, charge_gift_coins=50)

    start_date = timezone.now()
    end_date = start_date + timezone.timedelta(days=30)
    sub = SubscriptionPlan.objects.create(
        user=user,
        tier=None,
        status='pending',
        duration_type='monthly',
        start_date=start_date,
        end_date=end_date,
    )
    payment = SubscriptionPayment.objects.create(
        user=user,
        subscription=sub,
        amount=tier.price_etb,
        currency='ETB',
        status='pending',
        payment_method='telebirr',
        onevas_transaction_id='ocid-789',
        duration_type='monthly',
        period_start=start_date,
        period_end=end_date,
    )

    # Don't call _activate_ussd_subscription_payment - simulate failed payment
    # by not activating. The payment stays pending/failed.
    payment.status = 'failed'
    payment.save()

    # Verify no coins granted
    assert bonus_balance(user) == 0
    assert earned_balance(user) == 0


def test_ussd_subscription_webhook_duplicate_grants_only_once(user):
    """
    Duplicate USSD webhook deliveries must not grant coins twice.
    The webhook checks payment.status and returns early if not 'pending'.
    """
    tier = make_tier(bonus_coins=300, charge_gift_coins=50)

    start_date = timezone.now()
    end_date = start_date + timezone.timedelta(days=30)
    sub = SubscriptionPlan.objects.create(
        user=user,
        tier=None,
        status='pending',
        duration_type='monthly',
        start_date=start_date,
        end_date=end_date,
    )
    payment = SubscriptionPayment.objects.create(
        user=user,
        subscription=sub,
        amount=tier.price_etb,
        currency='ETB',
        status='pending',
        payment_method='telebirr',
        onevas_transaction_id='ocid-dup',
        duration_type='monthly',
        period_start=start_date,
        period_end=end_date,
    )

    # First activation
    _activate_ussd_subscription_payment(payment, tier)

    # Verify first grant
    assert bonus_balance(user) == 300
    assert earned_balance(user) == 50

    # Second activation attempt (simulate duplicate webhook)
    # The webhook would find payment.status != 'pending' and return early.
    # We verify the function's idempotency by calling it again with the
    # now-completed payment - it should not grant again.
    _activate_ussd_subscription_payment(payment, tier)

    # Coins should still be granted only once total
    assert bonus_balance(user) == 300
    assert earned_balance(user) == 50
    assert total_balance(user) == 350


# ---------------------------------------------------------------------------
# Audit trail tests
# ---------------------------------------------------------------------------


def test_coin_grants_create_audit_records(rf, user, tier):
    """
    Coin grants must create audit records (CoinTransaction) showing why/how
    coins were granted.
    """
    sub = SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        status='pending',
        duration_type='monthly',
        payment_reference='merch-audit',
    )

    request = rf.post(
        '/api/telebirr/one-time/callback/',
        data=json.dumps({
            'merch_order_id': 'merch-audit',
            'trade_status': 'Completed',
            'payment_order_id': 'order-audit',
        }),
        content_type='application/json',
    )

    from unittest.mock import patch
    with patch('api.views.subscription.telebirr_service.verify_notify') as mock_verify:
        mock_verify.return_value = {
            'verified': True,
            'merch_order_id': 'merch-audit',
            'trade_status': 'Completed',
            'payment_order_id': 'order-audit',
        }

        response = telebirr_one_time_callback(request)

    assert response.status_code == 200

    # Check CoinTransaction records exist for both grants
    bonus_tx = CoinTransaction.objects.filter(
        user=user,
        transaction_type='subscription_bonus',
    ).first()
    assert bonus_tx is not None
    assert bonus_tx.coins == 500
    assert 'subscription bonus' in bonus_tx.description.lower()

    gift_tx = CoinTransaction.objects.filter(
        user=user,
        transaction_type='subscription_gift',
    ).first()
    assert gift_tx is not None
    assert gift_tx.coins == 100
    assert 'subscription gift' in gift_tx.description.lower()

    # Verify the payment reference is recorded for traceability
    assert gift_tx.payment_reference != ''
    assert str(gift_tx.payment_reference) != ''