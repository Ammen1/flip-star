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

import logging
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from api.integrations.telebirr.checkout import telebirr_service
from api.integrations.telebirr.direct_debit import telebirr_direct_debit_service
from api.models.contest import CoinPackage, CoinTransaction, UserCoinBalance
from api.models.core import UserProfile
from api.models.wallet import WalletConfig, WithdrawalRequest
from api.serializers.core import UserSerializer
from api.views.core import _normalize_ethiopian_phone
from common.security import encrypted_endpoint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TRANSACTION_DISPLAY = dict(CoinTransaction.TRANSACTION_TYPES)


def _get_or_create_balance(user):
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    return balance


def _serialize_transaction(tx):
    # Method-aware display label for purchases
    type_display = TRANSACTION_DISPLAY.get(tx.transaction_type, tx.transaction_type)
    if tx.transaction_type == 'purchase' and tx.payment_method:
        method_label = {
            'airtime': 'Airtime',
            'telebirr': 'Telebirr',
            'coins': 'Coins',
        }.get(tx.payment_method, tx.payment_method.title())
        type_display = f'Coin Purchase ({method_label})'

    # For gifts, show the other party
    other_user = None
    if tx.recipient_id:
        other_user = {
            'id': tx.recipient_id,
            'username': tx.recipient.username,
        }

    # Get post details for gift transactions
    post_details = None
    if tx.reel_id and (
        tx.transaction_type == 'gift_sent' or tx.transaction_type == 'gift_received'
    ):
        try:
            reel = tx.reel
            if reel:
                post_details = {
                    'id': reel.id,
                    'title': reel.title or '',
                    'description': reel.description or '',
                    'media_url': reel.media.url if reel.media else None,
                }
        except Exception:
            # Best-effort enrichment: a transaction still serialises without
            # its reel. Logged rather than silently dropped so a broken
            # relation is visible.
            logger.debug('Could not attach reel to transaction %s', tx.id, exc_info=True)

    return {
        'id': tx.id,
        'type': tx.transaction_type,
        'type_display': type_display,
        'coins': tx.coins,
        'is_credit': tx.coins > 0,
        'description': tx.description or '',
        'other_user': other_user,
        'recipient_username': tx.recipient.username if tx.recipient_id else None,
        'reel_id': tx.reel_id,
        'post_details': post_details,
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
        'payout_method_display': dict(WithdrawalRequest.PAYOUT_METHODS).get(
            w.payout_method, w.payout_method
        ),
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
@encrypted_endpoint
def wallet_summary(request):
    """Get user's wallet summary: balances, points, totals, recent transactions."""
    balance = _get_or_create_balance(request.user)
    config = WalletConfig.get_config()

    recent_tx = CoinTransaction.objects.filter(user=request.user).order_by('-created_at')[:10]

    pending_withdrawals = WithdrawalRequest.objects.filter(
        user=request.user, status__in=['pending', 'approved', 'processing']
    ).count()

    return Response(
        {
            'balance': {
                'total': balance.balance,
                'earned': balance.earned_balance,
                'purchased': balance.purchased_balance,
            },
            'points': {
                'current': request.user.profile.points,
                'earned_total': request.user.profile.points_earned_total,
                'withdrawn_total': request.user.profile.points_withdrawn_total,
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
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
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

    return Response(
        {
            'count': total,
            'page': page,
            'page_size': page_size,
            'has_next': end < total,
            'has_prev': page > 1,
            'results': [_serialize_transaction(tx) for tx in items],
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
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

    return Response(
        {
            'enabled': config.withdrawal_enabled,
            'min_coins': config.withdrawal_min_coins,
            'max_coins_per_request': config.withdrawal_max_coins_per_request,
            'coins_per_birr': config.coins_per_birr,
            'fee_percent': str(config.withdrawal_fee_percent),
            'processing_days': config.withdrawal_processing_days,
            'available_coins': balance.earned_balance,
            'eligible': (
                config.withdrawal_enabled and balance.earned_balance >= config.withdrawal_min_coins
            ),
            'payout_methods': [
                {'value': value, 'label': label}
                for value, label in WithdrawalRequest.PAYOUT_METHODS
            ],
            'preview': preview,
            'currency': 'ETB',
        }
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
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

    # Telebirr payouts go to the user's own phone -- fall back to the
    # profile's number so the client doesn't have to resend it.
    if payout_method == 'telebirr' and not payout_account and request.user.profile.phone_number:
        payout_account = request.user.profile.phone_number

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

    # Deduct points now (refunded if rejected) and create the withdrawal
    # request together -- if either half fails the other must not stick.
    try:
        with db_transaction.atomic():
            user_profile.deduct_points(point_amount, total_field='points_withdrawn_total')
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
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Telebirr payouts trigger the B2C transfer right away. This call is a
    # real outbound HTTP request to Telebirr, so it deliberately runs
    # outside the row lock above -- holding a lock across an external call
    # would block every other action on this user's points/withdrawals for
    # as long as Telebirr takes to respond. The withdrawal already exists as
    # 'pending' at this point; a second, separate locked transaction below
    # moves it to 'processing' or 'failed' depending on the result. It is
    # only ever marked 'completed' by telebirr_b2c_webhook, once Telebirr
    # itself confirms the payout -- never here.
    if payout_method == 'telebirr':
        receiver_msisdn = payout_account
        if not receiver_msisdn.startswith('251'):
            receiver_msisdn = '251' + receiver_msisdn.lstrip('0')

        b2c_result = telebirr_direct_debit_service.initiate_b2c_payment(
            receiver_msisdn=receiver_msisdn,
            amount=breakdown['net_birr'],
            currency='ETB',
            reason_type='Points withdrawal payout',
            remark=f'Withdrawal #{withdrawal.id} - {point_amount} points to Birr',
            reference_data={'withdrawal_id': str(withdrawal.id)},
        )

        if b2c_result.get('success'):
            with db_transaction.atomic():
                withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal.pk)
                withdrawal.originator_conversation_id = (
                    b2c_result.get('originator_conversation_id') or ''
                )
                withdrawal.conversation_id = b2c_result.get('conversation_id') or ''
                withdrawal.status = 'processing'
                withdrawal.save(
                    update_fields=['originator_conversation_id', 'conversation_id', 'status']
                )
        else:
            logger.error(
                'B2C initiation failed for withdrawal #%s: %s',
                withdrawal.id,
                b2c_result.get('error'),
            )
            with db_transaction.atomic():
                withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal.pk)
                if withdrawal.status == 'pending':
                    withdrawal.status = 'failed'
                    withdrawal.rejection_reason = (
                        f"B2C payment failed: {b2c_result.get('error', 'Unknown error')}"
                    )
                    withdrawal.save(update_fields=['status', 'rejection_reason'])
                    # Refund the points. total_field is intentionally omitted:
                    # _apply_delta only ever increments a total counter, and
                    # points_withdrawn_total must not end up counting a
                    # withdrawal that was never actually paid out. Matches
                    # the existing, documented no-op quirk in
                    # WithdrawalRequest.mark_rejected for the coin side.
                    user_profile.add_points(point_amount, total_field=None)

            return Response(
                {
                    'error': 'B2C payment initiation failed',
                    'details': b2c_result.get('error'),
                    'withdrawal': _serialize_withdrawal(withdrawal),
                    'new_balance': {
                        'points': user_profile.points,
                        'points_earned_total': user_profile.points_earned_total,
                        'points_withdrawn_total': user_profile.points_withdrawn_total,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def reinvest_points(request):
    """
    Convert points back to coins (re-invest).
    Body: { points }
    1 Point = 1 Coin
    """
    try:
        points_amount = int(request.data.get('points', 0))
    except (TypeError, ValueError):
        return Response({'error': 'Invalid points amount'}, status=status.HTTP_400_BAD_REQUEST)

    if points_amount < 1:
        return Response({'error': 'Minimum 1 point required'}, status=status.HTTP_400_BAD_REQUEST)

    # Check user's point balance (fast, friendly pre-check; the deduction
    # below is the actual safety net under concurrency -- see deduct_points).
    user_profile = request.user.profile
    if user_profile.points < points_amount:
        return Response(
            {'error': f'Insufficient points. You have {user_profile.points} points.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get or create user's coin balance
    coin_balance = _get_or_create_balance(request.user)

    # Both steps succeed together or not at all -- a coin-credit failure
    # after points were already deducted would otherwise strand the user
    # with neither the points nor the coins.
    try:
        with db_transaction.atomic():
            user_profile.deduct_points(points_amount)
            # 1 point = 1 coin. Also creates the CoinTransaction record.
            coin_balance.add_earned(
                points_amount,
                transaction_type='reinvest',
                description=f'Converted {points_amount} points to coins',
            )
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            'message': 'Successfully converted points to coins',
            'points_converted': points_amount,
            'coins_received': points_amount,
            'new_balance': {
                'points': user_profile.points,
                'coins': coin_balance.balance,
                'earned_coins': coin_balance.earned_balance,
            },
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def my_withdrawals(request):
    """List current user's withdrawal requests with pagination."""
    qs = WithdrawalRequest.objects.filter(user=request.user).order_by('-created_at')

    try:
        page = max(int(request.query_params.get('page', 1)), 1)
        page_size = min(max(int(request.query_params.get('page_size', 20)), 1), 100)
    except ValueError:
        page, page_size = 1, 20

    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = qs[start:end]

    return Response(
        {
            'count': total,
            'page': page,
            'page_size': page_size,
            'has_next': end < total,
            'has_prev': page > 1,
            'results': [_serialize_withdrawal(w) for w in items],
        }
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
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

    return Response(
        {
            'message': 'Withdrawal cancelled and coins refunded',
            'withdrawal': _serialize_withdrawal(withdrawal),
            'new_balance': {
                'total': balance.balance,
                'earned': balance.earned_balance,
                'purchased': balance.purchased_balance,
            },
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def public_wallet_config(request):
    """
    Returns public-safe configuration (rates, costs, packages) for frontend display.
    No sensitive admin info.
    """
    config = WalletConfig.get_config()

    try:
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
    except Exception:
        # Table may not exist yet - return default packages
        packages = [
            {
                'id': 1,
                'name': 'Starter Pack',
                'price_etb': '10.0',
                'coin_amount': 100,
                'bonus_coins': 0,
                'total_coins': 100,
                'is_featured': False,
            },
            {
                'id': 2,
                'name': 'Good Value',
                'price_etb': '25.0',
                'coin_amount': 250,
                'bonus_coins': 25,
                'total_coins': 275,
                'is_featured': False,
            },
            {
                'id': 3,
                'name': 'Most Popular',
                'price_etb': '50.0',
                'coin_amount': 500,
                'bonus_coins': 75,
                'total_coins': 575,
                'is_featured': True,
            },
            {
                'id': 4,
                'name': 'Best Deal',
                'price_etb': '100.0',
                'coin_amount': 1000,
                'bonus_coins': 200,
                'total_coins': 1200,
                'is_featured': False,
            },
            {
                'id': 5,
                'name': 'Premium Package',
                'price_etb': '250.0',
                'coin_amount': 2500,
                'bonus_coins': 625,
                'total_coins': 3125,
                'is_featured': False,
            },
        ]

    return Response(
        {
            'currency': 'ETB',
            'currency_label': 'Birr',
            'coins_per_birr': config.coins_per_birr,
            'points_per_birr': config.points_per_birr,
            'withdrawal_min_points': config.withdrawal_min_points,
            'withdrawal_max_points_per_request': config.withdrawal_max_points_per_request,
            'coins_to_points_conversion': config.coins_to_points_conversion,
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
                'share': config.cost_share,
                'gift': config.cost_gift,
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
                'min_points_per_transaction': config.gift_min_points_per_transaction,
                'max_points_per_transaction': config.gift_max_points_per_transaction,
                'max_points_to_recipient_per_day': config.gift_max_points_to_recipient_per_day,
                'max_total_points_sent_per_day': config.gift_max_total_points_sent_per_day,
            },
            'packages': packages,
        }
    )


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
        'daily_login_day1',
        'daily_login_day2',
        'daily_login_day3',
        'daily_login_day4',
        'daily_login_day5',
        'daily_login_day6',
        'daily_login_day7',
        'daily_post_bonus',
        'campaign_join_reward',
        'receive_like_reward',
        'receive_like_daily_cap',
        'quality_comment_reward',
        'quality_comment_daily_cap',
        'profile_complete_reward',
        'referral_reward',
        'campaign_winner_reward',
        'cost_post_create',
        'cost_post_create_long_video',
        'cost_like',
        'cost_comment',
        'cost_share',
        'cost_gift',
        'cost_join_campaign',
        'cost_extra_campaign_entry',
        'cost_boost_1hr',
        'cost_boost_2hr',
        'cost_boost_24hr',
        'cost_trending_1hr',
        'cost_trending_24hr',
        'cost_post_create_non_campaign',
        'cost_post_create_long_video_non_campaign',
        'cost_like_non_campaign',
        'cost_comment_non_campaign',
        'cost_share_non_campaign',
        'cost_gift_non_campaign',
        'cost_boost_1hr_non_campaign',
        'cost_boost_2hr_non_campaign',
        'cost_boost_24hr_non_campaign',
        'cost_trending_1hr_non_campaign',
        'cost_trending_24hr_non_campaign',
        'min_balance_to_post',
        'min_balance_to_join_campaign',
        'withdrawal_enabled',
        'withdrawal_min_coins',
        'withdrawal_max_coins_per_request',
        'coins_per_birr',
        'withdrawal_fee_percent',
        'withdrawal_processing_days',
        'earned_coins_giftable',
        'purchased_coins_giftable',
        'earned_coins_withdrawable',
        'purchased_coins_withdrawable',
        'earned_coins_expire_days',
        'coins_to_points_conversion',
        'points_per_birr',
        'withdrawal_min_points',
        'withdrawal_max_points_per_request',
        'daily_winner_points',
        'weekly_winner_points',
        'monthly_winner_points',
        'grand_finalist_points',
        'grand_winner_points',
        'gift_min_points_per_transaction',
        'gift_max_points_per_transaction',
        'gift_max_points_to_recipient_per_day',
        'gift_max_total_points_sent_per_day',
    ]

    print(f'[WALLET_CONFIG] Request data keys: {list(request.data.keys())}')
    print(
        f"[WALLET_CONFIG] Non-campaign fields in request: {[k for k in request.data.keys() if 'non_campaign' in k]}"
    )

    for field in editable_fields:
        if field in request.data:
            value = request.data[field]
            print(f'[WALLET_CONFIG] Processing {field}={value} (type: {type(value).__name__})')
            if field in ('withdrawal_fee_percent',):
                value = Decimal(str(value))
            elif field.startswith(('earned_coins_', 'purchased_coins_', 'withdrawal_enabled')):
                if isinstance(value, str):
                    value = value.lower() in ('true', '1', 'yes', 'on')
            elif (
                field.startswith('cost_')
                or field.startswith('daily_')
                or field.startswith('min_')
                or field.startswith('max_')
                or field.startswith('coins_per_')
                or field.startswith('points_per_')
                or field.startswith('withdrawal_')
                or field.startswith('gift_')
            ):
                # Convert to integer for cost/points/withdrawal fields
                if isinstance(value, str):
                    try:
                        value = int(value)
                        print(f'[WALLET_CONFIG] Converted {field} to int: {value}')
                    except ValueError:
                        print(f'[WALLET_CONFIG] Failed to convert {field}={value} to int')
            print(f'[WALLET_CONFIG] Setting {field}={value} (type: {type(value).__name__})')
            setattr(config, field, value)

    config.updated_by = request.user
    config.save()

    return Response(
        {
            'message': 'Wallet configuration updated',
            'config': _serialize_full_config(config),
        }
    )


def _serialize_full_config(config):
    return {
        'rewards': {
            'welcome_bonus': config.welcome_bonus,
            'daily_login_day1': config.daily_login_day1,
            'daily_login_day2': config.daily_login_day2,
            'daily_login_day3': config.daily_login_day3,
            'daily_login_day4': config.daily_login_day4,
            'daily_login_day5': config.daily_login_day5,
            'daily_login_day6': config.daily_login_day6,
            'daily_login_day7': config.daily_login_day7,
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
            'post_create_long_video': config.cost_post_create_long_video,
            'like': config.cost_like,
            'comment': config.cost_comment,
            'share': config.cost_share,
            'gift': config.cost_gift,
            'join_campaign': config.cost_join_campaign,
            'extra_campaign_entry': config.cost_extra_campaign_entry,
            'boost_1hr': config.cost_boost_1hr,
            'boost_2hr': config.cost_boost_2hr,
            'boost_24hr': config.cost_boost_24hr,
            'trending_1hr': config.cost_trending_1hr,
            'trending_24hr': config.cost_trending_24hr,
            'post_create_non_campaign': config.cost_post_create_non_campaign,
            'post_create_long_video_non_campaign': config.cost_post_create_long_video_non_campaign,
            'like_non_campaign': config.cost_like_non_campaign,
            'comment_non_campaign': config.cost_comment_non_campaign,
            'share_non_campaign': config.cost_share_non_campaign,
            'gift_non_campaign': config.cost_gift_non_campaign,
            'boost_1hr_non_campaign': config.cost_boost_1hr_non_campaign,
            'boost_2hr_non_campaign': config.cost_boost_2hr_non_campaign,
            'boost_24hr_non_campaign': config.cost_boost_24hr_non_campaign,
            'trending_1hr_non_campaign': config.cost_trending_1hr_non_campaign,
            'trending_24hr_non_campaign': config.cost_trending_24hr_non_campaign,
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
            'min_points_per_transaction': config.gift_min_points_per_transaction,
            'max_points_per_transaction': config.gift_max_points_per_transaction,
            'max_points_to_recipient_per_day': config.gift_max_points_to_recipient_per_day,
            'max_total_points_sent_per_day': config.gift_max_total_points_sent_per_day,
        },
        'expiry': {
            'earned_coins_expire_days': config.earned_coins_expire_days,
        },
        'points': {
            'coins_to_points_conversion': config.coins_to_points_conversion,
            'points_per_birr': config.points_per_birr,
            'withdrawal_min_points': config.withdrawal_min_points,
            'withdrawal_max_points_per_request': config.withdrawal_max_points_per_request,
            'daily_winner_points': config.daily_winner_points,
            'weekly_winner_points': config.weekly_winner_points,
            'monthly_winner_points': config.monthly_winner_points,
            'grand_finalist_points': config.grand_finalist_points,
            'grand_winner_points': config.grand_winner_points,
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

    return Response(
        {
            'count': total,
            'page': page,
            'page_size': page_size,
            'has_next': end < total,
            'summary': summary,
            'results': results,
        }
    )


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_withdrawal_analytics(request):
    """Aggregate withdrawal totals for the admin dashboard."""
    from django.db.models import Avg, Sum
    from django.db.models.functions import Coalesce

    all_withdrawals = WithdrawalRequest.objects.all()

    total_gross = all_withdrawals.aggregate(total=Coalesce(Sum('gross_birr'), Decimal('0.00')))[
        'total'
    ]
    total_fee = all_withdrawals.aggregate(total=Coalesce(Sum('fee_birr'), Decimal('0.00')))['total']
    total_net = all_withdrawals.aggregate(total=Coalesce(Sum('net_birr'), Decimal('0.00')))['total']
    total_count = all_withdrawals.count()

    completed_count = all_withdrawals.filter(status='completed').count()
    pending_count = all_withdrawals.filter(status='pending').count()
    # Master counts a 'failed' status that doesn't exist on this model --
    # WithdrawalRequest.STATUS_CHOICES uses 'rejected'/'cancelled' instead.
    rejected_count = all_withdrawals.filter(status__in=('rejected', 'cancelled')).count()

    avg_withdrawal = all_withdrawals.filter(status='completed').aggregate(
        avg=Coalesce(Avg('net_birr'), Decimal('0.00')),
    )['avg']

    return Response(
        {
            'total_gross_birr': float(total_gross),
            'total_platform_fee_birr': float(total_fee),
            'total_net_birr': float(total_net),
            'total_withdrawals': total_count,
            'completed_count': completed_count,
            'pending_count': pending_count,
            'rejected_count': rejected_count,
            'avg_withdrawal_birr': float(avg_withdrawal),
        }
    )


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_withdrawal_action(request, withdrawal_id):
    """
    Admin action on a withdrawal request.
    Body: { action: 'approve'|'reject'|'mark_processing'|'mark_completed', notes?, payout_reference? }
    """
    action = (request.data.get('action') or '').lower()
    notes = request.data.get('notes', '')
    payout_reference = request.data.get('payout_reference', '')

    if action not in ('approve', 'reject', 'mark_processing', 'mark_completed'):
        return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)

    # Locked for the whole status check + transition. Two admins (or one
    # admin double-clicking) acting on the same withdrawal at once must not
    # both see status=='pending' and both process it as an approval -- the
    # second one has to wait for the first to commit, then see the *new*
    # status and correctly get "cannot approve a now-approved withdrawal"
    # instead of silently repeating the transition.
    try:
        with db_transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)

            if action == 'approve':
                if withdrawal.status != 'pending':
                    return Response(
                        {'error': f'Cannot approve a {withdrawal.status} withdrawal'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                withdrawal.status = 'approved'
                withdrawal.reviewed_at = timezone.now()
                withdrawal.reviewed_by = request.user
                if notes:
                    withdrawal.admin_notes = notes
                withdrawal.save()

            elif action == 'reject':
                if withdrawal.status not in ('pending', 'approved'):
                    return Response(
                        {'error': f'Cannot reject a {withdrawal.status} withdrawal'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                withdrawal.mark_rejected(request.user, reason=notes)

            elif action == 'mark_processing':
                if withdrawal.status not in ('approved',):
                    return Response(
                        {'error': 'Must be approved before processing'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                withdrawal.status = 'processing'
                if notes:
                    withdrawal.admin_notes = notes
                withdrawal.save()

            elif action == 'mark_completed':
                if withdrawal.status not in ('approved', 'processing'):
                    return Response(
                        {'error': 'Must be approved/processing first'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not payout_reference:
                    return Response(
                        {'error': 'payout_reference is required'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                withdrawal.mark_completed(request.user, payout_reference=payout_reference)
                if notes:
                    withdrawal.admin_notes = notes
                    withdrawal.save()
    except WithdrawalRequest.DoesNotExist:
        return Response({'error': 'Withdrawal not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response(
        {
            'message': f'Withdrawal {action} successful',
            'withdrawal': _serialize_withdrawal(withdrawal),
        }
    )


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_user_wallet(request, user_id):
    """Get user wallet data (admin only)."""
    try:
        user = User.objects.get(id=user_id)
        balance = _get_or_create_balance(user)

        # Ensure user has a profile
        if not hasattr(user, 'profile'):
            from api.models import UserProfile

            UserProfile.objects.get_or_create(user=user)
            user.refresh_from_db()

        return Response(
            {
                'balance': {
                    'total': balance.balance,
                    'earned': balance.earned_balance,
                    'purchased': balance.purchased_balance,
                },
                'points': {
                    'current': user.profile.points if hasattr(user, 'profile') else 0,
                    'earned_total': user.profile.points_earned_total
                    if hasattr(user, 'profile')
                    else 0,
                    'withdrawn_total': user.profile.points_withdrawn_total
                    if hasattr(user, 'profile')
                    else 0,
                },
            }
        )
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f'[Admin Wallet] Error for user {user_id}: {str(e)}')
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_user_transactions(request):
    """Get user transaction history (admin only)."""
    user_id = request.query_params.get('user_id')
    if not user_id:
        return Response({'error': 'user_id parameter required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(id=user_id)
        page_size = int(request.query_params.get('page_size', 20))

        transactions = CoinTransaction.objects.filter(user=user).order_by('-created_at')[:page_size]

        data = [
            {
                'id': tx.id,
                'transaction_type': tx.transaction_type,
                'type_display': TRANSACTION_DISPLAY.get(tx.transaction_type, tx.transaction_type),
                'coins': tx.coins if tx.coins is not None else 0,
                'is_credit': tx.coins > 0 if tx.coins is not None else False,
                'created_at': tx.created_at.isoformat() if tx.created_at else None,
                'description': tx.description or '',
                'fee_amount': float(tx.fee_amount) if tx.fee_amount else 0,
                'payment_method': tx.payment_method or '',
            }
            for tx in transactions
        ]

        return Response({'results': data})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        import logging

        logging.error(f'[Admin Transactions] Error for user {user_id}: {str(e)}')
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_all_coin_transactions(request):
    """Get all coin transactions (admin only). Optional ?type=purchase to filter by purchase type."""
    try:
        page_size = int(request.query_params.get('page_size', 50))
        tx_type = request.query_params.get('type')

        qs = CoinTransaction.objects.all().order_by('-created_at')
        if tx_type:
            qs = qs.filter(transaction_type=tx_type)

        transactions = qs[:page_size]

        data = []
        for tx in transactions:
            user_obj = tx.user
            phone = ''
            if (
                user_obj
                and hasattr(user_obj, 'profile')
                and getattr(user_obj.profile, 'phone_number', None)
            ):
                phone = user_obj.profile.phone_number

            data.append(
                {
                    'id': tx.id,
                    'transaction_type': tx.transaction_type,
                    'type_display': TRANSACTION_DISPLAY.get(
                        tx.transaction_type, tx.transaction_type
                    ),
                    'coins': tx.coins if tx.coins is not None else 0,
                    'is_credit': tx.coins > 0 if tx.coins is not None else False,
                    'created_at': tx.created_at.isoformat() if tx.created_at else None,
                    'description': tx.description or '',
                    'fee_amount': float(tx.fee_amount) if tx.fee_amount else 0,
                    'payment_method': tx.payment_method or '',
                    'user': user_obj.username if user_obj else 'N/A',
                    'user_id': user_obj.id if user_obj else None,
                    'email': user_obj.email if user_obj else '',
                    'phone': phone,
                }
            )

        return Response({'results': data, 'count': len(data)})
    except Exception as e:
        import logging

        logging.error(f'[Admin All Transactions] Error: {str(e)}')
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_adjust_balance(request):
    """
    Manually credit or debit a user's wallet (admin only).
    Body: { user_id, amount (positive or negative), bucket: 'earned'|'purchased'|'points', reason }
    """
    try:
        user_id = int(request.data.get('user_id'))
        amount = int(request.data.get('amount'))
    except (TypeError, ValueError):
        return Response({'error': 'Invalid user_id or amount'}, status=status.HTTP_400_BAD_REQUEST)

    bucket = request.data.get('bucket', 'earned')
    reason = request.data.get('reason', 'Admin adjustment')

    if bucket not in ('earned', 'purchased', 'points'):
        return Response(
            {'error': 'bucket must be earned, purchased, or points'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    # Handle points adjustment
    if bucket == 'points':
        profile = user.profile
        try:
            if amount >= 0:
                profile.add_points(amount)
            else:
                profile.deduct_points(abs(amount), total_field='points_withdrawn_total')
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'message': f"Adjusted {user.username}'s points by {amount}",
                'new_points': profile.points,
            }
        )

    # Handle coin balance adjustment
    balance = _get_or_create_balance(user)

    try:
        if amount >= 0:
            if bucket == 'earned':
                balance.add_earned(amount, transaction_type='admin_adjustment', description=reason)
            else:
                balance.add_purchased(
                    amount, transaction_type='admin_adjustment', description=reason
                )
        else:
            balance.deduct_from_bucket(
                bucket, abs(amount), transaction_type='admin_adjustment', description=reason
            )
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            'message': f"Adjusted {user.username}'s {bucket} balance by {amount}",
            'new_balance': {
                'total': balance.balance,
                'earned': balance.earned_balance,
                'purchased': balance.purchased_balance,
            },
        }
    )


# ---------------------------------------------------------------------------
# Telebirr Payment Integration
# ---------------------------------------------------------------------------


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def telebirr_initiate_payment(request):
    """
    Create a Telebirr H5 (InApp) prepaid order for a coin purchase.

    Body: { package_id }
    Returns a signed `raw_request` string that the H5 page must hand to the
    SuperApp via window.consumerapp.evaluate(js_fun_start_pay) -- this is
    the real Telebirr H5/Fabric flow, not a browser redirect. See
    api/integrations/telebirr/checkout.py's module docstring.
    """
    package_id = request.data.get('package_id')

    if not package_id:
        return Response({'error': 'package_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        package = CoinPackage.objects.get(id=package_id, is_active=True)
    except CoinPackage.DoesNotExist:
        return Response(
            {'error': 'Package not found or inactive'}, status=status.HTTP_404_NOT_FOUND
        )

    total_amount = f'{float(package.price_etb):.2f}'

    # create_order_ondemand: coin purchases have no payee fields (unlike
    # subscription mandates), matching Telebirr's on-demand order shape.
    result = telebirr_service.create_order_ondemand(
        title=package.name,
        amount=total_amount,
        trade_type='InApp',
    )

    if not result.get('success'):
        return Response(
            {
                'error': result.get('error', 'Payment initiation failed'),
                'details': result,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    merch_order_id = result.get('merch_order_id')

    # Record a pending transaction keyed by merch_order_id so the async
    # notify webhook can resolve it later.
    CoinTransaction.objects.create(
        user=request.user,
        transaction_type='purchase',
        coins=0,  # credited after payment confirmation
        payment_method='telebirr',
        payment_reference=merch_order_id,
        package=package,
        description=f'Pending Telebirr H5 payment for {package.name}',
        is_successful=False,
    )

    return Response(
        {
            'success': True,
            'raw_request': result.get('raw_request'),
            'merch_order_id': merch_order_id,
            'prepay_id': result.get('prepay_id'),
            'amount': total_amount,
            'package': {
                'id': package.id,
                'name': package.name,
                'coin_amount': package.coin_amount,
                'bonus_coins': package.bonus_coins,
                'total_coins': package.get_total_coins(),
            },
            'message': 'Order created. Call js_fun_start_pay with raw_request.',
        }
    )


def _credit_telebirr_order(merch_order_id, payment_order_id=None):
    """
    Idempotently credit coins for a completed Telebirr H5 order.

    Single-row design (unlike the double-row pattern the older SOAP-callback
    path below still uses, protected by migration 0089's constraint): the
    pending CoinTransaction created at order time is the only row this path
    ever writes, finalized in place rather than paired with a second ledger
    row from add_purchased(). Locks it for the duration of the update so a
    duplicate or concurrent webhook delivery (Telebirr is documented to
    retry) can't credit the same order twice -- the second caller's
    select_for_update().get(..., is_successful=False) finds nothing once the
    first has flipped the flag, and takes the "already processed" path.

    Returns (handled: bool, coins_added: int).
    """
    with db_transaction.atomic():
        try:
            coin_tx = CoinTransaction.objects.select_for_update().get(
                payment_reference=merch_order_id,
                payment_method='telebirr',
                is_successful=False,
            )
        except CoinTransaction.DoesNotExist:
            return False, 0

        package = coin_tx.package
        total_coins = package.get_total_coins() if package else 0

        balance = UserCoinBalance.objects.select_for_update().get(user=coin_tx.user)
        balance.telebirr_purchased_balance = (balance.telebirr_purchased_balance or 0) + total_coins
        balance.total_telebirr_purchased = (balance.total_telebirr_purchased or 0) + total_coins
        balance.total_purchased = (balance.total_purchased or 0) + total_coins
        balance._sync_balance()
        balance.save(
            update_fields=[
                'telebirr_purchased_balance',
                'purchased_balance',
                'balance',
                'total_purchased',
                'total_telebirr_purchased',
                'updated_at',
            ]
        )

        coin_tx.coins = total_coins
        coin_tx.is_successful = True
        coin_tx.payment_reference = payment_order_id or merch_order_id
        coin_tx.description = (
            f'Successful Telebirr payment for {package.name if package else "Unknown"}'
        )
        coin_tx.save()

    return True, total_coins


@api_view(['POST'])
@permission_classes([AllowAny])  # Telebirr calls this without authentication
def telebirr_callback(request):
    """
    Handle the Telebirr async payment notification (notify_url webhook).
    Verifies the SP signature, then credits coins on a Completed payment.
    """
    notify = telebirr_service.verify_notify(request.data)

    if not notify.get('verified'):
        logger.error('[TELEBIRR CALLBACK] Invalid signature for callback: %s', request.data)
        return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

    merch_order_id = notify.get('merch_order_id')
    if not merch_order_id:
        return Response({'error': 'Missing merch_order_id'}, status=status.HTTP_400_BAD_REQUEST)

    # Subscription orders share this webhook but are credited differently
    # (activate a SubscriptionPlan, not a coin balance) -- delegate.
    if merch_order_id.startswith('SUB'):
        from api.views.subscription import telebirr_one_time_callback

        return telebirr_one_time_callback(request)

    if not notify.get('is_paid'):
        CoinTransaction.objects.filter(
            payment_reference=merch_order_id,
            payment_method='telebirr',
            is_successful=False,
        ).update(description=f'Failed Telebirr payment: {notify.get("trade_status")}')
        return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'received'})

    handled, coins_added = _credit_telebirr_order(
        merch_order_id, payment_order_id=notify.get('payment_order_id')
    )

    if not handled:
        # Either unknown order or already processed (idempotent OK).
        return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'already processed'})

    return Response(
        {'result': 'SUCCESS', 'code': '0', 'msg': 'success', 'coins_added': coins_added}
    )


@api_view(['POST'])
@permission_classes([AllowAny])
@encrypted_endpoint
def telebirr_auth(request):
    """
    Telebirr SuperApp auto-login endpoint.

    Accepts an access_token from the SuperApp, exchanges it for the user's
    phone number via telebirr_service.request_auth_token, and logs in or
    (for a phone number never seen before) creates a minimal account for
    SuperApp onboarding -- the frontend still routes a new user to the
    subscription page (requires_subscription=True) before granting full access.
    """
    access_token = request.data.get('access_token')
    if not access_token:
        return Response({'error': 'access_token is required'}, status=status.HTTP_400_BAD_REQUEST)

    auth_result = telebirr_service.request_auth_token(access_token)
    if not auth_result.get('success'):
        return Response(
            {'error': auth_result.get('error', 'Failed to get user info from Telebirr')},
            status=status.HTTP_400_BAD_REQUEST,
        )

    phone_number = auth_result.get('identifier')
    if not phone_number:
        return Response(
            {'error': 'No phone number returned from Telebirr'}, status=status.HTTP_400_BAD_REQUEST
        )

    phone_number = ''.join(filter(str.isdigit, phone_number))

    phone_variants = {phone_number}
    if phone_number.startswith('251'):
        phone_variants.add('0' + phone_number[3:])
    elif phone_number.startswith('0'):
        phone_variants.add('251' + phone_number[1:])

    profile = UserProfile.objects.filter(phone_number__in=phone_variants).first()

    telebirr_info = {
        'open_id': auth_result.get('open_id'),
        'identityId': auth_result.get('identityId'),
        'identifier': auth_result.get('identifier'),
        'nickName': auth_result.get('nickName'),
    }

    if profile:
        user = profile.user
        token, _created = Token.objects.get_or_create(user=user)
        return Response(
            {'user': UserSerializer(user).data, 'token': token.key, 'telebirr_info': telebirr_info}
        )

    # New phone number: create a minimal account (username = phone number)
    # so the SuperApp session has something to auto-login into, but still
    # require the subscription step before granting real access.
    user, _created = User.objects.get_or_create(username=phone_number)
    profile, profile_created = UserProfile.objects.get_or_create(
        user=user, defaults={'phone_number': phone_number}
    )
    if not profile_created and not profile.phone_number:
        profile.phone_number = phone_number
        profile.save()
    UserCoinBalance.objects.get_or_create(user=user)

    token, _created = Token.objects.get_or_create(user=user)
    return Response(
        {
            'user': UserSerializer(user).data,
            'token': token.key,
            'telebirr_info': telebirr_info,
            'requires_subscription': True,
            'phone_number': phone_number,
            'is_new_user': True,
        },
        status=status.HTTP_401_UNAUTHORIZED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def telebirr_query_order(request):
    """
    Query a Telebirr H5 order's status and credit coins if paid -- a
    fallback for when the async notify webhook was not received.
    Query param: ?merch_order_id=<id>
    """
    merch_order_id = request.query_params.get('merch_order_id')
    if not merch_order_id:
        return Response({'error': 'merch_order_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    result = telebirr_service.query_order(merch_order_id)
    if not result.get('success'):
        return Response(
            {'error': result.get('error', 'Query failed'), 'details': result},
            status=status.HTTP_400_BAD_REQUEST,
        )

    coins_added = 0
    if result.get('is_paid'):
        _, coins_added = _credit_telebirr_order(
            merch_order_id, payment_order_id=result.get('payment_order_id')
        )

    return Response(
        {
            'success': True,
            'is_paid': result.get('is_paid'),
            'trade_status': result.get('trade_status'),
            'order_status': result.get('order_status'),
            'merch_order_id': merch_order_id,
            'payment_order_id': result.get('payment_order_id'),
            'coins_added': coins_added,
        }
    )


# ---------------------------------------------------------------------------
# USSD Push Coin Purchase (BuyGoodsForCustomer) -- parallel to the H5/InApp
# flow above; same CoinTransaction/UserCoinBalance crediting shape, keyed by
# originator_conversation_id instead of merch_order_id and payment_method
# 'telebirr_ussd' instead of 'telebirr' so the two pending-transaction
# lookups never collide.
# ---------------------------------------------------------------------------


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def telebirr_ussd_purchase(request):
    """Initiate a USSD Push payment (BuyGoodsForCustomer) for a coin purchase."""
    package_id = request.data.get('package_id')
    if not package_id:
        return Response({'error': 'package_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        package = CoinPackage.objects.get(id=package_id, is_active=True)
    except CoinPackage.DoesNotExist:
        return Response(
            {'error': 'Package not found or inactive'}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        phone_number = request.user.profile.phone_number
    except UserProfile.DoesNotExist:
        return Response({'error': 'User profile not found'}, status=status.HTTP_404_NOT_FOUND)
    if not phone_number:
        return Response(
            {'error': 'Phone number not found in profile'}, status=status.HTTP_400_BAD_REQUEST
        )

    normalized_phone = _normalize_ethiopian_phone(phone_number)
    if normalized_phone:
        phone_number = normalized_phone

    amount = f'{float(package.price_etb):.2f}'
    coins = package.get_total_coins()

    result = telebirr_direct_debit_service.initiate_ussd_push_payment(
        amount=amount,
        phone_number=phone_number,
        coins=coins,
    )
    if not result.get('success'):
        return Response(
            {
                'error': result.get('error', 'USSD Push payment initiation failed'),
                'details': result,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    CoinTransaction.objects.create(
        user=request.user,
        transaction_type='purchase',
        coins=0,  # credited after payment confirmation
        payment_method='telebirr_ussd',
        payment_reference=result.get('originator_conversation_id'),
        package=package,
        description=f'Pending USSD Push payment for {package.name}',
        is_successful=False,
    )

    return Response(
        {
            'success': True,
            'originator_conversation_id': result.get('originator_conversation_id'),
            'conversation_id': result.get('conversation_id'),
            'message': result.get('message'),
            'package': {
                'id': package.id,
                'name': package.name,
                'coin_amount': package.coin_amount,
                'bonus_coins': package.bonus_coins,
                'total_coins': coins,
            },
        }
    )


def _credit_telebirr_ussd_order(originator_conversation_id, transaction_id=None):
    """USSD-Push counterpart to _credit_telebirr_order -- same locked,
    idempotent single-row crediting, keyed by originator_conversation_id and
    payment_method='telebirr_ussd' instead of merch_order_id/'telebirr'.

    Returns (handled: bool, coins_added: int).
    """
    with db_transaction.atomic():
        try:
            coin_tx = CoinTransaction.objects.select_for_update().get(
                payment_reference=originator_conversation_id,
                payment_method='telebirr_ussd',
                is_successful=False,
            )
        except CoinTransaction.DoesNotExist:
            return False, 0

        package = coin_tx.package
        total_coins = package.get_total_coins() if package else 0

        balance = UserCoinBalance.objects.select_for_update().get(user=coin_tx.user)
        balance.telebirr_purchased_balance = (balance.telebirr_purchased_balance or 0) + total_coins
        balance.total_telebirr_purchased = (balance.total_telebirr_purchased or 0) + total_coins
        balance.total_purchased = (balance.total_purchased or 0) + total_coins
        balance._sync_balance()
        balance.save(
            update_fields=[
                'telebirr_purchased_balance',
                'purchased_balance',
                'balance',
                'total_purchased',
                'total_telebirr_purchased',
                'updated_at',
            ]
        )

        coin_tx.coins = total_coins
        coin_tx.is_successful = True
        coin_tx.payment_reference = transaction_id or originator_conversation_id
        coin_tx.description = (
            f'Successful USSD Push payment for {package.name if package else "Unknown"}'
        )
        coin_tx.save()

    return True, total_coins


@api_view(['POST'])
@permission_classes([AllowAny])  # Telebirr calls this without authentication
def telebirr_ussd_webhook(request):
    """Handle the USSD Push payment result webhook (SOAP Result envelope)."""
    from api.views.direct_debit import _parse_telebirr_soap_result

    raw_body = request.body or b''
    logger.info(
        '[USSD WEBHOOK] Received callback. Content-Type: %s, Body: %s',
        request.META.get('CONTENT_TYPE'),
        raw_body[:2000],
    )

    parsed = _parse_telebirr_soap_result(raw_body)
    originator_conversation_id = parsed['OriginatorConversationID']
    result_type = parsed['ResultType']
    result_code = parsed['ResultCode']
    result_desc = parsed['ResultDesc']
    transaction_id = parsed['TransactionID']

    is_success = result_code == '0' and result_type == '0'

    if not is_success:
        logger.warning('[USSD WEBHOOK] Payment failed: %s', result_desc)
        CoinTransaction.objects.filter(
            payment_reference=originator_conversation_id,
            payment_method='telebirr_ussd',
            is_successful=False,
        ).update(description=f'Failed USSD Push payment: {result_desc}')
        return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'received'})

    handled, coins_added = _credit_telebirr_ussd_order(
        originator_conversation_id, transaction_id=transaction_id
    )

    if not handled:
        # No coin order matched -- try the subscription flow before giving up.
        #
        # Telebirr registers ONE Result Address per merchant, so this endpoint
        # receives coin AND subscription confirmations. Returning early here
        # discarded every subscription callback: the conversation id has no
        # CoinTransaction, so `handled` was False and the payment was dropped
        # with a 200. That is why 29 subscriptions sat pending while coins
        # occasionally succeeded -- the callbacks arrived and were thrown away.
        from api.models import SubscriptionPayment
        from api.views.subscription import _activate_ussd_subscription_payment

        payment = (
            SubscriptionPayment.objects.select_related('subscription', 'subscription__tier')
            .filter(
                onevas_transaction_id=originator_conversation_id,
                payment_method='telebirr',
                status='pending',
            )
            .first()
        )
        if payment is not None:
            tier = payment.subscription.tier if payment.subscription else None
            _activate_ussd_subscription_payment(payment, tier)
            logger.info('[USSD WEBHOOK] Activated subscription for %s', originator_conversation_id)
            return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'subscription activated'})

        # Genuinely unknown, or already processed -- idempotent OK either way.
        return Response(
            {'result': 'SUCCESS', 'code': '0', 'msg': 'transaction not found or already processed'}
        )

    return Response(
        {'result': 'SUCCESS', 'code': '0', 'msg': 'success', 'coins_added': coins_added}
    )
