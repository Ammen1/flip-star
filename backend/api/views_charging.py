"""Onevas charging API views for on-demand subscription purchases"""
from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Count, Sum, Q, F
from datetime import timedelta, datetime

from .models_subscription import SubscriptionTier, OnevasChargingTransaction, SubscriptionPlan
from .models_contest import UserCoinBalance, CoinTransaction
from .onevas_charging_service import onevas_charging_service
import logging

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_on_demand_charging(request):
    """
    Initiate on-demand charging for subscription purchase
    
    Payload:
    {
        "subscription_tier_id": "uuid",
        "phone_number": "2519..."
    }
    """
    try:
        tier_id = request.data.get('subscription_tier_id')
        phone_number = request.data.get('phone_number')
        
        if not tier_id or not phone_number:
            return Response(
                {'error': 'subscription_tier_id and phone_number are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the subscription tier
        tier = SubscriptionTier.objects.filter(id=tier_id).first()
        if not tier:
            return Response(
                {'error': 'Subscription tier not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Only allow on-demand subscriptions
        if tier.duration_type != 'ondemand':
            return Response(
                {'error': 'Only on-demand subscriptions can use charging'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create charging transaction record
        transaction = OnevasChargingTransaction.objects.create(
            user=request.user,
            phone_number=phone_number,
            product_number=tier.product_id,
            application_key=tier.application_key,
            subscription_tier=tier,
            amount_etb=tier.price_etb,
            status='pending'
        )
        
        # Initiate charging with Onevas
        charging_response = onevas_charging_service.initiate_charging(
            phone_number=phone_number,
            product_number=tier.product_id,
            application_key=tier.application_key
        )
        
        # Update transaction with response
        transaction.response_status = charging_response.get('status_code')
        transaction.response_body = charging_response.get('data')
        
        # Parse response to determine status
        parsed_status, error_message = onevas_charging_service.parse_charging_response(charging_response)
        transaction.status = parsed_status
        transaction.error_message = error_message
        
        if charging_response.get('data') and charging_response['data'].get('transaction_id'):
            transaction.transaction_id = charging_response['data']['transaction_id']
        
        transaction.save()
        
        # If charging successful, create subscription
        if parsed_status == 'success':
            subscription = SubscriptionPlan.objects.create(
                user=request.user,
                tier=tier,
                status='active',
                start_date=timezone.now(),
                # On-demand has no end date
            )
            
            return Response({
                'success': True,
                'message': 'Subscription activated successfully',
                'transaction_id': str(transaction.id),
                'subscription_id': str(subscription.id),
                'amount_charged': float(tier.price_etb)
            }, status=status.HTTP_201_CREATED)
        
        # If insufficient balance
        elif parsed_status == 'insufficient_balance':
            return Response({
                'success': False,
                'error': 'insufficient_balance',
                'message': 'Your balance is not enough to complete this charge',
                'transaction_id': str(transaction.id)
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # If failed
        else:
            return Response({
                'success': False,
                'error': 'charging_failed',
                'message': error_message or 'Charging failed',
                'transaction_id': str(transaction.id)
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"[Charging] Error: {str(e)}")
        return Response(
            {'error': 'Internal server error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_charging_statistics(request):
    """
    Get charging statistics (admin only)
    
    Query params:
    - days: number of days to look back (default: 30)
    """
    try:
        # Check if user is admin
        if not request.user.is_staff:
            return Response(
                {'error': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        # Get statistics
        total_transactions = OnevasChargingTransaction.objects.filter(
            created_at__gte=start_date
        ).count()
        
        successful_transactions = OnevasChargingTransaction.objects.filter(
            created_at__gte=start_date,
            status='success'
        ).count()
        
        failed_transactions = OnevasChargingTransaction.objects.filter(
            created_at__gte=start_date,
            status='failed'
        ).count()
        
        insufficient_balance = OnevasChargingTransaction.objects.filter(
            created_at__gte=start_date,
            status='insufficient_balance'
        ).count()
        
        expected_collection = OnevasChargingTransaction.objects.filter(
            created_at__gte=start_date
        ).aggregate(total=Sum('amount_etb'))['total'] or 0
        
        actual_collection = OnevasChargingTransaction.objects.filter(
            created_at__gte=start_date,
            status='success'
        ).aggregate(total=Sum('amount_etb'))['total'] or 0
        
        success_rate = (successful_transactions / total_transactions * 100) if total_transactions > 0 else 0
        
        # Daily statistics for charts
        daily_stats = []
        for i in range(days):
            date = (timezone.now() - timedelta(days=days - i - 1)).date()
            day_transactions = OnevasChargingTransaction.objects.filter(
                created_at__date=date
            ).aggregate(
                total=Count('id'),
                success=Count('id', filter=Q(status='success')),
                amount=Sum('amount_etb')
            )
            
            daily_stats.append({
                'date': date.isoformat(),
                'total': day_transactions['total'] or 0,
                'success': day_transactions['success'] or 0,
                'amount': float(day_transactions['amount'] or 0)
            })
        
        return Response({
            'period_days': days,
            'total_transactions': total_transactions,
            'successful_transactions': successful_transactions,
            'failed_transactions': failed_transactions,
            'insufficient_balance': insufficient_balance,
            'expected_collection': float(expected_collection),
            'actual_collection': float(actual_collection),
            'success_rate': round(success_rate, 2),
            'daily_statistics': daily_stats
        })
        
    except Exception as e:
        logger.error(f"[Charging Statistics] Error: {str(e)}")
        return Response(
            {'error': 'Internal server error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_charging_transactions(request):
    """
    Get charging transactions (admin only)
    
    Query params:
    - status: filter by status
    - days: number of days to look back
    - page: page number
    - page_size: items per page
    """
    try:
        # Check if user is admin
        if not request.user.is_staff:
            return Response(
                {'error': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        status_filter = request.GET.get('status')
        days = int(request.GET.get('days', 30))
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        start_date = timezone.now() - timedelta(days=days)
        
        queryset = OnevasChargingTransaction.objects.filter(
            created_at__gte=start_date
        ).select_related('user', 'subscription_tier').order_by('-created_at')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        total_count = queryset.count()
        offset = (page - 1) * page_size
        transactions = queryset[offset:offset + page_size]
        
        transactions_data = []
        for t in transactions:
            transactions_data.append({
                'id': str(t.id),
                'user': t.user.username,
                'phone_number': t.phone_number,
                'subscription_tier': t.subscription_tier.name if t.subscription_tier else None,
                'amount_etb': float(t.amount_etb),
                'status': t.status,
                'transaction_id': t.transaction_id,
                'error_message': t.error_message,
                'created_at': t.created_at.isoformat(),
                'updated_at': t.updated_at.isoformat()
            })
        
        return Response({
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'transactions': transactions_data
        })
        
    except Exception as e:
        logger.error(f"[Charging Transactions] Error: {str(e)}")
        return Response(
            {'error': 'Internal server error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def purchase_coins_on_demand(request):
    """
    Purchase coins via Onevas airtime charging (on-demand: 10 ETB = 100 coins)
    
    Payload:
    {
        "phone_number": "2519..."
    }
    
    Uses:
    - application_key: "4CROFBT0EGCM1OK8R88EQBTEZOMI3138"
    - product_number: "10000302853"
    - URL: https://onevas.et/api/v1/charging
    """
    try:
        phone_number = request.data.get('phone_number')
        
        if not phone_number:
            return Response(
                {'error': 'phone_number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Onevas configuration for on-demand coin purchase
        application_key = "4CROFBT0EGCM1OK8R88EQBTEZOMI3138"
        product_number = "10000302853"
        amount_etb = 10  # Fixed amount for on-demand
        coins_amount = 100  # Fixed coins for on-demand
        
        # Initiate charging with Onevas
        charging_response = onevas_charging_service.initiate_charging(
            phone_number=phone_number,
            product_number=product_number,
            application_key=application_key
        )
        
        # Parse response to determine status
        parsed_status, error_message = onevas_charging_service.parse_charging_response(charging_response)
        
        # Log the transaction
        logger.info(f"[Coin Purchase] User: {request.user.username}, Phone: {phone_number}, Status: {parsed_status}")
        
        # If charging successful, add coins to user balance
        if parsed_status == 'success':
            balance, _ = UserCoinBalance.objects.get_or_create(user=request.user)
            transaction = balance.add_coins(
                coins_amount,
                transaction_type='purchase',
                payment_method='airtime',
                fee_amount=0,
                description=f'On-demand coin purchase via airtime (10 ETB = 100 coins)'
            )
            
            return Response({
                'success': True,
                'message': 'Coins purchased successfully',
                'coins_added': coins_amount,
                'new_balance': balance.balance,
                'amount_charged': amount_etb
            }, status=status.HTTP_201_CREATED)
        
        # If insufficient balance
        elif parsed_status == 'insufficient_balance':
            return Response({
                'success': False,
                'error': 'insufficient_balance',
                'message': 'Your balance is not enough to complete this charge'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # If failed
        else:
            return Response({
                'success': False,
                'error': 'charging_failed',
                'message': error_message or 'Charging failed'
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"[Coin Purchase] Error: {str(e)}")
        return Response(
            {'error': 'Internal server error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
