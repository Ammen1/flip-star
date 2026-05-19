"""
Telebirr Direct Debit API Views

API endpoints for direct debit mandate management:
- Create mandate
- Activate mandate
- Cancel mandate
- List user mandates
- Webhook for async results
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal

import logging
import re

from .models_direct_debit import DirectDebitMandate, DirectDebitTransaction
from .models_subscription import SubscriptionTier, SubscriptionPlan, SubscriptionPayment
from .telebirr_direct_debit_service import telebirr_direct_debit_service

logger = logging.getLogger(__name__)


def _parse_telebirr_soap_result(raw_body):
    """Extract the fields we care about from a Telebirr SOAP Result envelope.

    Telebirr sends ``Content-Type: text/xml`` with an ``<api:Result>`` SOAP
    envelope. DRF's ``request.data`` cannot parse this so we operate on the
    raw bytes/string with regex (the schema is fixed and small).
    """
    if isinstance(raw_body, (bytes, bytearray)):
        try:
            raw_body = raw_body.decode('utf-8', errors='replace')
        except Exception:
            raw_body = str(raw_body)
    text = raw_body or ''

    def _find(tag):
        m = re.search(
            r'<(?:[a-zA-Z]+:)?{0}>([^<]*)</(?:[a-zA-Z]+:)?{0}>'.format(tag),
            text,
        )
        return m.group(1).strip() if m else None

    return {
        'ResultType': _find('ResultType'),
        'ResultCode': _find('ResultCode'),
        'ResultDesc': _find('ResultDesc'),
        'ConversationID': _find('ConversationID'),
        'OriginatorConversationID': _find('OriginatorConversationID'),
        'TransactionID': _find('TransactionID'),
        'MandateID': _find('MandateID'),
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_direct_debit_mandate(request):
    """
    Create a direct debit mandate for subscription payment
    
    Request Body:
    {
        "tier_id": "uuid",
        "payer_msisdn": "251911234567",
        "frequency": "05"  // 02=Daily, 03=Weekly, 05=Monthly
    }
    """
    try:
        user = request.user
        tier_id = request.data.get('tier_id')
        payer_msisdn = request.data.get('payer_msisdn')
        frequency = request.data.get('frequency')
        
        # Validate required fields
        if not all([tier_id, payer_msisdn, frequency]):
            return Response(
                {'error': 'tier_id, payer_msisdn, and frequency are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get subscription tier
        try:
            tier = SubscriptionTier.objects.get(id=tier_id, is_active=True)
        except SubscriptionTier.DoesNotExist:
            return Response(
                {'error': 'Invalid subscription tier'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate frequency matches tier duration
        frequency_map = {
            'daily': '02',
            'weekly': '03',
            'monthly': '05',
        }
        if tier.duration_type not in frequency_map:
            return Response(
                {'error': 'This tier does not support direct debit (only tier-based subscriptions)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        expected_frequency = frequency_map[tier.duration_type]
        if frequency != expected_frequency:
            return Response(
                {'error': f'Frequency must be {expected_frequency} for {tier.duration_type} tier'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate payer reference number
        payer_reference_number = f"FLP{user.id}{int(timezone.now().timestamp())}"
        
        # Calculate dates
        first_payment_date = timezone.now().date()
        expiry_date = first_payment_date + timedelta(days=365)  # 1 year expiry
        
        # Call Telebirr service to create mandate
        result = telebirr_direct_debit_service.create_mandate(
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            frequency=frequency,
            first_payment_date=first_payment_date.strftime('%Y%m%d'),
            expiry_date=expiry_date.strftime('%Y%m%d'),
        )
        
        if not result.get('success'):
            return Response(
                {'error': result.get('error', 'Mandate creation failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Create mandate record. The synchronous Telebirr response is only an
        # acceptance ack; the real result (with the Telebirr-generated
        # MandateID) arrives later on the webhook. Until then, the mandate
        # stays in `pending_created` and cannot be activated/cancelled/debited.
        mandate = DirectDebitMandate.objects.create(
            user=user,
            tier=tier,
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            payee_identifier_value=getattr(tier, 'short_code', '9286'),
            frequency=frequency,
            first_payment_date=first_payment_date,
            expiry_date=expiry_date,
            agreed_tc=True,
            originator_conversation_id=result.get('originator_conversation_id'),
            conversation_id=result.get('conversation_id'),
            status='pending_created'
        )
        
        return Response({
            'success': True,
            'mandate_id': str(mandate.id),
            'payer_reference_number': payer_reference_number,
            'status': mandate.status,
            'message': 'Mandate created successfully. Please activate it to complete subscription.',
            'originator_conversation_id': result.get('originator_conversation_id')
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': f'Failed to create mandate: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def activate_direct_debit_mandate(request):
    """
    Activate a direct debit mandate
    
    Request Body:
    {
        "mandate_id": "uuid",
        "payer_account_name": "John Doe"  // optional
    }
    """
    try:
        user = request.user
        mandate_id = request.data.get('mandate_id')
        payer_account_name = request.data.get('payer_account_name', '')
        
        # Validate required fields
        if not mandate_id:
            return Response(
                {'error': 'mandate_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get mandate
        try:
            mandate = DirectDebitMandate.objects.get(id=mandate_id, user=user)
        except DirectDebitMandate.DoesNotExist:
            return Response(
                {'error': 'Mandate not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check mandate status
        if mandate.status != 'pending_active':
            return Response(
                {'error': f'Mandate is in {mandate.status} status, cannot activate'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Telebirr requires the real MandateID (max 18 bytes) generated by
        # the Mobile Money system and delivered via the async result webhook.
        # Substituting payer_reference_number here would be rejected.
        if not mandate.mandate_id:
            return Response(
                {'error': 'Mandate is not yet ready for activation. Telebirr has not returned the MandateID. Please retry shortly.'},
                status=status.HTTP_409_CONFLICT
            )

        # Call Telebirr service to activate mandate
        result = telebirr_direct_debit_service.activate_mandate(
            mandate_id=mandate.mandate_id,
            payer_msisdn=mandate.payer_msisdn,
            agreed_tc=True,
            payer_account_name=payer_account_name
        )
        
        if not result.get('success'):
            mandate.mark_failed(result.get('error'))
            return Response(
                {'error': result.get('error', 'Mandate activation failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Update mandate
        mandate.payer_account_name = payer_account_name
        mandate.originator_conversation_id = result.get('originator_conversation_id')
        mandate.conversation_id = result.get('conversation_id')
        mandate.activate()

        # Create subscription plan from the tier persisted at mandate creation
        # time. (Previously this read mandate.subscription_plan.tier which is
        # always None at activation, so subscriptions were never created.)
        subscription_plan = None
        tier = mandate.tier
        if tier:
            subscription_plan = SubscriptionPlan.objects.create(
                user=user,
                tier=tier,
                status='active',
                duration_type=tier.duration_type,
                start_date=timezone.now(),
                end_date=timezone.now() + timedelta(days=tier.duration_days) if tier.duration_days else None,
                next_renewal_date=timezone.now() + timedelta(days=tier.duration_days) if tier.duration_days else None,
                auto_renew=True,
                payment_method='telebirr_direct_debit'
            )
            
            # Link mandate to subscription
            mandate.subscription_plan = subscription_plan
            mandate.save()
            
            # Create initial payment record
            SubscriptionPayment.objects.create(
                subscription=subscription_plan,
                user=user,
                amount=tier.price_etb,
                currency='ETB',
                status='pending',
                payment_method='telebirr_direct_debit',
                duration_type=tier.duration_type,
                period_start=timezone.now(),
                period_end=subscription_plan.end_date or timezone.now() + timedelta(days=30)
            )
        
        return Response({
            'success': True,
            'mandate_id': str(mandate.id),
            'status': mandate.status,
            'subscription_id': str(subscription_plan.id) if subscription_plan else None,
            'message': 'Mandate activated successfully. Subscription created.'
        })
        
    except Exception as e:
        return Response(
            {'error': f'Failed to activate mandate: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_direct_debit_mandate(request):
    """
    Cancel a direct debit mandate
    
    Request Body:
    {
        "mandate_id": "uuid"
    }
    """
    try:
        user = request.user
        mandate_id = request.data.get('mandate_id')
        
        # Validate required fields
        if not mandate_id:
            return Response(
                {'error': 'mandate_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get mandate
        try:
            mandate = DirectDebitMandate.objects.get(id=mandate_id, user=user)
        except DirectDebitMandate.DoesNotExist:
            return Response(
                {'error': 'Mandate not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if mandate is active
        if not mandate.is_active():
            return Response(
                {'error': f'Mandate is {mandate.status}, cannot cancel'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not mandate.mandate_id:
            return Response(
                {'error': 'Mandate has no Telebirr MandateID yet, cannot cancel.'},
                status=status.HTTP_409_CONFLICT
            )

        # Call Telebirr service to cancel mandate
        result = telebirr_direct_debit_service.cancel_mandate(
            mandate_id=mandate.mandate_id,
            payer_msisdn=mandate.payer_msisdn
        )
        
        if not result.get('success'):
            return Response(
                {'error': result.get('error', 'Mandate cancellation failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Update mandate
        mandate.cancel()
        
        # Cancel linked subscription auto-renewal
        if mandate.subscription_plan:
            mandate.subscription_plan.auto_renew = False
            mandate.subscription_plan.save()
        
        return Response({
            'success': True,
            'mandate_id': str(mandate.id),
            'status': mandate.status,
            'message': 'Mandate cancelled successfully. Auto-renewal disabled.'
        })
        
    except Exception as e:
        return Response(
            {'error': f'Failed to cancel mandate: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_user_mandates(request):
    """
    List all mandates for the authenticated user
    """
    try:
        user = request.user
        mandates = DirectDebitMandate.objects.filter(user=user).order_by('-created_at')
        
        mandate_data = []
        for mandate in mandates:
            mandate_data.append({
                'id': str(mandate.id),
                'mandate_id': mandate.mandate_id,
                'payer_msisdn': mandate.payer_msisdn,
                'status': mandate.status,
                'frequency': mandate.frequency,
                'first_payment_date': mandate.first_payment_date,
                'expiry_date': mandate.expiry_date,
                'subscription_plan_id': str(mandate.subscription_plan.id) if mandate.subscription_plan else None,
                'created_at': mandate.created_at,
                'is_active': mandate.is_active(),
            })
        
        return Response({
            'success': True,
            'mandates': mandate_data
        })
        
    except Exception as e:
        return Response(
            {'error': f'Failed to list mandates: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])  # Telebirr calls this webhook
def telebirr_direct_debit_webhook(request):
    """Webhook endpoint for Telebirr async Result envelopes.

    Telebirr POSTs a SOAP Result envelope (``Content-Type: text/xml``). The
    previous version read ``request.data`` (JSON-only) which silently 400'd
    every real callback. We now parse the raw XML body and correlate by
    ``OriginatorConversationID``. We always return HTTP 200 so Telebirr
    does not retry-storm us; processing errors are logged.
    """
    raw_body = request.body or b''
    logger.warning(
        'Telebirr webhook hit: ct=%s len=%d body=%s',
        request.META.get('CONTENT_TYPE'),
        len(raw_body),
        raw_body[:4000],
    )

    try:
        # XML first (real Telebirr); JSON fallback for manual tests.
        parsed = _parse_telebirr_soap_result(raw_body)
        if not parsed.get('OriginatorConversationID') and isinstance(request.data, dict):
            tx = request.data.get('TransactionResult') or {}
            parsed = {
                'ResultType': request.data.get('ResultType'),
                'ResultCode': request.data.get('ResultCode'),
                'ResultDesc': request.data.get('ResultDesc'),
                'ConversationID': request.data.get('ConversationID'),
                'OriginatorConversationID': request.data.get('OriginatorConversationID'),
                'TransactionID': tx.get('TransactionID') if isinstance(tx, dict) else request.data.get('TransactionID'),
                'MandateID': request.data.get('MandateID'),
            }

        logger.info('Telebirr webhook parsed: %s', parsed)

        originator_conversation_id = parsed.get('OriginatorConversationID')
        result_code = parsed.get('ResultCode')
        result_type = parsed.get('ResultType')
        result_desc = parsed.get('ResultDesc') or ''
        # Telebirr returns the new MandateID either in <MandateID> or, for
        # InitTrans, the transaction id in <TransactionID>.
        new_mandate_id = parsed.get('MandateID') or parsed.get('TransactionID')

        if not originator_conversation_id:
            logger.warning('Telebirr webhook: no OriginatorConversationID found, ignoring')
            return Response({'success': True})

        mandate = DirectDebitMandate.objects.filter(
            originator_conversation_id=originator_conversation_id
        ).first()

        if not mandate:
            logger.warning(
                'Telebirr webhook: no mandate matched OriginatorConversationID=%s',
                originator_conversation_id,
            )
            return Response({'success': True})

        is_success = result_code == '0' and (result_type == '0' or result_type is None)

        if is_success:
            # Persist the real MandateID as soon as we get it (max 18 bytes).
            if new_mandate_id and not mandate.mandate_id:
                mandate.mandate_id = new_mandate_id[:18]

            # Handle one-off payments (coin purchases)
            if mandate.payment_type == 'one_off':
                # Add coins to user's profile
                from .models import UserProfile
                try:
                    profile = mandate.user.profile
                    coins_to_add = mandate.metadata.get('coins', 100)
                    profile.coins += coins_to_add
                    profile.coins_earned_total += coins_to_add
                    profile.save()
                    logger.info(f'Added {coins_to_add} coins to user {mandate.user.username} for one-off payment {mandate.id}')
                    
                    # Mark mandate as completed
                    mandate.status = 'active'  # Use active to indicate successful one-off payment
                    mandate.save()
                except UserProfile.DoesNotExist:
                    logger.error(f'UserProfile not found for user {mandate.user.username}, cannot add coins')
                    mandate.mark_failed('UserProfile not found')
            else:
                # Handle recurring mandates
                if mandate.status == 'pending_created':
                    mandate.status = 'pending_active'
                    mandate.save()
                elif mandate.status == 'pending_active':
                    mandate.activate()  # also sets activated_at and saves
                else:
                    mandate.save()
        else:
            mandate.mark_failed(result_desc or f'ResultCode={result_code}')

        return Response({'success': True})

    except Exception as e:
        # Don't bubble 500s back to Telebirr; just log and ack.
        logger.exception('Telebirr webhook processing failed: %s', e)
        return Response({'success': True})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_direct_debit(request):
    """
    Manually initiate a direct debit transaction (for testing or manual renewal)
    
    Request Body:
    {
        "mandate_id": "uuid",
        "amount": 100.00
    }
    """
    try:
        user = request.user
        mandate_id = request.data.get('mandate_id')
        amount = request.data.get('amount')
        
        # Validate required fields
        if not all([mandate_id, amount]):
            return Response(
                {'error': 'mandate_id and amount are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get mandate
        try:
            mandate = DirectDebitMandate.objects.get(id=mandate_id, user=user)
        except DirectDebitMandate.DoesNotExist:
            return Response(
                {'error': 'Mandate not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if mandate is active
        if not mandate.is_active():
            return Response(
                {'error': f'Mandate is {mandate.status}, cannot initiate debit'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not mandate.mandate_id:
            return Response(
                {'error': 'Mandate has no Telebirr MandateID yet, cannot initiate debit.'},
                status=status.HTTP_409_CONFLICT
            )

        # Create transaction record
        transaction = DirectDebitTransaction.objects.create(
            mandate=mandate,
            amount=Decimal(str(amount)),
            currency='ETB',
            status='pending'
        )

        # Call Telebirr service to initiate debit
        result = telebirr_direct_debit_service.initiate_debit(
            mandate_id=mandate.mandate_id,
            payer_reference_number=mandate.payer_reference_number,
            amount=amount,
            shortcode=mandate.payee_identifier_value
        )
        
        if not result.get('success'):
            transaction.mark_failed(result.get('error'))
            return Response(
                {'error': result.get('error', 'Direct debit initiation failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Update transaction
        transaction.originator_conversation_id = result.get('originator_conversation_id')
        transaction.conversation_id = result.get('conversation_id')
        transaction.telebirr_transaction_id = result.get('transaction_id')
        transaction.save()
        
        return Response({
            'success': True,
            'transaction_id': str(transaction.id),
            'status': transaction.status,
            'message': 'Direct debit initiated successfully'
        })
        
    except Exception as e:
        return Response(
            {'error': f'Failed to initiate direct debit: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_one_off_coin_purchase(request):
    """
    Create a one-off payment for coin purchasing via Telebirr Direct Debit
    
    Request Body:
    {
        "amount": 10.00,
        "coins": 100
    }
    
    Returns:
    {
        "success": true,
        "mandate_id": "uuid",
        "originator_conversation_id": "S_X20260519...",
        "message": "One-off payment request accepted"
    }
    """
    try:
        user = request.user
        amount = request.data.get('amount')
        coins = request.data.get('coins', 100)
        
        # Validate required fields
        if not amount:
            return Response(
                {'error': 'amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get user's phone number from profile
        from .models import UserProfile
        try:
            profile = user.profile
            payer_msisdn = profile.phone_number
            if not payer_msisdn:
                return Response(
                    {'error': 'Phone number not found in profile'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except UserProfile.DoesNotExist:
            return Response(
                {'error': 'User profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Generate unique payer reference number
        payer_reference_number = f"COIN_{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Call Telebirr service to create one-off payment
        result = telebirr_direct_debit_service.create_one_off_payment(
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            amount=amount
        )
        
        if not result.get('success'):
            return Response(
                {'error': result.get('error', 'One-off payment request failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Create mandate record with payment_type='one_off'
        mandate = DirectDebitMandate.objects.create(
            user=user,
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            payee_identifier_type=4,
            payee_identifier_value=telebirr_direct_debit_service.shortcode,
            payee_account_name=telebirr_direct_debit_service.payee_account_name,
            status='pending_created',
            payment_type='one_off',
            frequency='01',
            first_payment_date=datetime.now().date(),
            expiry_date=datetime.now().date(),
            agreed_tc=True,
            originator_conversation_id=result.get('originator_conversation_id'),
            conversation_id=result.get('conversation_id'),
            metadata={
                'coins': coins,
                'amount': amount
            }
        )
        
        return Response({
            'success': True,
            'mandate_id': str(mandate.id),
            'originator_conversation_id': result.get('originator_conversation_id'),
            'conversation_id': result.get('conversation_id'),
            'message': 'One-off payment request accepted successfully. Wait for payment confirmation.',
            'coins': coins,
            'amount': amount
        })
        
    except Exception as e:
        return Response(
            {'error': f'Failed to create one-off payment: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
