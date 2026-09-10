"""Onevas charging API views for on-demand subscription purchases"""

import logging
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models.contest import CoinTransaction, UserCoinBalance
from common.security import encrypted_endpoint
from common.validators import AIRTIME, validate_pay_method

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def initiate_on_demand_charging(request):
    """
    DISABLED: Ethio Telecom SIM cards are only accessible for SMS OTP purposes.
    On-demand charging has been disabled to ensure phone numbers are used solely for OTP verification.
    """
    return Response(
        {
            'error': 'On-demand charging is disabled. Ethio Telecom SIM cards are only accessible for SMS OTP verification.'
        },
        status=status.HTTP_403_FORBIDDEN,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_charging_statistics(request):
    """
    Get charging statistics (admin only) - queries CoinTransaction for on-demand airtime purchases

    Query params:
    - days: number of days to look back (default: 3650 = 10 years to show all)
    """
    try:
        # Check if user is admin
        if not request.user.is_staff:
            return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

        days = int(request.GET.get('days', 3650))  # Default to 10 years to show all
        start_date = timezone.now() - timedelta(days=days)

        # Query CoinTransaction for on-demand airtime purchases
        base_filter = (
            Q(transaction_type='purchase')
            & Q(payment_method='airtime')
            & Q(created_at__gte=start_date)
        )

        # Get statistics
        total_transactions = CoinTransaction.objects.filter(base_filter).count()

        successful_transactions = CoinTransaction.objects.filter(
            base_filter & Q(is_successful=True)
        ).count()

        failed_transactions = CoinTransaction.objects.filter(
            base_filter & Q(is_successful=False)
        ).count()

        # Calculate total coins purchased
        total_coins = (
            CoinTransaction.objects.filter(base_filter & Q(is_successful=True)).aggregate(
                total=Sum('coins')
            )['total']
            or 0
        )

        # Calculate total amount (ETB) - assuming 10 ETB = 100 coins ratio
        total_amount_etb = (total_coins / 10) if total_coins else 0

        success_rate = (
            (successful_transactions / total_transactions * 100) if total_transactions > 0 else 0
        )

        # Daily statistics for charts
        daily_stats = []
        for i in range(min(days, 30)):  # Limit to 30 days for chart
            date = (timezone.now() - timedelta(days=days - i - 1)).date()
            day_transactions = CoinTransaction.objects.filter(
                base_filter & Q(created_at__date=date)
            ).aggregate(
                total=Count('id'),
                success=Count('id', filter=Q(is_successful=True)),
                coins=Sum('coins', filter=Q(is_successful=True)),
            )

            daily_stats.append(
                {
                    'date': date.isoformat(),
                    'total': day_transactions['total'] or 0,
                    'success': day_transactions['success'] or 0,
                    'coins': int(day_transactions['coins'] or 0),
                    'amount': float((day_transactions['coins'] or 0) / 10),
                }
            )

        return Response(
            {
                'period_days': days,
                'total_transactions': total_transactions,
                'successful_transactions': successful_transactions,
                'failed_transactions': failed_transactions,
                'insufficient_balance': 0,  # Not applicable for CoinTransaction
                'expected_collection': total_amount_etb,
                'actual_collection': total_amount_etb,
                'success_rate': round(success_rate, 2),
                'daily_statistics': daily_stats,
            }
        )

    except Exception as e:
        logger.error(f'[Charging Statistics] Error: {str(e)}')
        return Response(
            {'error': 'Internal server error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_charging_transactions(request):
    """
    Get charging transactions (admin only) - queries CoinTransaction for on-demand airtime purchases

    Query params:
    - status: filter by status (successful/failed)
    - days: number of days to look back (default: 3650 = 10 years to show all)
    - page: page number
    - page_size: items per page
    """
    try:
        # Check if user is admin
        if not request.user.is_staff:
            return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

        status_filter = request.GET.get('status')
        days = int(request.GET.get('days', 3650))  # Default to 10 years to show all transactions
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))

        start_date = timezone.now() - timedelta(days=days)

        # Query CoinTransaction for on-demand airtime purchases
        base_filter = (
            Q(transaction_type='purchase')
            & Q(payment_method='airtime')
            & Q(created_at__gte=start_date)
        )
        queryset = (
            CoinTransaction.objects.filter(base_filter)
            .select_related('user', 'user__profile')
            .order_by('-created_at')
        )

        if status_filter:
            if status_filter == 'successful':
                queryset = queryset.filter(is_successful=True)
            elif status_filter == 'failed':
                queryset = queryset.filter(is_successful=False)

        total_count = queryset.count()
        offset = (page - 1) * page_size
        transactions = queryset[offset : offset + page_size]

        transactions_data = []
        for t in transactions:
            # Get user phone from user profile if available
            phone = getattr(t.user, 'phone', '') or ''

            transactions_data.append(
                {
                    'id': str(t.id),
                    'user': t.user.username,
                    'phone_number': phone,
                    'subscription_tier': None,  # Not applicable for coin purchases
                    'amount_etb': float(t.coins / 10) if t.coins else 0,  # 10 ETB = 100 coins
                    'status': 'success' if t.is_successful else 'failed',
                    'transaction_id': t.payment_reference,
                    'error_message': t.description if not t.is_successful else '',
                    'created_at': t.created_at.isoformat(),
                    'updated_at': t.created_at.isoformat(),
                    'coins': t.coins,
                }
            )

        return Response(
            {
                'total': total_count,
                'page': page,
                'page_size': page_size,
                'transactions': transactions_data,
            }
        )

    except Exception as e:
        logger.error(f'[Charging Transactions] Error: {str(e)}')
        return Response(
            {'error': 'Internal server error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def purchase_coins_on_demand(request):
    """
    Buy a coin package with airtime, charged through TIMWE chargeAmount.

    OFF unless TIMWE_AIRTIME_PURCHASE_ENABLED is set. It was disabled by policy
    -- "Ethio Telecom SIM cards are only accessible for SMS OTP verification"
    -- and switching it on reverses that policy, which is a business decision
    rather than a deployment detail. With the flag off this answers exactly as
    it always has.

    With it on, the client sends only ``package_id`` and an idempotency key.
    The price comes from the package and the number charged is the account's
    own; see api/services/timwe_charging.py.

    The price rule is enforced *before* the flag check on purpose. Airtime is
    only permitted for a 10 ETB purchase (see common/validators/payment.py);
    putting the check here means the constraint holds whichever way the flag
    is set, rather than being something a future change has to remember.
    """
    from django.conf import settings

    price_etb = (
        request.data.get('price_etb')
        or request.data.get('amount')
        or request.data.get('amount_etb')
    )
    if price_etb is not None:
        # Raises ValidationError (400) when airtime is not allowed at this
        # price; the DRF exception handler renders it.
        validate_pay_method(AIRTIME, price_etb)

    if not getattr(settings, 'TIMWE_AIRTIME_PURCHASE_ENABLED', False):
        return Response(
            {
                'error': 'Coin purchase via airtime charging is disabled. Ethio Telecom SIM cards are only accessible for SMS OTP verification.'
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    return _purchase_coins_with_timwe(request)


def _purchase_coins_with_timwe(request):
    """The enabled path. A POST handler only -- never reached by a read."""
    from api.integrations.timwe.errors import TimweConfigurationError
    from api.models.contest import CoinPackage
    from api.services.timwe_charging import (
        AirtimePurchaseRefused,
        ChargeRefused,
        purchase_coins_with_airtime,
        user_message,
    )

    # Required, and supplied by the client: only the client knows that two
    # requests are the same purchase. Without it a double tap is two charges,
    # and a server-generated key would be different on each of them.
    idempotency_key = (
        request.headers.get('Idempotency-Key') or request.data.get('idempotency_key') or ''
    ).strip()
    if not idempotency_key:
        return Response(
            {'error': 'An Idempotency-Key is required.', 'code': 'IDEMPOTENCY_KEY_REQUIRED'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(idempotency_key) > 255:
        return Response(
            {'error': 'Idempotency-Key is too long.', 'code': 'IDEMPOTENCY_KEY_INVALID'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    package_id = request.data.get('package_id')
    package = (
        CoinPackage.objects.filter(pk=package_id, is_active=True).first() if package_id else None
    )
    if package is None:
        return Response(
            {'error': 'Choose a valid coin package.', 'code': 'PACKAGE_NOT_FOUND'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        result, coin_transaction = purchase_coins_with_airtime(
            user=request.user,
            package=package,
            idempotency_key=idempotency_key,
        )
    except TimweConfigurationError:
        # Details stay in the server log. The client is told only that the
        # method is unavailable -- setting names are internal.
        logger.error('TIMWE airtime purchase attempted while charging is not configured')
        return Response(
            {
                'error': 'Airtime payments are temporarily unavailable.',
                'code': 'AIRTIME_UNAVAILABLE',
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except (ChargeRefused, AirtimePurchaseRefused) as exc:
        return Response(
            {'error': str(exc), 'code': 'PURCHASE_REFUSED'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    charge = result.transaction
    body = {
        'success': result.succeeded,
        'status': charge.status,
        'reference_code': charge.reference_code,
        'message': user_message(result),
        'replayed': not result.created,
    }

    if result.succeeded:
        balance = UserCoinBalance.objects.filter(user=request.user).first()
        body['coins_credited'] = package.get_total_coins()
        body['balance'] = balance.balance if balance else None
        return Response(body, status=status.HTTP_200_OK)

    if result.is_ambiguous:
        # 202: accepted for processing, outcome not yet known. Not an error --
        # the client must not treat it as one and retry, which is exactly how
        # an ambiguous charge becomes a double one.
        body['code'] = 'PAYMENT_CONFIRMING'
        return Response(body, status=status.HTTP_202_ACCEPTED)

    body['code'] = 'PAYMENT_FAILED'
    body['can_retry'] = result.can_retry_with_new_key
    return Response(
        body,
        status=(
            status.HTTP_503_SERVICE_UNAVAILABLE
            if charge.outcome == 'unreachable'
            else status.HTTP_402_PAYMENT_REQUIRED
        ),
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def search_charging_transactions(request):
    """
    Search charging transactions by phone number or user ID (admin only) - queries CoinTransaction

    Query params:
    - phone: phone number to search
    - user_id: user ID to search
    """
    try:
        # Check if user is admin
        if not request.user.is_staff:
            return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

        phone = request.GET.get('phone')
        user_id = request.GET.get('user_id')

        if not phone and not user_id:
            return Response(
                {'error': 'Either phone or user_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Query CoinTransaction for on-demand airtime purchases
        base_filter = Q(transaction_type='purchase') & Q(payment_method='airtime')
        queryset = (
            CoinTransaction.objects.filter(base_filter)
            .select_related('user', 'user__profile')
            .order_by('-created_at')
        )

        if phone:
            # Search by phone in user profile
            queryset = queryset.filter(user__profile__phone_number__contains=phone)

        if user_id:
            try:
                user_id_int = int(user_id)
                queryset = queryset.filter(user_id=user_id_int)
            except ValueError:
                return Response(
                    {'error': 'Invalid user_id format'}, status=status.HTTP_400_BAD_REQUEST
                )

        transactions = queryset[:100]  # Limit to 100 results

        transactions_data = []
        for t in transactions:
            # Get user phone from user profile
            phone = ''
            if hasattr(t.user, 'profile'):
                phone = getattr(t.user.profile, 'phone_number', '') or ''

            transactions_data.append(
                {
                    'id': str(t.id),
                    'user_id': t.user.id,
                    'user': t.user.username,
                    'phone_number': phone,
                    'subscription_tier': None,  # Not applicable for coin purchases
                    'amount_etb': float(t.coins / 10) if t.coins else 0,
                    'status': 'success' if t.is_successful else 'failed',
                    'transaction_id': t.payment_reference,
                    'error_message': t.description if not t.is_successful else '',
                    'created_at': t.created_at.isoformat(),
                    'updated_at': t.created_at.isoformat(),
                    'coins': t.coins,
                }
            )

        return Response({'total': len(transactions_data), 'transactions': transactions_data})

    except Exception as e:
        logger.error(f'[Charging Search] Error: {str(e)}')
        return Response(
            {'error': 'Internal server error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_charging_analytics(request):
    """
    Get charging analytics by period (admin only) - queries CoinTransaction for on-demand airtime purchases

    Query params:
    - period: daily, monthly, yearly
    """
    try:
        # Check if user is admin
        if not request.user.is_staff:
            return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

        period = request.GET.get('period', 'daily')

        if period not in ['daily', 'monthly', 'yearly']:
            return Response(
                {'error': 'Invalid period. Must be daily, monthly, or yearly'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine date range based on period
        now = timezone.now()
        if period == 'daily':
            start_date = now - timedelta(days=30)
        elif period == 'monthly':
            start_date = now - timedelta(days=365)
        else:  # yearly
            start_date = now - timedelta(days=365 * 5)

        # Query CoinTransaction for on-demand airtime purchases
        base_filter = (
            Q(transaction_type='purchase')
            & Q(payment_method='airtime')
            & Q(created_at__gte=start_date)
        )

        # Get total statistics
        total_transactions = CoinTransaction.objects.filter(base_filter).count()

        successful = CoinTransaction.objects.filter(base_filter & Q(is_successful=True)).count()

        failed = CoinTransaction.objects.filter(base_filter & Q(is_successful=False)).count()

        total_coins = (
            CoinTransaction.objects.filter(base_filter & Q(is_successful=True)).aggregate(
                total=Sum('coins')
            )['total']
            or 0
        )
        total_revenue = (total_coins / 10) if total_coins else 0  # 10 ETB = 100 coins

        success_rate = (successful / total_transactions * 100) if total_transactions > 0 else 0

        # Get period-wise breakdown
        if period == 'daily':
            breakdown = []
            for i in range(30):
                date = (now - timedelta(days=29 - i)).date()
                day_stats = CoinTransaction.objects.filter(
                    base_filter & Q(created_at__date=date)
                ).aggregate(
                    total=Count('id'),
                    success=Count('id', filter=Q(is_successful=True)),
                    failed=Count('id', filter=Q(is_successful=False)),
                    coins=Sum('coins', filter=Q(is_successful=True)),
                )
                breakdown.append(
                    {
                        'date': date.isoformat(),
                        'total': day_stats['total'] or 0,
                        'success': day_stats['success'] or 0,
                        'failed': day_stats['failed'] or 0,
                        'revenue': float((day_stats['coins'] or 0) / 10),
                    }
                )
        elif period == 'monthly':
            breakdown = []
            for i in range(12):
                month_date = now - timedelta(days=30 * (11 - i))
                month_stats = CoinTransaction.objects.filter(
                    base_filter
                    & Q(created_at__year=month_date.year, created_at__month=month_date.month)
                ).aggregate(
                    total=Count('id'),
                    success=Count('id', filter=Q(is_successful=True)),
                    failed=Count('id', filter=Q(is_successful=False)),
                    coins=Sum('coins', filter=Q(is_successful=True)),
                )
                breakdown.append(
                    {
                        'month': f'{month_date.year}-{month_date.month:02d}',
                        'total': month_stats['total'] or 0,
                        'success': month_stats['success'] or 0,
                        'failed': month_stats['failed'] or 0,
                        'revenue': float((month_stats['coins'] or 0) / 10),
                    }
                )
        else:  # yearly
            breakdown = []
            for i in range(5):
                year_date = now - timedelta(days=365 * (4 - i))
                year_stats = CoinTransaction.objects.filter(
                    base_filter & Q(created_at__year=year_date.year)
                ).aggregate(
                    total=Count('id'),
                    success=Count('id', filter=Q(is_successful=True)),
                    failed=Count('id', filter=Q(is_successful=False)),
                    coins=Sum('coins', filter=Q(is_successful=True)),
                )
                breakdown.append(
                    {
                        'year': str(year_date.year),
                        'total': year_stats['total'] or 0,
                        'success': year_stats['success'] or 0,
                        'failed': year_stats['failed'] or 0,
                        'revenue': float((year_stats['coins'] or 0) / 10),
                    }
                )

        return Response(
            {
                'period': period,
                'total_transactions': total_transactions,
                'successful': successful,
                'failed': failed,
                'insufficient_balance': 0,  # Not applicable for CoinTransaction
                'total_revenue': float(total_revenue),
                'success_rate': round(success_rate, 2),
                'breakdown': breakdown,
            }
        )

    except Exception as e:
        logger.error(f'[Charging Analytics] Error: {str(e)}')
        return Response(
            {'error': 'Internal server error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
