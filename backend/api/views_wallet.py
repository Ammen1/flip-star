"""
Wallet API - User-facing endpoints for the coin economy.

Endpoints:
- GET    /api/wallet/                       Wallet summary (balances + recent transactions)
- GET    /api/wallet/transactions/          Paginated transaction history
- GET    /api/wallet/withdrawal-info/       Withdrawal eligibility + conversion preview
- POST   /api/wallet/withdraw/              Request a withdrawal (coins -> Birr)
- GET    /api/wallet/withdrawals/           User's withdrawal request history
- POST   /api/wallet/withdrawals/<id>/cancel/   Cancel pending withdrawal
- GET    /api/wallet/config/                Public-safe wallet config (rates, thresholds)
- POST   /api/wallet/telebirr/initiate/     Initiate Telebirr payment for coin purchase
- POST   /api/wallet/telebirr-callback/     Telebirr payment callback webhook
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response

from .models_contest import UserCoinBalance, CoinTransaction, CoinPackage
from .models_wallet import WalletConfig, WithdrawalRequest
from .telebirr_service import telebirr_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TRANSACTION_DISPLAY = dict(CoinTransaction.TRANSACTION_TYPES)


def _get_or_create_balance(user):
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    return balance


def _serialize_transaction(tx):
    return {
        'id': tx.id,
        'type': tx.transaction_type,
        'type_display': TRANSACTION_DISPLAY.get(tx.transaction_type, tx.transaction_type),
        'coins': tx.coins,
        'is_credit': tx.coins > 0,
        'description': tx.description or '',
        'recipient_username': tx.recipient.username if tx.recipient_id else None,
        'reel_id': tx.reel_id,
        'payment_method': tx.payment_method or None,
        'payment_reference': tx.payment_reference or None,
        'is_successful': tx.is_successful,
        'created_at': tx.created_at.isoformat(),
    }


def _serialize_withdrawal(w):
    return {
        'id': w.id,
        'coin_amount': w.coin_amount,
        'gross_birr': str(w.gross_birr),
        'fee_birr': str(w.fee_birr),
        'net_birr': str(w.net_birr),
        'conversion_rate': w.conversion_rate,
        'payout_method': w.payout_method,
        'payout_method_display': dict(WithdrawalRequest.PAYOUT_METHODS).get(w.payout_method, w.payout_method),
        'payout_account': w.payout_account,
        'payout_account_name': w.payout_account_name,
        'status': w.status,
        'status_display': dict(WithdrawalRequest.STATUS_CHOICES).get(w.status, w.status),
        'admin_notes': w.admin_notes if w.status in ('approved', 'completed', 'rejected') else '',
        'rejection_reason': w.rejection_reason,
        'payout_reference': w.payout_reference,
        'created_at': w.created_at.isoformat(),
        'reviewed_at': w.reviewed_at.isoformat() if w.reviewed_at else None,
        'completed_at': w.completed_at.isoformat() if w.completed_at else None,
        'can_cancel': w.can_cancel(),
    }


# ---------------------------------------------------------------------------
# User wallet endpoints
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_summary(request):
    """Get user's wallet summary: balances, totals, recent transactions."""
    balance = _get_or_create_balance(request.user)
    config = WalletConfig.get_config()

    recent_tx = (
        CoinTransaction.objects
        .filter(user=request.user)
        .order_by('-created_at')[:10]
    )

    pending_withdrawals = WithdrawalRequest.objects.filter(
        user=request.user,
        status__in=['pending', 'approved', 'processing']
    ).count()

    return Response({
        'balance': {
            'total': balance.balance,
            'earned': balance.earned_balance,
            'purchased': balance.purchased_balance,
        },
        'totals': {
            'lifetime_earned': balance.total_earned,
            'lifetime_spent': balance.total_spent,
            'lifetime_purchased': balance.total_purchased,
            'lifetime_withdrawn': balance.total_withdrawn,
        },
        'withdrawal': {
            'enabled': config.withdrawal_enabled,
            'min_coins': config.withdrawal_min_coins,
            'coins_per_birr': config.coins_per_birr,
            'fee_percent': str(config.withdrawal_fee_percent),
            'eligible': (
                config.withdrawal_enabled
                and balance.earned_balance >= config.withdrawal_min_coins
            ),
            'pending_requests': pending_withdrawals,
        },
        'currency': 'ETB',
        'recent_transactions': [_serialize_transaction(tx) for tx in recent_tx],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_transactions(request):
    """Paginated transaction history. Query params: ?type=&page=&page_size="""
    qs = CoinTransaction.objects.filter(user=request.user).order_by('-created_at')

    tx_type = request.query_params.get('type')
    if tx_type:
        qs = qs.filter(transaction_type=tx_type)

    direction = request.query_params.get('direction')  # 'in' or 'out'
    if direction == 'in':
        qs = qs.filter(coins__gt=0)
    elif direction == 'out':
        qs = qs.filter(coins__lt=0)

    try:
        page = max(int(request.query_params.get('page', 1)), 1)
        page_size = min(max(int(request.query_params.get('page_size', 20)), 1), 100)
    except ValueError:
        page, page_size = 1, 20

    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = qs[start:end]

    return Response({
        'count': total,
        'page': page,
        'page_size': page_size,
        'has_next': end < total,
        'has_prev': page > 1,
        'results': [_serialize_transaction(tx) for tx in items],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def withdrawal_info(request):
    """
    Get withdrawal eligibility info + preview conversion for a given amount.
    Query params: ?coins=<amount>
    """
    balance = _get_or_create_balance(request.user)
    config = WalletConfig.get_config()

    coins_param = request.query_params.get('coins')
    preview = None
    if coins_param:
        try:
            coins = int(coins_param)
            if coins > 0:
                breakdown = config.calculate_withdrawal(coins)
                preview = {
                    'coins': breakdown['coins'],
                    'gross_birr': str(breakdown['gross_birr']),
                    'fee_birr': str(breakdown['fee_birr']),
                    'net_birr': str(breakdown['net_birr']),
                    'fee_percent': str(breakdown['fee_percent']),
                }
        except ValueError:
            pass

    return Response({
        'enabled': config.withdrawal_enabled,
        'min_coins': config.withdrawal_min_coins,
        'max_coins_per_request': config.withdrawal_max_coins_per_request,
        'coins_per_birr': config.coins_per_birr,
        'fee_percent': str(config.withdrawal_fee_percent),
        'processing_days': config.withdrawal_processing_days,
        'available_coins': balance.earned_balance,
        'eligible': (
            config.withdrawal_enabled
            and balance.earned_balance >= config.withdrawal_min_coins
        ),
        'payout_methods': [
            {'value': v, 'label': l} for v, l in WithdrawalRequest.PAYOUT_METHODS
        ],
        'preview': preview,
        'currency': 'ETB',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_withdrawal(request):
    """
    Create a withdrawal request using points (not coins).
    Body: { point_amount, payout_method, payout_account, payout_account_name }
    """
    config = WalletConfig.get_config()

    if not config.withdrawal_enabled:
        return Response(
            {'error': 'Withdrawals are currently disabled'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        point_amount = int(request.data.get('point_amount', 0))
    except (TypeError, ValueError):
        return Response({'error': 'Invalid point_amount'}, status=status.HTTP_400_BAD_REQUEST)

    payout_method = request.data.get('payout_method', 'telebirr')
    payout_account = (request.data.get('payout_account') or '').strip()
    payout_account_name = (request.data.get('payout_account_name') or '').strip()

    if point_amount < config.withdrawal_min_points:
        return Response(
            {'error': f'Minimum withdrawal is {config.withdrawal_min_points} points'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if point_amount > config.withdrawal_max_points_per_request:
        return Response(
            {'error': f'Maximum per request is {config.withdrawal_max_points_per_request} points'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if payout_method not in dict(WithdrawalRequest.PAYOUT_METHODS):
        return Response({'error': 'Invalid payout method'}, status=status.HTTP_400_BAD_REQUEST)
    if not payout_account:
        return Response(
            {'error': 'payout_account is required (phone or bank account number)'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check user's point balance
    user_profile = request.user.profile
    if user_profile.points < point_amount:
        return Response(
            {'error': f'Insufficient points. You have {user_profile.points} points.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    breakdown = config.calculate_points_withdrawal(point_amount)

    # Deduct points now (refunded if rejected)
    user_profile.points -= point_amount
    user_profile.points_withdrawn_total += point_amount
    user_profile.save()

    withdrawal = WithdrawalRequest.objects.create(
        user=request.user,
        point_amount=point_amount,
        gross_birr=breakdown['gross_birr'],
        fee_birr=breakdown['fee_birr'],
        net_birr=breakdown['net_birr'],
        conversion_rate=config.points_per_birr,
        payout_method=payout_method,
        payout_account=payout_account,
        payout_account_name=payout_account_name,
        status='pending',
    )

    return Response(
        {
            'message': 'Withdrawal request submitted successfully',
            'withdrawal': _serialize_withdrawal(withdrawal),
            'new_balance': {
                'points': user_profile.points,
                'points_earned_total': user_profile.points_earned_total,
                'points_withdrawn_total': user_profile.points_withdrawn_total,
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_withdrawals(request):
    """List current user's withdrawal requests."""
    qs = WithdrawalRequest.objects.filter(user=request.user).order_by('-created_at')
    return Response({
        'count': qs.count(),
        'results': [_serialize_withdrawal(w) for w in qs[:50]],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_withdrawal(request, withdrawal_id):
    """Cancel a pending withdrawal request and refund the coins."""
    try:
        withdrawal = WithdrawalRequest.objects.get(id=withdrawal_id, user=request.user)
    except WithdrawalRequest.DoesNotExist:
        return Response({'error': 'Withdrawal request not found'}, status=status.HTTP_404_NOT_FOUND)

    if not withdrawal.can_cancel():
        return Response(
            {'error': f'Cannot cancel a {withdrawal.status} withdrawal'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Refund coins back to earned balance
    balance = _get_or_create_balance(request.user)
    balance.earned_balance = (balance.earned_balance or 0) + withdrawal.coin_amount
    balance.total_withdrawn = max(0, balance.total_withdrawn - withdrawal.coin_amount)
    balance._sync_balance()
    balance.save()

    CoinTransaction.objects.create(
        user=request.user,
        transaction_type='refund',
        coins=withdrawal.coin_amount,
        description=f'Cancelled withdrawal #{withdrawal.id}',
    )

    withdrawal.status = 'cancelled'
    withdrawal.save()

    return Response({
        'message': 'Withdrawal cancelled and coins refunded',
        'withdrawal': _serialize_withdrawal(withdrawal),
        'new_balance': {
            'total': balance.balance,
            'earned': balance.earned_balance,
            'purchased': balance.purchased_balance,
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def public_wallet_config(request):
    """
    Returns public-safe configuration (rates, costs, packages) for frontend display.
    No sensitive admin info.
    """
    config = WalletConfig.get_config()

    packages = [
        {
            'id': p.id,
            'name': p.name,
            'price_etb': str(p.price_etb),
            'coin_amount': p.coin_amount,
            'bonus_coins': p.bonus_coins,
            'total_coins': p.get_total_coins(),
            'is_featured': p.is_featured,
        }
        for p in CoinPackage.objects.filter(is_active=True).order_by('sort_order', 'price_etb')
    ]

    return Response({
        'currency': 'ETB',
        'currency_label': 'Birr',
        'coins_per_birr': config.coins_per_birr,
        'rewards': {
            'welcome_bonus': config.welcome_bonus,
            'daily_post_bonus': config.daily_post_bonus,
            'campaign_join': config.campaign_join_reward,
            'receive_like': config.receive_like_reward,
            'campaign_winner': config.campaign_winner_reward,
            'referral': config.referral_reward,
        },
        'costs': {
            'post_create': config.cost_post_create,
            'like': config.cost_like,
            'comment': config.cost_comment,
            'join_campaign': config.cost_join_campaign,
            'extra_campaign_entry': config.cost_extra_campaign_entry,
            'boost_2hr': config.cost_boost_2hr,
            'boost_24hr': config.cost_boost_24hr,
        },
        'withdrawal': {
            'enabled': config.withdrawal_enabled,
            'min_coins': config.withdrawal_min_coins,
            'fee_percent': str(config.withdrawal_fee_percent),
            'processing_days': config.withdrawal_processing_days,
        },
        'gifting': {
            'earned_coins_giftable': config.earned_coins_giftable,
            'purchased_coins_giftable': config.purchased_coins_giftable,
        },
        'packages': packages,
    })


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@api_view(['GET', 'PATCH'])
@permission_classes([IsAdminUser])
def admin_wallet_config(request):
    """Get or update wallet configuration (admin only)."""
    config = WalletConfig.get_config()

    if request.method == 'GET':
        return Response({'config': _serialize_full_config(config)})

    # PATCH
    editable_fields = [
        'welcome_bonus',
        'daily_login_day1', 'daily_login_day2', 'daily_login_day3', 'daily_login_day4',
        'daily_login_day5', 'daily_login_day6', 'daily_login_day7',
        'daily_post_bonus', 'campaign_join_reward', 'receive_like_reward',
        'receive_like_daily_cap', 'quality_comment_reward', 'quality_comment_daily_cap',
        'profile_complete_reward', 'referral_reward', 'campaign_winner_reward',
        'cost_post_create', 'cost_like', 'cost_comment', 'cost_join_campaign',
        'cost_extra_campaign_entry', 'cost_boost_2hr', 'cost_boost_24hr',
        'min_balance_to_post', 'min_balance_to_join_campaign',
        'withdrawal_enabled', 'withdrawal_min_coins', 'withdrawal_max_coins_per_request',
        'coins_per_birr', 'withdrawal_fee_percent', 'withdrawal_processing_days',
        'earned_coins_giftable', 'purchased_coins_giftable',
        'earned_coins_withdrawable', 'purchased_coins_withdrawable',
        'earned_coins_expire_days',
    ]
    for field in editable_fields:
        if field in request.data:
            value = request.data[field]
            if field in ('withdrawal_fee_percent',):
                value = Decimal(str(value))
            elif field.startswith(('earned_coins_', 'purchased_coins_', 'withdrawal_enabled')):
                if isinstance(value, str):
                    value = value.lower() in ('true', '1', 'yes', 'on')
            setattr(config, field, value)

    config.updated_by = request.user
    config.save()

    return Response({
        'message': 'Wallet configuration updated',
        'config': _serialize_full_config(config),
    })


def _serialize_full_config(config):
    return {
        'rewards': {
            'welcome_bonus': config.welcome_bonus,
            'daily_login': {
                'day1': config.daily_login_day1,
                'day2': config.daily_login_day2,
                'day3': config.daily_login_day3,
                'day4': config.daily_login_day4,
                'day5': config.daily_login_day5,
                'day6': config.daily_login_day6,
                'day7': config.daily_login_day7,
            },
            'daily_post_bonus': config.daily_post_bonus,
            'campaign_join_reward': config.campaign_join_reward,
            'receive_like_reward': config.receive_like_reward,
            'receive_like_daily_cap': config.receive_like_daily_cap,
            'quality_comment_reward': config.quality_comment_reward,
            'quality_comment_daily_cap': config.quality_comment_daily_cap,
            'profile_complete_reward': config.profile_complete_reward,
            'referral_reward': config.referral_reward,
            'campaign_winner_reward': config.campaign_winner_reward,
        },
        'costs': {
            'post_create': config.cost_post_create,
            'like': config.cost_like,
            'comment': config.cost_comment,
            'join_campaign': config.cost_join_campaign,
            'extra_campaign_entry': config.cost_extra_campaign_entry,
            'boost_2hr': config.cost_boost_2hr,
            'boost_24hr': config.cost_boost_24hr,
        },
        'thresholds': {
            'min_balance_to_post': config.min_balance_to_post,
            'min_balance_to_join_campaign': config.min_balance_to_join_campaign,
        },
        'withdrawal': {
            'enabled': config.withdrawal_enabled,
            'min_coins': config.withdrawal_min_coins,
            'max_coins_per_request': config.withdrawal_max_coins_per_request,
            'coins_per_birr': config.coins_per_birr,
            'fee_percent': str(config.withdrawal_fee_percent),
            'processing_days': config.withdrawal_processing_days,
        },
        'gifting': {
            'earned_coins_giftable': config.earned_coins_giftable,
            'purchased_coins_giftable': config.purchased_coins_giftable,
            'earned_coins_withdrawable': config.earned_coins_withdrawable,
            'purchased_coins_withdrawable': config.purchased_coins_withdrawable,
        },
        'expiry': {
            'earned_coins_expire_days': config.earned_coins_expire_days,
        },
        'updated_at': config.updated_at.isoformat() if config.updated_at else None,
        'updated_by': config.updated_by.username if config.updated_by_id else None,
    }


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_withdrawals_list(request):
    """List all withdrawal requests for admin review."""
    status_filter = request.query_params.get('status', '')
    qs = WithdrawalRequest.objects.select_related('user', 'reviewed_by').order_by('-created_at')
    if status_filter:
        qs = qs.filter(status=status_filter)

    try:
        page = max(int(request.query_params.get('page', 1)), 1)
        page_size = min(max(int(request.query_params.get('page_size', 25)), 1), 100)
    except ValueError:
        page, page_size = 1, 25

    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size

    results = []
    for w in qs[start:end]:
        item = _serialize_withdrawal(w)
        item['user'] = {
            'id': w.user_id,
            'username': w.user.username,
            'email': w.user.email,
        }
        if w.reviewed_by_id:
            item['reviewed_by'] = w.reviewed_by.username
        results.append(item)

    summary = {
        'pending': WithdrawalRequest.objects.filter(status='pending').count(),
        'approved': WithdrawalRequest.objects.filter(status='approved').count(),
        'processing': WithdrawalRequest.objects.filter(status='processing').count(),
        'completed': WithdrawalRequest.objects.filter(status='completed').count(),
        'rejected': WithdrawalRequest.objects.filter(status='rejected').count(),
    }

    return Response({
        'count': total,
        'page': page,
        'page_size': page_size,
        'has_next': end < total,
        'summary': summary,
        'results': results,
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_withdrawal_action(request, withdrawal_id):
    """
    Admin action on a withdrawal request.
    Body: { action: 'approve'|'reject'|'mark_processing'|'mark_completed', notes?, payout_reference? }
    """
    try:
        withdrawal = WithdrawalRequest.objects.get(id=withdrawal_id)
    except WithdrawalRequest.DoesNotExist:
        return Response({'error': 'Withdrawal not found'}, status=status.HTTP_404_NOT_FOUND)

    action = (request.data.get('action') or '').lower()
    notes = request.data.get('notes', '')
    payout_reference = request.data.get('payout_reference', '')

    if action == 'approve':
        if withdrawal.status != 'pending':
            return Response({'error': f'Cannot approve a {withdrawal.status} withdrawal'},
                            status=status.HTTP_400_BAD_REQUEST)
        withdrawal.status = 'approved'
        withdrawal.reviewed_at = timezone.now()
        withdrawal.reviewed_by = request.user
        if notes:
            withdrawal.admin_notes = notes
        withdrawal.save()

    elif action == 'reject':
        if withdrawal.status not in ('pending', 'approved'):
            return Response({'error': f'Cannot reject a {withdrawal.status} withdrawal'},
                            status=status.HTTP_400_BAD_REQUEST)
        withdrawal.mark_rejected(request.user, reason=notes)

    elif action == 'mark_processing':
        if withdrawal.status not in ('approved',):
            return Response({'error': f'Must be approved before processing'},
                            status=status.HTTP_400_BAD_REQUEST)
        withdrawal.status = 'processing'
        if notes:
            withdrawal.admin_notes = notes
        withdrawal.save()

    elif action == 'mark_completed':
        if withdrawal.status not in ('approved', 'processing'):
            return Response({'error': f'Must be approved/processing first'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not payout_reference:
            return Response({'error': 'payout_reference is required'},
                            status=status.HTTP_400_BAD_REQUEST)
        withdrawal.mark_completed(request.user, payout_reference=payout_reference)
        if notes:
            withdrawal.admin_notes = notes
            withdrawal.save()

    else:
        return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        'message': f'Withdrawal {action} successful',
        'withdrawal': _serialize_withdrawal(withdrawal),
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_adjust_balance(request):
    """
    Manually credit or debit a user's wallet (admin only).
    Body: { user_id, amount (positive or negative), bucket: 'earned'|'purchased', reason }
    """
    try:
        user_id = int(request.data.get('user_id'))
        amount = int(request.data.get('amount'))
    except (TypeError, ValueError):
        return Response({'error': 'Invalid user_id or amount'}, status=status.HTTP_400_BAD_REQUEST)

    bucket = request.data.get('bucket', 'earned')
    reason = request.data.get('reason', 'Admin adjustment')

    if bucket not in ('earned', 'purchased'):
        return Response({'error': 'bucket must be earned or purchased'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    balance = _get_or_create_balance(user)

    if amount >= 0:
        if bucket == 'earned':
            balance.add_earned(amount, transaction_type='admin_adjustment', description=reason)
        else:
            balance.add_purchased(amount, transaction_type='admin_adjustment', description=reason)
    else:
        # Debit
        deduct = abs(amount)
        if bucket == 'earned':
            if balance.earned_balance < deduct:
                return Response({'error': 'Insufficient earned balance to deduct'},
                                status=status.HTTP_400_BAD_REQUEST)
            balance.earned_balance -= deduct
        else:
            if balance.purchased_balance < deduct:
                return Response({'error': 'Insufficient purchased balance to deduct'},
                                status=status.HTTP_400_BAD_REQUEST)
            balance.purchased_balance -= deduct
        balance.total_spent += deduct
        balance._sync_balance()
        balance.save()
        CoinTransaction.objects.create(
            user=user,
            transaction_type='admin_adjustment',
            coins=-deduct,
            description=reason,
        )

    return Response({
        'message': f'Adjusted {user.username}\'s {bucket} balance by {amount}',
        'new_balance': {
            'total': balance.balance,
            'earned': balance.earned_balance,
            'purchased': balance.purchased_balance,
        },
    })


# ---------------------------------------------------------------------------
# Telebirr Payment Integration
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def telebirr_initiate_payment(request):
    """
    Initiate a Telebirr payment for coin purchase.
    Body: { package_id, phone_number }
    """
    package_id = request.data.get('package_id')
    phone_number = request.data.get('phone_number')
    
    if not package_id:
        return Response({'error': 'package_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not phone_number:
        return Response({'error': 'phone_number is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        package = CoinPackage.objects.get(id=package_id, is_active=True)
    except CoinPackage.DoesNotExist:
        return Response({'error': 'Package not found or inactive'}, status=status.HTTP_404_NOT_FOUND)
    
    # Calculate total amount (package price + potential fee)
    config = WalletConfig.get_config()
    fee_percent = config.withdrawal_fee_percent or Decimal('0.0')
    fee_amount = float(package.price_etb) * float(fee_percent) / 100
    total_amount = float(package.price_etb) + fee_amount
    
    # Initiate payment with Telebirr
    result = telebirr_service.initiate_payment(
        amount=total_amount,
        phone_number=phone_number,
        user_id=request.user.id,
        package_id=package_id
    )
    
    if result.get('success'):
        # Create a pending transaction record
        balance = _get_or_create_balance(request.user)
        transaction = CoinTransaction.objects.create(
            user=request.user,
            transaction_type='purchase',
            coins=0,  # Will be updated after successful payment
            payment_method='telebirr',
            payment_reference=result.get('transaction_id'),
            package=package,
            description=f'Pending Telebirr payment for {package.name}',
            is_successful=False
        )
        
        return Response({
            'success': True,
            'payment_url': result.get('payment_url'),
            'transaction_id': result.get('transaction_id'),
            'out_trade_no': result.get('out_trade_no'),
            'amount': total_amount,
            'package': {
                'id': package.id,
                'name': package.name,
                'coin_amount': package.coin_amount,
                'bonus_coins': package.bonus_coins,
                'total_coins': package.get_total_coins(),
            },
            'message': 'Payment initiated. Redirect to payment_url to complete.'
        })
    else:
        return Response({
            'error': result.get('error', 'Payment initiation failed'),
            'details': result
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])  # Telebirr calls this without authentication
def telebirr_callback(request):
    """
    Handle Telebirr payment callback (webhook).
    This endpoint is called by Telebirr after payment completion.
    """
    callback_data = request.data
    
    # Process the callback
    result = telebirr_service.process_callback(callback_data)
    
    if not result.get('success'):
        return Response({'error': result.get('error')}, status=status.HTTP_400_BAD_REQUEST)
    
    # Extract transaction info
    out_trade_no = result.get('transaction_id')
    telebirr_transaction_id = result.get('telebirr_transaction_id')
    amount = result.get('amount')
    is_paid = result.get('success')
    
    # Find the pending transaction
    try:
        transaction = CoinTransaction.objects.get(
            payment_reference=out_trade_no,
            payment_method='telebirr',
            is_successful=False
        )
    except CoinTransaction.DoesNotExist:
        return Response({'error': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if is_paid:
        # Payment successful - credit the user's account
        package = transaction.package
        total_coins = package.get_total_coins() if package else 0
        
        balance = _get_or_create_balance(transaction.user)
        
        # Add coins to purchased balance
        balance.add_purchased(
            amount=total_coins,
            transaction_type='purchase',
            payment_method='telebirr',
            payment_reference=telebirr_transaction_id,
            package=package,
            description=f'Coin purchase via Telebirr: {package.name if package else "Unknown"}'
        )
        
        # Update transaction record
        transaction.coins = total_coins
        transaction.is_successful = True
        transaction.payment_reference = telebirr_transaction_id
        transaction.description = f'Successful Telebirr payment for {package.name if package else "Unknown"}'
        transaction.save()
        
        return Response({
            'success': True,
            'message': 'Payment processed successfully',
            'coins_added': total_coins
        })
    else:
        # Payment failed - update transaction record
        transaction.description = f'Failed Telebirr payment: {result.get("status")}'
        transaction.save()
        
        return Response({
            'success': False,
            'message': 'Payment failed or cancelled'
        }, status=status.HTTP_400_BAD_REQUEST)
