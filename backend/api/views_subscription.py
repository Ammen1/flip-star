from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.models import User

from .models_subscription import (
    SubscriptionTier, SubscriptionPlan as UserSubscription, SubscriptionPayment, SubscriptionHistory,
    OnevasWebhookLog, PromoCode, UserPromoUsage, SubscriptionFeatureUsage,
    ExpiredSubscriptionAction, TrialPopupLog, SubscriptionCoinTransaction as CoinTransaction, AdminRole, SubscriptionReport
)
from .models import UserProfile
from .telebirr_service import telebirr_service
import requests
import json
import uuid
from datetime import timedelta

# Onevas SMS Configuration
ONEVAS_SMS_URL = "https://onevas.et/api/partnerSms/send"
ONEVAS_APPLICATION_KEY = settings.ONEVAS_APPLICATION_KEY if hasattr(settings, 'ONEVAS_APPLICATION_KEY') else "YOUR_APPLICATION_KEY"
ONEVAS_PRODUCT_NUMBER = settings.ONEVAS_PRODUCT_NUMBER if hasattr(settings, 'ONEVAS_PRODUCT_NUMBER') else "YOUR_PRODUCT_NUMBER"

# Onevas Product Configuration (SPID, Service ID, Product ID, Application Key)
ONEVAS_PRODUCTS = {
    'daily': {
        'spid': '300263',
        'service_id': '30026300007331',
        'product_id': '10000302850',
        'application_key': 'UPJG5ZM3X6C9LLDSKKCME4MA86UQRKWV'
    },
    'weekly': {
        'spid': '300263',
        'service_id': '30026300007332',
        'product_id': '10000302851',
        'application_key': 'I6QEX9W5D341NN50QPB0KQ9HW6DH99TQ'
    },
    'monthly': {
        'spid': '300263',
        'service_id': '30026300007333',
        'product_id': '10000302852',
        'application_key': '0Y72TFLJP4ZAQ127K0O43IJSD9QAPTWQ'
    },
    'ondemand': {
        'spid': '300263',
        'service_id': '30026300007334',
        'product_id': '10000302853',
        'application_key': '4CROFBT0EGCM1OK8R88EQBTEZOMI3138'
    }
}

# App Links (placeholders - update with actual URLs)
# WEB_APP_LINK = "https://uat.flipstar.et?subscription_tp=true"
WEB_APP_LINK = "https://uat.flipstar.et"
MOBILE_APP_LINK = "https://play.google.com/store/apps/details?id=com.postworq.mobile"

# Helper function to mask phone number (show first 9 digits, mask last 4)
def mask_phone_number(phone):
    if not phone or len(phone) < 4:
        return phone
    return phone[:9] + '****'


class UserSubscriptionStatusView(APIView):
    """Check user subscription status"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get current user's subscription status"""
        try:
            from django.utils import timezone
            
            # Check for active subscription
            active_subscription = UserSubscription.objects.filter(
                user=request.user,
                status='active',
                end_date__gt=timezone.now()
            ).first()
            
            if active_subscription:
                return Response({
                    'has_subscription': True,
                    'subscription': {
                        'id': str(active_subscription.id),
                        'tier': {
                            'id': str(active_subscription.tier.id) if active_subscription.tier else None,
                            'name': active_subscription.tier.name if active_subscription.tier else None,
                            'duration_type': active_subscription.tier.duration_type if active_subscription.tier else None,
                            'price_etb': float(active_subscription.tier.price_etb) if active_subscription.tier else 0,
                        },
                        'status': active_subscription.status,
                        'start_date': active_subscription.start_date.isoformat(),
                        'end_date': active_subscription.end_date.isoformat() if active_subscription.end_date else None,
                        'auto_renew': active_subscription.auto_renew,
                    }
                })
            else:
                # Check if user has any subscription (expired or cancelled)
                any_subscription = UserSubscription.objects.filter(user=request.user).first()
                
                return Response({
                    'has_subscription': False,
                    'subscription': None,
                    'has_had_subscription': any_subscription is not None,
                    'message': 'You need an active subscription to access this feature'
                }, status=status.HTTP_403_FORBIDDEN)
        
        except Exception as e:
            return Response({
                'error': str(e),
                'has_subscription': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OnevasWebhookView(APIView):
    """Handle Onevas webhook notifications"""
    permission_classes = [AllowAny]
    
    def handle_stop_command(self, phone_number, stop_keyword='STOP'):
        """Handle STOP command for subscription cancellation"""
        print(f"[SUBSCRIPTION DEBUG] {stop_keyword} command received for phone: {phone_number}")

        # Map STOP keywords to tier duration types
        stop_keyword_mapping = {
            'STOP': 'daily',
            'STOP1': 'daily',
            'STOP2': 'weekly',
            'STOP3': 'monthly'
        }
        target_duration_type = stop_keyword_mapping.get(stop_keyword, None)
        print(f"[SUBSCRIPTION DEBUG] Target duration type for {stop_keyword}: {target_duration_type}")


        # First try to find registered user - improved mapping logic
        user = None
        try:
            profile = UserProfile.objects.get(phone_number=phone_number)
            user = profile.user
            print(f"[SUBSCRIPTION DEBUG] Found registered user: {user.username}")
        except UserProfile.DoesNotExist:
            # Try to find user via existing subscriptions with this phone number
            existing_subscription = UserSubscription.objects.filter(onevas_phone_number=phone_number).first()
            if existing_subscription and existing_subscription.user:
                user = existing_subscription.user
                print(f"[SUBSCRIPTION DEBUG] Found user via existing subscription: {user.username}")
                # Update UserProfile phone_number if not set
                if not user.profile.phone_number:
                    user.profile.phone_number = phone_number
                    user.profile.save()
                    print(f"[SUBSCRIPTION DEBUG] Updated UserProfile phone_number for {user.username}")
            else:
                print(f"[SUBSCRIPTION DEBUG] User not registered, checking for SMS-first subscription")

        # Find active subscriptions (either by user or by phone number for SMS-first)
        subscriptions = []
        if user:
            print(f"[SUBSCRIPTION DEBUG] Checking subscriptions for user: {user.username}")
            all_user_subs = UserSubscription.objects.filter(user=user)
            print(f"[SUBSCRIPTION DEBUG] Total subscriptions for user: {all_user_subs.count()}")
            for sub in all_user_subs:
                print(f"[SUBSCRIPTION DEBUG]   - ID: {sub.id}, Status: {sub.status}, Duration: {sub.duration_type}, Tier: {sub.tier.name if sub.tier else 'None'}")
            
            if target_duration_type:
                # Find ALL active subscriptions with this duration type
                subscriptions = list(UserSubscription.objects.filter(
                    user=user,
                    status='active',
                    tier__duration_type=target_duration_type
                ))
                print(f"[SUBSCRIPTION DEBUG] Looking for ALL active subscriptions with duration_type={target_duration_type}: Found {len(subscriptions)}")
            else:
                # No specific duration type, find ALL active subscriptions
                subscriptions = list(UserSubscription.objects.filter(
                    user=user,
                    status='active'
                ))
                print(f"[SUBSCRIPTION DEBUG] Looking for ALL active subscriptions: Found {len(subscriptions)}")
        else:
            # Check for SMS-first subscription (user not registered yet)
            print(f"[SUBSCRIPTION DEBUG] Checking SMS-first subscriptions for phone: {phone_number}")
            if target_duration_type:
                subscriptions = list(UserSubscription.objects.filter(
                    onevas_phone_number=phone_number,
                    status='active',
                    subscription_source='sms',
                    tier__duration_type=target_duration_type
                ))
                print(f"[SUBSCRIPTION DEBUG] SMS-first subscriptions with duration_type={target_duration_type}: Found {len(subscriptions)}")
            else:
                subscriptions = list(UserSubscription.objects.filter(
                    onevas_phone_number=phone_number,
                    status='active',
                    subscription_source='sms'
                ))
                print(f"[SUBSCRIPTION DEBUG] All SMS-first active subscriptions: Found {len(subscriptions)}")

        if not subscriptions:
            # No active subscriptions
            print(f"[SUBSCRIPTION DEBUG] No active subscriptions found for phone: {phone_number}")
            no_sub_message = "You don't have an active subscription to cancel."
            print(f"[SUBSCRIPTION DEBUG] Sending no-subscription SMS to {phone_number}")
            sms_sent = self.send_sms(phone_number, no_sub_message)
            print(f"[SUBSCRIPTION DEBUG] No-subscription SMS sent: {sms_sent}")
            return Response({'status': 'no_active_subscription', 'message': 'No active subscription found'})

        # Cancel ALL matching subscriptions
        cancelled_count = 0
        for subscription in subscriptions:
            print(f"[SUBSCRIPTION DEBUG] Cancelling subscription: ID {subscription.id}, Tier: {subscription.tier.name}, Status: {subscription.status}")
            subscription.cancel(reason='User cancelled via STOP SMS')
            
            # Record history
            SubscriptionHistory.objects.create(
                user=user,
                subscription=subscription,
                tier=subscription.tier,
                action='cancelled',
                reason='User cancelled via STOP SMS',
                metadata={'method': 'stop_command', 'sms_subscription': user is None}
            )
            cancelled_count += 1

        print(f"[SUBSCRIPTION DEBUG] Cancelled {cancelled_count} subscription(s) successfully")

        # Send SMS confirmation
        # Use the tier from the first cancelled subscription for the SMS
        if subscriptions and subscriptions[0].tier:
            tier = subscriptions[0].tier
            # Map duration type to resubscribe keyword and stop keyword
            resubscribe_keywords = {
                'daily': 'A',
                'weekly': 'B',
                'monthly': 'C',
                'ondemand': 'D'
            }
            stop_keywords = {
                'daily': 'STOP',
                'weekly': 'STOP2',
                'monthly': 'STOP3',
                'ondemand': 'STOP'
            }
            resubscribe_keyword = resubscribe_keywords.get(tier.duration_type, 'A')
            cancel_keyword = stop_keywords.get(tier.duration_type, 'STOP')
            cancellation_message = f"You have successfully unsubscribed from the {tier.name} service. To subscribe again, send {resubscribe_keyword} to {tier.short_code}."
            print(f"[SUBSCRIPTION DEBUG] Sending cancellation SMS to {phone_number}")
            sms_sent = self.send_sms(phone_number, cancellation_message, tier.duration_type)
            print(f"[SUBSCRIPTION DEBUG] Cancellation SMS sent: {sms_sent}")
        else:
            print(f"[SUBSCRIPTION DEBUG] WARNING: subscription.tier is None, cannot send SMS with tier info")
            cancellation_message = f"You have successfully unsubscribed from the Flipstar service."
            print(f"[SUBSCRIPTION DEBUG] Sending generic cancellation SMS to {phone_number}")
            sms_sent = self.send_sms(phone_number, cancellation_message, None)
            print(f"[SUBSCRIPTION DEBUG] Cancellation SMS sent: {sms_sent}")

        return Response({'status': 'success', 'message': f'{cancelled_count} subscription(s) cancelled via STOP command'})
    
    def send_sms(self, phone_number, text, tier_type=None):
        """Send SMS using Onevas API with tier-specific application key"""
        try:
            # Get application key for the specific tier, or use default
            app_key = ONEVAS_APPLICATION_KEY
            if tier_type and tier_type in ONEVAS_PRODUCTS:
                app_key = ONEVAS_PRODUCTS[tier_type]['application_key']

            # Get product number from configuration
            product_number = ONEVAS_PRODUCT_NUMBER
            if tier_type and tier_type in ONEVAS_PRODUCTS:
                product_number = ONEVAS_PRODUCTS[tier_type]['product_id']

            payload = {
                "phone_number": phone_number,
                "application_key": app_key,
                "text": text,
                "product_number": product_number
            }
            print(f"[SMS DEBUG] Sending SMS - phone: {phone_number}, tier_type: {tier_type}, app_key: {app_key[:10]}..., product_number: {product_number}")
            print(f"[SMS DEBUG] SMS text length: {len(text)}")
            response = requests.post(ONEVAS_SMS_URL, json=payload, timeout=10)
            print(f"[SMS DEBUG] Response status: {response.status_code}, response body: {response.text}")
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send SMS: {e}")
            return False
    
    def post(self, request, webhook_type):
        """Handle subscription, unsubscription, renewal, and stop webhooks"""
        try:
            payload = request.data
            print(f"[SUBSCRIPTION DEBUG] Webhook received - type: {webhook_type}")
            print(f"[SUBSCRIPTION DEBUG] Webhook payload: {payload}")
            
            # Log the webhook
            log = OnevasWebhookLog.objects.create(
                webhook_type=webhook_type,
                payload=payload
            )
            print(f"[SUBSCRIPTION DEBUG] Webhook log created: ID {log.id}")
            
            if webhook_type == 'subscription':
                print(f"[SUBSCRIPTION DEBUG] Routing to handle_subscription")
                response = self.handle_subscription(payload, log)
            elif webhook_type == 'unsubscription':
                print(f"[SUBSCRIPTION DEBUG] Routing to handle_unsubscription")
                response = self.handle_unsubscription(payload, log)
            elif webhook_type == 'renewal':
                print(f"[SUBSCRIPTION DEBUG] Routing to handle_renewal")
                response = self.handle_renewal(payload, log)
            elif webhook_type == 'stop':
                phone_number = payload.get('phone_number')
                product_number = payload.get('product_number', '').upper()
                print(f"[SUBSCRIPTION DEBUG] STOP webhook - phone: {phone_number}, product: {product_number}")
                print(f"[SUBSCRIPTION DEBUG] Full STOP payload: {payload}")

                # Extract keyword from params array if present
                params = payload.get('params', [])
                stop_keyword = 'STOP'  # Default
                for param in params:
                    if param.get('name') == 'keyword':
                        stop_keyword = param.get('value', 'STOP').upper()
                        break

                # If no keyword in params, try to determine from product_number
                if stop_keyword == 'STOP' and product_number:
                    product_to_keyword = {
                        '10000302850': 'STOP1',  # Daily
                        '10000302851': 'STOP2',  # Weekly
                        '10000302852': 'STOP3',  # Monthly
                        '10000302853': 'STOP'   # OnDemand
                    }
                    stop_keyword = product_to_keyword.get(product_number, 'STOP')
                    print(f"[SUBSCRIPTION DEBUG] Determined keyword from product_number: {stop_keyword}")

                print(f"[SUBSCRIPTION DEBUG] Routing to handle_stop_command for {phone_number} with keyword: {stop_keyword}")
                response = self.handle_stop_command(phone_number, stop_keyword)
            else:
                print(f"[SUBSCRIPTION DEBUG] Invalid webhook type: {webhook_type}")
                response = Response({'error': 'Invalid webhook type'}, status=400)
            
            log.response_status = response.status_code
            log.response_body = response.data if hasattr(response, 'data') else {}
            log.processed = True
            log.save()
            print(f"[SUBSCRIPTION DEBUG] Webhook processed - status: {response.status_code}")
            
            return response
            
        except Exception as e:
            return Response({'error': str(e)}, status=500)
    
    def handle_subscription(self, payload, log):
        """Handle subscription notification from Onevas"""
        phone_number = payload.get('phone_number')
        product_number = payload.get('product_number', '').upper()  # Convert to uppercase
        password = payload.get('password', '').upper()  # SMS code might be in password field

        print(f"[SUBSCRIPTION DEBUG] Received subscription webhook - phone: {phone_number}, product: {product_number}, password: {password}")
        print(f"[SUBSCRIPTION DEBUG] Full payload: {payload}")

        # Extract keyword from params array if present
        params = payload.get('params', [])
        keyword_from_params = None
        for param in params:
            if param.get('name') == 'keyword':
                keyword_from_params = param.get('value', '').upper()
                break
        if keyword_from_params:
            print(f"[SUBSCRIPTION DEBUG] Keyword from params: {keyword_from_params}")

        # Find user by phone number - improved mapping logic
        user = None
        user_exists = False
        try:
            # First try exact match on phone_number
            profile = UserProfile.objects.get(phone_number=phone_number)
            user = profile.user
            user_exists = True
            print(f"[SUBSCRIPTION DEBUG] User found by phone_number: {user.username}")
        except UserProfile.DoesNotExist:
            # Try to find user by checking if they have any existing subscriptions with this phone
            existing_subscription = UserSubscription.objects.filter(onevas_phone_number=phone_number).first()
            if existing_subscription and existing_subscription.user:
                user = existing_subscription.user
                user_exists = True
                print(f"[SUBSCRIPTION DEBUG] User found via existing subscription: {user.username}")
                # Update UserProfile phone_number if not set
                if not user.profile.phone_number:
                    user.profile.phone_number = phone_number
                    user.profile.save()
                    print(f"[SUBSCRIPTION DEBUG] Updated UserProfile phone_number for {user.username}")
            else:
                print(f"[SUBSCRIPTION DEBUG] User not found for phone: {phone_number}")

        # Find tier by product number or SMS code
        tier = None
        if product_number:
            try:
                tier = SubscriptionTier.objects.get(product_id=product_number)
                print(f"[SUBSCRIPTION DEBUG] Tier found by product_number: {tier.name} (ID: {tier.id})")
            except SubscriptionTier.DoesNotExist:
                print(f"[SUBSCRIPTION DEBUG] Tier not found for product: {product_number}")

        # If no tier found by product_number, try using SMS code from params (Ok1, Ok2, Ok3, Ok4) or password (A, B, C, D)
        if not tier:
            sms_code = (keyword_from_params or password or '').upper()
            sms_code_mapping = {
                'OK1': 'daily',
                'OK2': 'weekly',
                'OK3': 'monthly',
                'OK4': 'ondemand',
            }
            duration_type = sms_code_mapping.get(sms_code)
            if duration_type:
                try:
                    tier = SubscriptionTier.objects.get(duration_type=duration_type, is_active=True)
                    print(f"[SUBSCRIPTION DEBUG] Tier found by SMS code {sms_code}: {tier.name} (ID: {tier.id})")
                except SubscriptionTier.DoesNotExist:
                    print(f"[SUBSCRIPTION DEBUG] No active tier found for duration type: {duration_type}")

        if not tier:
            print(f"[SUBSCRIPTION DEBUG] Tier not found - product_number: {product_number}, password: {password}, keyword from params: {keyword_from_params}")
            return Response({'error': 'Tier not found. Please check product_number or SMS code.'}, status=404)
        
        # If user is not registered, create active subscription (SMS-first flow)
        if not user_exists:
            print(f"[SUBSCRIPTION DEBUG] Creating SMS-first subscription (user not registered)")
            
            # Check if there's already an SMS-first subscription of the same duration type for this phone
            existing_sms_sub = UserSubscription.objects.filter(
                onevas_phone_number=phone_number,
                status='active',
                subscription_source='sms',
                duration_type=tier.duration_type
            ).first()
            
            if existing_sms_sub:
                print(f"[SUBSCRIPTION DEBUG] Found existing SMS-first subscription of same type, renewing it...")
                # Renew existing subscription
                existing_sms_sub.tier = tier
                existing_sms_sub.duration_type = tier.duration_type
                existing_sms_sub.activate()
                
                from .services.otp_service import OTPService
                otp_code = OTPService.generate_otp()
                existing_sms_sub.setup_otp = otp_code
                existing_sms_sub.save()
                
    
                SubscriptionPayment.objects.create(
                    subscription=existing_sms_sub,
                    user=None,
                    amount=tier.price_etb,
                    payment_method='onevas',
                    duration_type=tier.duration_type,
                    period_start=existing_sms_sub.start_date,
                    period_end=existing_sms_sub.end_date or timezone.now() + timedelta(days=tier.duration_days or 30),
                    status='completed'
                )
                
                # Record history
                SubscriptionHistory.objects.create(
                    user=None,
                    subscription=existing_sms_sub,
                    tier=tier,
                    action='renewed',
                    reason='SMS-first subscription renewed via Onevas',
                    metadata={'webhook_payload': payload, 'sms_subscription': True}
                )
                
                # Send success SMS
                stop_keywords = {
                    'daily': 'STOP1',
                    'weekly': 'STOP2',
                    'monthly': 'STOP3',
                    'ondemand': 'STOP'
                }
                stop_keyword = stop_keywords.get(tier.duration_type, 'STOP')
                price_periods = {
                    'daily': 'day',
                    'weekly': 'week',
                    'monthly': 'month',
                    'ondemand': 'use'
                }
                price_period = price_periods.get(tier.duration_type, 'day')
                success_message = f"Dear valued customer, you have successfully subscribed to the {tier.name} Flipstar service, effective from {existing_sms_sub.start_date.strftime('%Y-%m-%d %H:%M')}. You have 1 day remaining in your complimentary free trial. After your free trial concludes, the subscription price will be {tier.price_etb} ETB per {price_period}. To access your premium service, please click on https://uat.flipstar.et?subscription_tp=true&phone={mask_phone_number(phone_number)} and enter your OTP: {otp_code}. To cancel your subscription at any time, please send {stop_keyword} to {tier.short_code}."
                print(f"[SUBSCRIPTION DEBUG] Sending renewal SMS to {phone_number} with OTP: {otp_code}")
                self.send_sms(phone_number, success_message, tier.duration_type)
                print(f"[SUBSCRIPTION DEBUG] SMS-first subscription renewed successfully")
                return Response({'status': 'success', 'message': 'SMS-first subscription renewed'})
            
            # Check for other SMS-first subscriptions of different duration types and cancel them
            other_sms_subs = UserSubscription.objects.filter(
                onevas_phone_number=phone_number,
                status='active',
                subscription_source='sms'
            ).exclude(duration_type=tier.duration_type)
            
            if other_sms_subs.exists():
                print(f"[SUBSCRIPTION DEBUG] Found {other_sms_subs.count()} other SMS-first subscription(s) of different types, cancelling them...")
                for sub in other_sms_subs:
                    sub.cancel(reason='Cancelled due to new SMS-first subscription of different duration type')
                    SubscriptionHistory.objects.create(
                        user=None,
                        subscription=sub,
                        tier=sub.tier,
                        action='cancelled',
                        reason='Cancelled due to new SMS-first subscription of different duration type',
                        metadata={'new_duration_type': tier.duration_type, 'sms_subscription': True}
                    )
                    print(f"[SUBSCRIPTION DEBUG] Cancelled SMS-first subscription ID {sub.id} (duration_type={sub.duration_type})")
            
            # Generate OTP for user to set up their account
            from .services.otp_service import OTPService
            otp_code = OTPService.generate_otp()
            print(f"[SUBSCRIPTION DEBUG] Generated OTP for account setup: {otp_code}")
            
            # Create active subscription linked to phone number (user can log in without OTP)
            try:
                with transaction.atomic():
                    print(f"[SUBSCRIPTION DEBUG] Starting transaction to create SMS-first subscription...")
                    
                    # Check if user has any previous subscription history (for free trial eligibility)
                    has_previous_subscriptions = UserSubscription.objects.filter(
                        onevas_phone_number=phone_number
                    ).exists()
                    
                    # Calculate end date with free trial if eligible
                    base_duration_days = tier.duration_days or 30
                    free_trial_days = 0
                    
                    if not has_previous_subscriptions:
                        # First-time subscriber - grant 1 free trial day
                        free_trial_days = 1
                        print(f"[SUBSCRIPTION DEBUG] First-time subscriber - granting 1 free trial day")
                    else:
                        print(f"[SUBSCRIPTION DEBUG] User has previous subscriptions - no free trial")
                    
                    total_duration_days = base_duration_days + free_trial_days
                    
                    subscription = UserSubscription.objects.create(
                        user=None,  # No user yet - will be linked when they register
                        tier=tier,
                        duration_type=tier.duration_type,
                        onevas_phone_number=phone_number,
                        onevas_subscription_id=str(uuid.uuid4()),
                        status='active',  # Active immediately, not pending
                        start_date=timezone.now(),
                        end_date=timezone.now() + timedelta(days=total_duration_days),
                        subscription_source='sms',  # Track that this came from SMS
                        setup_otp=otp_code,  # Store OTP for account setup
                        free_trial_days=free_trial_days  # Track free trial days granted
                    )
                    print(f"[SUBSCRIPTION DEBUG] Subscription created: ID {subscription.id}, status: {subscription.status}")
                    
                    # Verify the subscription was actually saved
                    saved_subscription = UserSubscription.objects.get(id=subscription.id)
                    print(f"[SUBSCRIPTION DEBUG] Verified subscription in database: ID {saved_subscription.id}, status: {saved_subscription.status}")
                    
                    # Record payment
                    payment = SubscriptionPayment.objects.create(
                        subscription=subscription,
                        user=None,
                        amount=tier.price_etb,
                        payment_method='onevas',
                        duration_type=tier.duration_type,
                        period_start=subscription.start_date,
                        period_end=subscription.end_date,
                        status='completed'
                    )
                    print(f"[SUBSCRIPTION DEBUG] Payment recorded: {tier.price_etb} ETB, payment ID: {payment.id}")
                    
                    # Record history
                    history = SubscriptionHistory.objects.create(
                        user=None,
                        subscription=subscription,
                        tier=tier,
                        action='created',
                        reason='Subscription created via Onevas SMS (active, user not registered yet)',
                        metadata={'webhook_payload': payload, 'sms_subscription': True}
                    )
                    print(f"[SUBSCRIPTION DEBUG] History recorded: action=created, history ID: {history.id}")
                    print(f"[SUBSCRIPTION DEBUG] Transaction committed successfully")
            except Exception as e:
                print(f"[SUBSCRIPTION DEBUG] ERROR during transaction: {str(e)}")
                import traceback
                print(f"[SUBSCRIPTION DEBUG] Traceback: {traceback.format_exc()}")
                return Response({'error': f'Failed to create subscription: {str(e)}'}, status=500)
            
            # Send success SMS with registration info (no OTP needed)
            stop_keywords = {
                'daily': 'STOP1',
                'weekly': 'STOP2',
                'monthly': 'STOP3',
                'ondemand': 'STOP'
            }
            stop_keyword = stop_keywords.get(tier.duration_type, 'STOP')
            # Determine price period based on tier
            price_periods = {
                'daily': 'day',
                'weekly': 'week',
                'monthly': 'month',
                'ondemand': 'use'
            }
            price_period = price_periods.get(tier.duration_type, 'day')
            
            # Customize message based on whether free trial was granted
            if free_trial_days > 0:
                trial_message = f"You have {free_trial_days} day(s) of complimentary free trial. After your free trial concludes, the subscription price will be {tier.price_etb} ETB per {price_period}."
            else:
                trial_message = f"The subscription price is {tier.price_etb} ETB per {price_period}."
            
            success_message = f"Dear valued customer, you have successfully subscribed to the {tier.name} Flipstar service, effective from {subscription.start_date.strftime('%Y-%m-%d %H:%M')}. {trial_message} To access your premium service, please click on https://uat.flipstar.et?subscription_tp=true&phone={mask_phone_number(phone_number)} and enter your OTP: {otp_code}. To cancel your subscription at any time, please send {stop_keyword} to {tier.short_code}."
            print(f"[SUBSCRIPTION DEBUG] Sending success SMS to {phone_number} with OTP: {otp_code}")
            self.send_sms(phone_number, success_message, tier.duration_type)
            print(f"[SUBSCRIPTION DEBUG] SMS-first subscription completed successfully")
            return Response({'status': 'success', 'message': 'Active subscription created via SMS, user can log in without OTP'})
        
        # User exists - proceed with subscription
        print(f"[SUBSCRIPTION DEBUG] User exists, proceeding with subscription for {user.username}")
        
        # Cancel any other active subscriptions of different duration types to prevent conflicts
        other_active_subs = UserSubscription.objects.filter(
            user=user,
            status='active'
        ).exclude(duration_type=tier.duration_type)
        
        if other_active_subs.exists():
            print(f"[SUBSCRIPTION DEBUG] Found {other_active_subs.count()} other active subscription(s) of different types, cancelling them...")
            for sub in other_active_subs:
                sub.cancel(reason='Cancelled due to new subscription of different duration type')
                SubscriptionHistory.objects.create(
                    user=user,
                    subscription=sub,
                    tier=sub.tier,
                    action='cancelled',
                    reason='Cancelled due to new subscription of different duration type',
                    metadata={'new_duration_type': tier.duration_type}
                )
                print(f"[SUBSCRIPTION DEBUG] Cancelled subscription ID {sub.id} (duration_type={sub.duration_type})")
        
        # Check if user already has active subscription of the SAME duration type
        active_sub = UserSubscription.objects.filter(
            user=user,
            status='active',
            duration_type=tier.duration_type
        ).first()

        print(f"[SUBSCRIPTION DEBUG] Active subscription check for duration_type={tier.duration_type}: {'Found' if active_sub else 'Not found'}")
        if active_sub:
            print(f"[SUBSCRIPTION DEBUG] Found active subscription of same type, renewing...")
            # Update existing subscription
            active_sub.tier = tier
            active_sub.duration_type = tier.duration_type
            active_sub.activate()
            
            # Record history
            SubscriptionHistory.objects.create(
                user=user,
                subscription=active_sub,
                tier=tier,
                action='renewed',
                reason='Subscription renewed via Onevas',
                metadata={'webhook_payload': payload}
            )
            
            # Create payment record
            SubscriptionPayment.objects.create(
                subscription=active_sub,
                user=user,
                amount=tier.price_etb,
                payment_method='onevas',
                duration_type=tier.duration_type,
                period_start=active_sub.start_date,
                period_end=active_sub.end_date or timezone.now() + timedelta(days=tier.duration_days or 30),
                status='completed'
            )
            
            # Update user trial status
            profile.is_trial_user = False
            profile.save()

            # Send SMS with registration link and OTP for SMS subscriptions
            stop_keywords = {
                'daily': 'STOP1',
                'weekly': 'STOP2',
                'monthly': 'STOP3',
                'ondemand': 'STOP'
            }
            stop_keyword = stop_keywords.get(tier.duration_type, 'STOP')
            price_periods = {
                'daily': 'day',
                'weekly': 'week',
                'monthly': 'month',
                'ondemand': 'use'
            }
            price_period = price_periods.get(tier.duration_type, 'day')
            renewal_message = f"Dear valued customer, you have successfully subscribed to the {tier.name} Flipstar service, effective from {active_sub.start_date.strftime('%Y-%m-%d %H:%M')}. The subscription price is {tier.price_etb} ETB per {price_period}. To access your premium service, please click on https://uat.flipstar.et?subscription_tp=true&phone={mask_phone_number(phone_number)} and enter your OTP: {otp_code}. To cancel your subscription at any time, please send {stop_keyword} to {tier.short_code}."
            print(f"[SUBSCRIPTION DEBUG] Sending renewal SMS with OTP to {phone_number}")
            sms_result = self.send_sms(phone_number, renewal_message, tier.duration_type)
            print(f"[SUBSCRIPTION DEBUG] Renewal SMS sent: {sms_result}")

            return Response({'status': 'success', 'message': 'Subscription renewed'})
        
        else:
            print(f"[SUBSCRIPTION DEBUG] No active subscription found, creating new subscription")
            # Generate OTP for login
            from .services.otp_service import OTPService
            otp_code = OTPService.generate_otp()
            print(f"[SUBSCRIPTION DEBUG] Generated OTP for new subscription: {otp_code}")
            
            # Create new subscription
            try:
                with transaction.atomic():
                    # Check if user has any previous subscription history (for free trial eligibility)
                    has_previous_subscriptions = UserSubscription.objects.filter(
                        user=user
                    ).exists()
                    
                    # Calculate end date with free trial if eligible
                    base_duration_days = tier.duration_days or 30
                    free_trial_days = 0
                    
                    if not has_previous_subscriptions:
                        # First-time subscriber - grant 1 free trial day
                        free_trial_days = 1
                        print(f"[SUBSCRIPTION DEBUG] First-time subscriber - granting 1 free trial day")
                        # Mark user as having used free trial
                        if user.profile:
                            user.profile.has_used_free_trial = True
                            user.profile.save()
                    else:
                        print(f"[SUBSCRIPTION DEBUG] User has previous subscriptions - no free trial")
                    
                    total_duration_days = base_duration_days + free_trial_days
                    
                    subscription = UserSubscription.objects.create(
                        user=user,
                        tier=tier,
                        duration_type=tier.duration_type,
                        onevas_phone_number=phone_number,
                        onevas_subscription_id=str(uuid.uuid4()),
                        status='pending',
                        subscription_source='app',
                        end_date=timezone.now() + timedelta(days=total_duration_days),
                        setup_otp=otp_code,  # Set OTP for account login
                        free_trial_days=free_trial_days  # Track free trial days granted
                    )
                    print(f"[SUBSCRIPTION DEBUG] New subscription created: ID {subscription.id}, setup_otp: {subscription.setup_otp}, free_trial_days: {free_trial_days}")
                
                subscription.activate()
                
                # Record history
                SubscriptionHistory.objects.create(
                    user=user,
                    subscription=subscription,
                    tier=tier,
                    action='created',
                    reason='Subscription created via Onevas',
                    metadata={'webhook_payload': payload}
                )
                
                # Create payment record
                SubscriptionPayment.objects.create(
                    subscription=subscription,
                    user=user,
                    amount=tier.price_etb,
                    payment_method='onevas',
                    duration_type=tier.duration_type,
                    period_start=subscription.start_date,
                    period_end=subscription.end_date or timezone.now() + timedelta(days=tier.duration_days or 30),
                    status='completed'
                )
                
                # Update user trial status
                user.profile.is_trial_user = False
                user.profile.save()

                # Send SMS with registration link and OTP for SMS subscriptions
                stop_keywords = {
                    'daily': 'STOP1',
                    'weekly': 'STOP2',
                    'monthly': 'STOP3',
                    'ondemand': 'STOP'
                }
                stop_keyword = stop_keywords.get(tier.duration_type, 'STOP')
                price_periods = {
                    'daily': 'day',
                    'weekly': 'week',
                    'monthly': 'month',
                    'ondemand': 'use'
                }
                price_period = price_periods.get(tier.duration_type, 'day')
                confirmation_message = f"Dear valued customer, you have successfully subscribed to the {tier.name} Flipstar service, effective from {subscription.start_date.strftime('%Y-%m-%d %H:%M')}. The subscription price is {tier.price_etb} ETB per {price_period}. To access your premium service, please click on https://uat.flipstar.et?subscription_tp=true&phone={mask_phone_number(phone_number)} and enter your OTP: {otp_code}. To cancel your subscription at any time, please send {stop_keyword} to {tier.short_code}."
                print(f"[SUBSCRIPTION DEBUG] Sending confirmation SMS with OTP to {phone_number}")
                sms_result = self.send_sms(phone_number, confirmation_message, tier.duration_type)
                print(f"[SUBSCRIPTION DEBUG] Confirmation SMS sent: {sms_result}")

                return Response({'status': 'success', 'message': 'Subscription created'})

            except Exception as e:
                print(f"[SUBSCRIPTION DEBUG] Error creating new subscription: {str(e)}")
                import traceback
                print(f"[SUBSCRIPTION DEBUG] Traceback: {traceback.format_exc()}")
                return Response({'error': str(e)}, status=500)
    
    def handle_unsubscription(self, payload, log):
        """Handle unsubscription notification from Onevas"""
        phone_number = payload.get('phone_number')
        product_number = payload.get('product_number')
        
        # Find user by phone number
        try:
            profile = UserProfile.objects.get(phone_number=phone_number)
            user = profile.user
        except UserProfile.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)
        
        # Find active subscription
        subscription = UserSubscription.objects.filter(
            user=user,
            status='active'
        ).first()
        
        if not subscription:
            return Response({'error': 'No active subscription found'}, status=404)
        
        # Cancel subscription
        subscription.cancel(reason='User unsubscribed via Onevas (STOP message)')
        
        # Record history
        SubscriptionHistory.objects.create(
            user=user,
            subscription=subscription,
            tier=subscription.tier,
            action='cancelled',
            reason='User unsubscribed via Onevas',
            metadata={'webhook_payload': payload}
        )
        
        # Send SMS confirmation
        cancellation_message = f"Your {subscription.tier.name} subscription has been cancelled. Thank you for using our service!"
        self.send_sms(phone_number, cancellation_message, subscription.tier.duration_type)
        
        return Response({'status': 'success', 'message': 'Subscription cancelled'})
    
    def handle_renewal(self, payload, log):
        """Handle renewal notification from Onevas"""
        phone_number = payload.get('phone_number')
        next_renewal_date = payload.get('nextRenewalDate')
        product_number = payload.get('product_number')
        
        # Find user by phone number
        try:
            profile = UserProfile.objects.get(phone_number=phone_number)
            user = profile.user
        except UserProfile.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)
        
        # Find active subscription
        subscription = UserSubscription.objects.filter(
            user=user,
            status='active'
        ).first()
        
        if not subscription:
            return Response({'error': 'No active subscription found'}, status=404)
        
        # Update next renewal date
        if next_renewal_date:
            from datetime import datetime
            try:
                subscription.next_renewal_date = datetime.strptime(next_renewal_date, '%Y-%m-%d')
                subscription.save()
            except ValueError:
                pass
        
        return Response({'status': 'success', 'message': 'Renewal date updated'})


class SubscriptionTierViewSet(viewsets.ModelViewSet):
    """Manage subscription tiers"""
    permission_classes = [IsAuthenticated]
    
    queryset = SubscriptionTier.objects.filter(is_active=True)
    serializer_class = None  # Add serializer later
    
    def get_queryset(self):
        return super().get_queryset().order_by('sort_order', 'price_etb')
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get all active tiers"""
        tiers = self.get_queryset()
        data = [{
            'id': str(tier.id),
            'name': tier.name,
            'slug': tier.slug,
            'description': tier.description,
            'duration_type': tier.duration_type,
            'duration_days': tier.duration_days,
            'price_etb': float(tier.price_etb),
            'price_coins': tier.price_coins,
            'onevas_code': tier.onevas_code,
            'short_code': tier.short_code,
            'features': tier.features,
            'privileges': tier.privileges,
        } for tier in tiers]
        return Response(data)


class SubscriptionViewSet(viewsets.ModelViewSet):
    """Manage user subscriptions"""
    permission_classes = [IsAuthenticated]

    queryset = UserSubscription.objects.all()
    serializer_class = None  # Add serializer later

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def list(self, request):
        """Get user's current subscription"""
        subscription = self.get_queryset().filter(status='active').first()
        
        if not subscription:
            # Check if user is in trial
            profile = request.user.profile
            if profile.is_trial_user and profile.trial_end_date and profile.trial_end_date > timezone.now():
                return Response({
                    'status': 'trial',
                    'trial_end_date': profile.trial_end_date.isoformat(),
                    'days_remaining': (profile.trial_end_date - timezone.now()).days
                })
            else:
                return Response({'status': 'no_subscription'})
        
        data = {
            'id': str(subscription.id),
            'tier': {
                'name': subscription.tier.name,
                'duration_type': subscription.tier.duration_type,
                'price_etb': float(subscription.tier.price_etb),
                'privileges': subscription.tier.privileges,
            },
            'status': subscription.status,
            'start_date': subscription.start_date.isoformat(),
            'end_date': subscription.end_date.isoformat() if subscription.end_date else None,
            'next_renewal_date': subscription.next_renewal_date.isoformat() if subscription.next_renewal_date else None,
            'auto_renew': subscription.auto_renew,
        }
        return Response(data)
    
    @action(detail=False, methods=['post'])
    def subscribe(self, request):
        """Initiate subscription request"""
        tier_id = request.data.get('tier_id')
        payment_method = request.data.get('payment_method', 'onevas')  # onevas, telebirr, coins
        
        try:
            tier = SubscriptionTier.objects.get(id=tier_id, is_active=True)
        except SubscriptionTier.DoesNotExist:
            return Response({'error': 'Invalid tier'}, status=400)
        
        user = request.user
        profile = user.profile
        
        # Check if user already has active subscription
        active_sub = UserSubscription.objects.filter(user=user, status='active').first()
        if active_sub:
            return Response({'error': 'Already subscribed'}, status=400)
        
        if payment_method == 'onevas':
            # Send Onevas charging request
            response = self.send_onevas_charge(user, tier)
            return response
        
        elif payment_method == 'coins':
            # Check coin balance
            if not tier.price_coins:
                return Response({'error': 'This tier cannot be purchased with coins'}, status=400)
            
            if profile.coins < tier.price_coins:
                return Response({'error': 'Insufficient coins'}, status=400)
            
            # Deduct coins and activate subscription
            with transaction.atomic():
                # Create coin transaction
                CoinTransaction.objects.create(
                    user=user,
                    transaction_type='subscription',
                    amount=-tier.price_coins,
                    balance_after=profile.coins - tier.price_coins,
                    description=f'Subscription: {tier.name}',
                    reference_id=str(tier.id),
                    reference_type='subscription'
                )
                
                # Update profile
                profile.coins -= tier.price_coins
                profile.coins_spent_total += tier.price_coins
                profile.is_trial_user = False
                profile.save()
                
                # Create subscription
                subscription = UserSubscription.objects.create(
                    user=user,
                    tier=tier,
                    duration_type=tier.duration_type,
                    status='pending'
                )
                subscription.activate()
                
                # Record history
                SubscriptionHistory.objects.create(
                    user=user,
                    subscription=subscription,
                    tier=tier,
                    action='created',
                    reason='Purchased with coins',
                    metadata={'payment_method': 'coins', 'amount': tier.price_coins}
                )
                
                # Create payment record
                SubscriptionPayment.objects.create(
                    subscription=subscription,
                    user=user,
                    amount=tier.price_etb,
                    payment_method='coins',
                    duration_type=tier.duration_type,
                    period_start=subscription.start_date,
                    period_end=subscription.end_date or timezone.now() + timedelta(days=tier.duration_days or 30),
                    status='completed'
                )
            
            return Response({'status': 'success', 'message': 'Subscription activated'})
        
        elif payment_method == 'telebirr':
            # Initiate Telebirr payment
            response = self.initiate_telebirr_payment(user, tier)
            return response
        
        else:
            return Response({'error': 'Invalid payment method'}, status=400)
    
    def send_onevas_charge(self, user, tier):
        """Send charging request to Onevas"""
        profile = user.profile
        
        # Onevas charging endpoint
        url = 'https://onevas.alet.io/api/partner/charge'
        
        payload = {
            'application_key': tier.application_key,
            'phone_number': profile.phone_number,
            'product_number': tier.product_id
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                return Response({
                    'status': 'pending',
                    'message': 'Charging request sent. Please confirm via SMS.',
                    'onevas_code': tier.onevas_code,
                    'short_code': tier.short_code
                })
            else:
                return Response({'error': 'Failed to send charging request'}, status=500)
        
        except Exception as e:
            return Response({'error': str(e)}, status=500)
    
    def initiate_telebirr_payment(self, user, tier):
        """Initiate Telebirr payment for subscription"""
        profile = user.profile
        
        try:
            response = telebirr_service.initiate_payment(
                amount=float(tier.price_etb),
                phone_number=profile.phone_number,
                user_id=user.id,
                package_id=tier.id
            )
            
            if response.get('success'):
                # Create pending payment record
                payment = SubscriptionPayment.objects.create(
                    user=user,
                    subscription=None,  # Will be linked after payment success
                    amount=tier.price_etb,
                    currency='ETB',
                    status='pending',
                    payment_method='telebirr',
                    onevas_transaction_id=response.get('transaction_id'),
                    period_start=timezone.now(),
                    period_end=timezone.now() + timedelta(days=tier.duration_days or 30),
                )
                
                return Response({
                    'status': 'pending',
                    'message': 'Payment initiated. Please complete payment via Telebirr.',
                    'payment_url': response.get('payment_url'),
                    'transaction_id': response.get('transaction_id'),
                    'payment_id': str(payment.id)
                })
            else:
                return Response({'error': response.get('error', 'Payment initiation failed')}, status=400)
                
        except Exception as e:
            return Response({'error': str(e)}, status=500)
    
    @action(detail=False, methods=['post'])
    def unsubscribe(self, request):
        """Cancel subscription"""
        subscription = self.get_queryset().filter(status='active').first()
        
        if not subscription:
            return Response({'error': 'No active subscription'}, status=400)
        
        reason = request.data.get('reason', 'User requested cancellation')
        subscription.cancel(reason=reason)
        
        # Record history
        SubscriptionHistory.objects.create(
            user=request.user,
            subscription=subscription,
            tier=subscription.tier,
            action='cancelled',
            reason=reason
        )
        
        return Response({'status': 'success', 'message': 'Subscription cancelled'})
    
    @action(detail=False, methods=['get'])
    def history(self, request):
        """Get subscription history"""
        history = SubscriptionHistory.objects.filter(user=request.user).order_by('-created_at')
        
        data = [{
            'action': item.action,
            'tier_name': item.tier.name if item.tier else None,
            'reason': item.reason,
            'created_at': item.created_at.isoformat(),
        } for item in history]
        
        return Response(data)


class TrialPopupViewSet(viewsets.ModelViewSet):
    """Track trial popup interactions"""
    permission_classes = [IsAuthenticated]
    
    queryset = TrialPopupLog.objects.all()
    serializer_class = None
    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
    
    def create(self, request):
        """Log popup interaction"""
        trigger_action = request.data.get('trigger_action')
        trigger_screen = request.data.get('trigger_screen')
        user_action = request.data.get('user_action')
        
        # Update user profile
        profile = request.user.profile
        profile.trial_interaction_count += 1
        if user_action:
            profile.trial_popup_shown_count += 1
        profile.save()
        
        # Log the popup
        TrialPopupLog.objects.create(
            user=request.user,
            trigger_action=trigger_action,
            trigger_screen=trigger_screen,
            user_action=user_action
        )
        
        return Response({'status': 'success'})


class CoinTransactionViewSet(viewsets.ModelViewSet):
    """Manage coin transactions"""
    permission_classes = [IsAuthenticated]
    
    queryset = CoinTransaction.objects.all()
    serializer_class = None
    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user).order_by('-created_at')
    
    def list(self, request):
        """Get user's coin transactions"""
        transactions = self.get_queryset()
        
        data = [{
            'id': str(t.id),
            'transaction_type': t.transaction_type,
            'amount': t.amount,
            'balance_after': t.balance_after,
            'description': t.description,
            'created_at': t.created_at.isoformat(),
        } for t in transactions]
        
        return Response(data)
    
    @action(detail=False, methods=['post'])
    def purchase(self, request):
        """Purchase coins via Telebirr or airtime"""
        amount = request.data.get('amount')  # ETB amount
        payment_method = request.data.get('payment_method', 'telebirr')
        
        # Coin conversion: 10 ETB = 100 coins (1 ETB = 10 coins)
        coins = int(amount * 10)
        
        if payment_method == 'telebirr':
            # Initiate Telebirr payment
            from .telebirr_service import TelebirrService
            
            try:
                telebirr = TelebirrService()
                response = telebirr.create_payment(
                    amount=float(amount),
                    phone_number=request.user.profile.phone_number,
                    description=f'Purchase {coins} coins'
                )
                
                if response.get('success'):
                    return Response({
                        'status': 'pending',
                        'message': f'Purchasing {coins} coins via Telebirr',
                        'payment_url': response.get('payment_url'),
                        'coins': coins
                    })
                else:
                    return Response({'error': response.get('error', 'Payment failed')}, status=500)
            
            except Exception as e:
                return Response({'error': str(e)}, status=500)
        
        else:
            return Response({'error': 'Invalid payment method'}, status=400)


class AdminSubscriptionViewSet(viewsets.ModelViewSet):
    """Admin subscription management"""
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Check admin permissions
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            return UserSubscription.objects.none()
        
        return UserSubscription.objects.all()
    
    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """Get subscription analytics"""
        if not self._is_admin(request):
            return Response({'error': 'Unauthorized'}, status=403)
        
        total_subscriptions = UserSubscription.objects.count()
        active_subscriptions = UserSubscription.objects.filter(status='active').count()
        expired_subscriptions = UserSubscription.objects.filter(status='expired').count()
        
        # Revenue calculation
        total_revenue = sum(
            p.amount for p in SubscriptionPayment.objects.filter(status='completed')
        )
        
        # Trial users
        trial_users = UserProfile.objects.filter(is_trial_user=True).count()
        
        # Tier distribution
        tier_distribution = {}
        for tier in SubscriptionTier.objects.all():
            count = UserSubscription.objects.filter(tier=tier, status='active').count()
            tier_distribution[tier.name] = count
        
        data = {
            'total_subscriptions': total_subscriptions,
            'active_subscriptions': active_subscriptions,
            'expired_subscriptions': expired_subscriptions,
            'total_revenue': float(total_revenue),
            'trial_users': trial_users,
            'tier_distribution': tier_distribution,
        }
        
        return Response(data)
    
    @action(detail=False, methods=['get'])
    def charging_analytics(self, request):
        """Get real-time charging analytics"""
        if not self._is_admin(request):
            return Response({'error': 'Unauthorized'}, status=403)
        
        from django.db.models import Sum, Count
        from datetime import datetime, timedelta
        
        # Get time ranges
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Active subscriptions by tier
        active_by_tier = UserSubscription.objects.filter(
            status='active'
        ).values('tier__name').annotate(
            count=Count('id'),
            total_revenue=Sum('tier__price_etb')
        ).order_by('-total_revenue')
        
        # Today's revenue
        today_payments = SubscriptionPayment.objects.filter(
            status='completed',
            period_start__date=today
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        # This week's revenue
        week_payments = SubscriptionPayment.objects.filter(
            status='completed',
            period_start__date__gte=week_ago
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        # This month's revenue
        month_payments = SubscriptionPayment.objects.filter(
            status='completed',
            period_start__date__gte=month_ago
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        # Cancellations this month
        month_cancellations = SubscriptionHistory.objects.filter(
            action='cancelled',
            created_at__date__gte=month_ago
        ).count()
        
        # Expected monthly recurring revenue (MRR)
        active_subs = UserSubscription.objects.filter(status='active')
        mrr = sum([sub.tier.price_etb for sub in active_subs if sub.tier])
        
        # Recent transactions
        recent_transactions = SubscriptionPayment.objects.filter(
            status='completed'
        ).order_by('-created_at')[:20]
        
        recent_data = []
        for tx in recent_transactions:
            recent_data.append({
                'id': str(tx.id),
                'amount': float(tx.amount),
                'payment_method': tx.payment_method,
                'tier': tx.subscription.tier.name if tx.subscription and tx.subscription.tier else 'N/A',
                'user': tx.subscription.user.username if tx.subscription and tx.subscription.user else 'N/A',
                'date': tx.period_start.strftime('%Y-%m-%d %H:%M') if tx.period_start else 'N/A',
                'status': tx.status
            })
        
        return Response({
            'active_subscriptions': {
                'total': active_subs.count(),
                'by_tier': list(active_by_tier),
                'mrr': float(mrr)
            },
            'revenue': {
                'today': {
                    'total': float(today_payments['total'] or 0),
                    'count': today_payments['count'] or 0
                },
                'week': {
                    'total': float(week_payments['total'] or 0),
                    'count': week_payments['count'] or 0
                },
                'month': {
                    'total': float(month_payments['total'] or 0),
                    'count': month_payments['count'] or 0
                }
            },
            'cancellations': {
                'month_count': month_cancellations
            },
            'recent_transactions': recent_data
        })
    
    @action(detail=False, methods=['get'])
    def revenue(self, request):
        """Get revenue reports"""
        if not self._is_admin(request):
            return Response({'error': 'Unauthorized'}, status=403)
        
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        payments = SubscriptionPayment.objects.filter(status='completed')
        
        if date_from:
            from datetime import datetime
            payments = payments.filter(created_at__gte=datetime.fromisoformat(date_from))
        if date_to:
            from datetime import datetime
            payments = payments.filter(created_at__lte=datetime.fromisoformat(date_to))
        
        revenue_by_tier = {}
        for payment in payments:
            tier_name = payment.subscription.tier.name if payment.subscription.tier else 'Unknown'
            revenue_by_tier[tier_name] = revenue_by_tier.get(tier_name, 0) + float(payment.amount)
        
        data = {
            'total_revenue': sum(float(p.amount) for p in payments),
            'revenue_by_tier': revenue_by_tier,
            'payment_count': payments.count(),
        }
        
        return Response(data)
    
    def _is_admin(self, request):
        """Check if user has admin permissions"""
        return request.user.is_staff or request.user.is_superuser
