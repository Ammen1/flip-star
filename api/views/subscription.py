import logging
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.integrations.telebirr.checkout import telebirr_service
from api.integrations.telebirr.direct_debit import telebirr_direct_debit_service
from api.models import UserProfile
from api.models.subscription import (
    OnevasWebhookLog,
    SubscriptionHistory,
    SubscriptionPayment,
    SubscriptionTier,
    TrialPopupLog,
)
from api.models.subscription import (
    SubscriptionCoinTransaction as CoinTransaction,
)
from api.models.subscription import (
    SubscriptionPlan as UserSubscription,
)
from api.services.superapp_sms_service import superapp_sms_service
from common.security import EncryptedPayloadMixin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Onevas configuration
# ---------------------------------------------------------------------------
# All of this used to be hardcoded here, including four live per-tier
# application keys. Everything now resolves through Django settings, which read
# environment -> Vault -> .env. See docs/secrets.md.
#
# The authoritative source for per-tier provisioning is the SubscriptionTier row
# (it carries spid / service_id / product_id / application_key). ONEVAS_PRODUCTS
# is only the fallback for tiers with nothing stored.

ONEVAS_SMS_URL = settings.ONEVAS_SMS_URL
ONEVAS_APPLICATION_KEY = settings.ONEVAS_APPLICATION_KEY
ONEVAS_PRODUCT_NUMBER = settings.ONEVAS_PRODUCT_NUMBER
ONEVAS_PRODUCTS = settings.ONEVAS_PRODUCTS

# App Links (placeholders - update with actual URLs)
# WEB_APP_LINK = "https://api.uat.flipstar.et?subscription_tp=true"
WEB_APP_LINK = "https://api.uat.flipstar.et"
MOBILE_APP_LINK = "https://play.google.com/store/apps/details?id=com.postworq.mobile"

# Helper function to mask phone number (show first 9 digits, mask last 4)
def mask_phone_number(phone):
    if not phone or len(phone) < 4:
        return phone
    return phone[:9] + '****'


class UserSubscriptionStatusView(EncryptedPayloadMixin, APIView):
    """Check user subscription status"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current user's subscription status"""
        try:
            from django.utils import timezone

            from api.models import Subscription

            print(f'[SUBSCRIPTION STATUS] Checking subscription for user: {request.user.username} (ID: {request.user.id})')

            # First check new UserSubscription model
            active_subscription = UserSubscription.objects.filter(
                user=request.user,
                status='active',
                end_date__gt=timezone.now()
            ).first()

            print(f'[SUBSCRIPTION STATUS] UserSubscription active found: {active_subscription is not None}')
            if active_subscription:
                print(f'[SUBSCRIPTION STATUS] UserSubscription: ID={active_subscription.id}, status={active_subscription.status}, end_date={active_subscription.end_date}')

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

            # Fallback to old Subscription model
            old_subscription = Subscription.objects.filter(
                user=request.user,
                expires_at__gt=timezone.now()
            ).first()

            print(f'[SUBSCRIPTION STATUS] Old Subscription active found: {old_subscription is not None}')
            if old_subscription:
                print(f'[SUBSCRIPTION STATUS] Old Subscription: ID={old_subscription.id}, plan={old_subscription.plan}, expires_at={old_subscription.expires_at}')

            if old_subscription:
                return Response({
                    'has_subscription': True,
                    'subscription': {
                        'id': str(old_subscription.id),
                        'tier': {
                            'id': None,
                            'name': old_subscription.plan,
                            'duration_type': None,
                            'price_etb': 0,
                        },
                        'status': 'active',
                        'start_date': old_subscription.started_at.isoformat() if old_subscription.started_at else None,
                        'end_date': old_subscription.expires_at.isoformat() if old_subscription.expires_at else None,
                        'auto_renew': False,
                    }
                })

            # No active subscription found - check for any subscriptions
            any_subscription = UserSubscription.objects.filter(user=request.user)
            any_old_subscription = Subscription.objects.filter(user=request.user)

            print(f'[SUBSCRIPTION STATUS] Any UserSubscription count: {any_subscription.count()}')
            print(f'[SUBSCRIPTION STATUS] Any old Subscription count: {any_old_subscription.count()}')

            if any_subscription.exists():
                for sub in any_subscription:
                    print(f'[SUBSCRIPTION STATUS] UserSubscription: status={sub.status}, end_date={sub.end_date}')

            if any_old_subscription.exists():
                for sub in any_old_subscription:
                    print(f'[SUBSCRIPTION STATUS] Old Subscription: plan={sub.plan}, expires_at={sub.expires_at}')

            return Response({
                'has_subscription': False,
                'subscription': None,
                'has_had_subscription': any_subscription.exists() or any_old_subscription.exists(),
                'message': 'No active subscription found'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f'[SUBSCRIPTION STATUS] Error: {e}')
            import traceback
            traceback.print_exc()
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
                print("[SUBSCRIPTION DEBUG] User not registered, checking for SMS-first subscription")

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
            # Map tier duration type to service name and resubscribe keyword for message
            service_names = {
                'daily': 'Daily',
                'weekly': 'Weekly',
                'monthly': 'Monthly',
                'ondemand': 'On-Demand'
            }
            service_name = service_names.get(tier.duration_type, tier.name)

            # Map duration type to the correct resubscribe keyword for the message
            resubscribe_keyword_map = {
                'daily': '1',
                'weekly': '2',
                'monthly': '3',
                'ondemand': '4'
            }
            message_keyword = resubscribe_keyword_map.get(tier.duration_type, '1')
            cancellation_message = f"You have successfully unsubscribed from the {service_name} service. To subscribe again, send {message_keyword} to {tier.short_code}."
            print(f"[SUBSCRIPTION DEBUG] Sending cancellation SMS to {phone_number}")
            sms_sent = self.send_sms(phone_number, cancellation_message, tier.duration_type)
            print(f"[SUBSCRIPTION DEBUG] Cancellation SMS sent: {sms_sent}")
        else:
            print("[SUBSCRIPTION DEBUG] WARNING: subscription.tier is None, cannot send SMS with tier info")
            cancellation_message = "You have successfully unsubscribed from the Flipstar service."
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
                print("[SUBSCRIPTION DEBUG] Routing to handle_subscription")
                response = self.handle_subscription(payload, log)
            elif webhook_type == 'unsubscription':
                print("[SUBSCRIPTION DEBUG] Routing to handle_unsubscription")
                response = self.handle_unsubscription(payload, log)
            elif webhook_type == 'renewal':
                print("[SUBSCRIPTION DEBUG] Routing to handle_renewal")
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
                '1': 'daily',
                '2': 'weekly',
                '3': 'monthly',
                '4': 'ondemand',
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
            print("[SUBSCRIPTION DEBUG] Creating SMS-first subscription (user not registered)")

            # Check if there's already an SMS-first subscription of the same duration type for this phone
            existing_sms_sub = UserSubscription.objects.filter(
                onevas_phone_number=phone_number,
                status='active',
                subscription_source='sms',
                duration_type=tier.duration_type
            ).first()

            if existing_sms_sub:
                print("[SUBSCRIPTION DEBUG] Found existing SMS-first subscription of same type, renewing it...")
                # Renew existing subscription
                existing_sms_sub.tier = tier
                existing_sms_sub.duration_type = tier.duration_type
                existing_sms_sub.activate()

                from api.services.otp import OTPService
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
                success_message = f"Dear valued customer, you have successfully subscribed to the {tier.name} Flipstar service, effective from {existing_sms_sub.start_date.strftime('%Y-%m-%d %H:%M')}. You have 1 day remaining in your complimentary free trial. After your free trial concludes, the subscription price will be {tier.price_etb} ETB per {price_period}. To access your premium service, please click on https://api.uat.flipstar.et?subscription_tp=true&phone={mask_phone_number(phone_number)} and enter your OTP: {otp_code}. To cancel your subscription at any time, please send {stop_keyword} to {tier.short_code}."
                print(f"[SUBSCRIPTION DEBUG] Sending renewal SMS to {phone_number} with OTP: {otp_code}")
                self.send_sms(phone_number, success_message, tier.duration_type)
                print("[SUBSCRIPTION DEBUG] SMS-first subscription renewed successfully")
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
            from api.services.otp import OTPService
            otp_code = OTPService.generate_otp()
            print(f"[SUBSCRIPTION DEBUG] Generated OTP for account setup: {otp_code}")

            # Create active subscription linked to phone number (user can log in without OTP)
            try:
                with transaction.atomic():
                    print("[SUBSCRIPTION DEBUG] Starting transaction to create SMS-first subscription...")

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
                        print("[SUBSCRIPTION DEBUG] First-time subscriber - granting 1 free trial day")
                    else:
                        print("[SUBSCRIPTION DEBUG] User has previous subscriptions - no free trial")

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
                    print("[SUBSCRIPTION DEBUG] Transaction committed successfully")
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

            success_message = f"Dear valued customer, you have successfully subscribed to the {tier.name} Flipstar service, effective from {subscription.start_date.strftime('%Y-%m-%d %H:%M')}. {trial_message} To access your premium service, please click on https://api.uat.flipstar.et?subscription_tp=true&phone={phone_number} and enter your OTP: {otp_code}. To cancel your subscription at any time, please send {stop_keyword} to {tier.short_code}."
            print(f"[SUBSCRIPTION DEBUG] Sending success SMS to {phone_number} with OTP: {otp_code}")
            self.send_sms(phone_number, success_message, tier.duration_type)
            print("[SUBSCRIPTION DEBUG] SMS-first subscription completed successfully")
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
            print("[SUBSCRIPTION DEBUG] Found active subscription of same type, renewing...")
            # Generate OTP for login
            from api.services.otp import OTPService
            otp_code = OTPService.generate_otp()
            print(f"[SUBSCRIPTION DEBUG] Generated OTP for renewal: {otp_code}")

            # Update existing subscription
            active_sub.tier = tier
            active_sub.duration_type = tier.duration_type
            active_sub.setup_otp = otp_code  # Store OTP for login
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
            renewal_message = f"Dear valued customer, you have successfully subscribed to the {tier.name} Flipstar service, effective from {active_sub.start_date.strftime('%Y-%m-%d %H:%M')}. The subscription price is {tier.price_etb} ETB per {price_period}. To access your premium service, please click on https://api.uat.flipstar.et?subscription_tp=true&phone={phone_number}&existing_user=true and enter your OTP: {otp_code}. To cancel your subscription at any time, please send {stop_keyword} to {tier.short_code}."
            print(f"[SUBSCRIPTION DEBUG] Sending renewal SMS with OTP to {phone_number}")
            sms_result = self.send_sms(phone_number, renewal_message, tier.duration_type)
            print(f"[SUBSCRIPTION DEBUG] Renewal SMS sent: {sms_result}")

            return Response({'status': 'success', 'message': 'Subscription renewed'})

        else:
            print("[SUBSCRIPTION DEBUG] No active subscription found, creating new subscription")
            # Generate OTP for login
            from api.services.otp import OTPService
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
                        print("[SUBSCRIPTION DEBUG] First-time subscriber - granting 1 free trial day")
                        # Mark user as having used free trial
                        if user.profile:
                            user.profile.has_used_free_trial = True
                            user.profile.save()
                    else:
                        print("[SUBSCRIPTION DEBUG] User has previous subscriptions - no free trial")

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
                        free_trial_days=free_trial_days,  # Track free trial days granted
                        payment_method='onevas'  # Onevas webhook always uses onevas payment method
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
                confirmation_message = f"Dear valued customer, you have successfully subscribed to the {tier.name} Flipstar service, effective from {subscription.start_date.strftime('%Y-%m-%d %H:%M')}. The subscription price is {tier.price_etb} ETB per {price_period}. To access your premium service, please click on https://api.uat.flipstar.et?subscription_tp=true&phone={phone_number}&existing_user=true and enter your OTP: {otp_code}. To cancel your subscription at any time, please send {stop_keyword} to {tier.short_code}."
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


class SubscriptionTierViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    """Manage subscription tiers"""
    permission_classes = [IsAuthenticated]

    queryset = SubscriptionTier.objects.filter(is_active=True)
    serializer_class = None  # Add serializer later

    def get_queryset(self):
        return super().get_queryset().order_by('sort_order', 'price_etb')

    def list(self, request):
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

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get all active tiers (alias for list)"""
        return self.list(request)


class SubscriptionViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
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

            # Deduct coins and activate subscription. deduct_coins locks the
            # profile row, re-reads it fresh, and raises ValueError if the
            # balance is insufficient -- see UserProfile._apply_delta's
            # docstring for why that has to happen under the lock rather
            # than as a separate check beforehand: a concurrent purchase
            # that already spent this balance must still be caught here.
            try:
                with transaction.atomic():
                    profile.deduct_coins(tier.price_coins, total_field='coins_spent_total')

                    # Create coin transaction (balance_after reflects the
                    # deduction above, not the pre-check snapshot).
                    CoinTransaction.objects.create(
                        user=user,
                        transaction_type='subscription',
                        amount=-tier.price_coins,
                        balance_after=profile.coins,
                        description=f'Subscription: {tier.name}',
                        reference_id=str(tier.id),
                        reference_type='subscription'
                    )

                    profile.is_trial_user = False
                    profile.save(update_fields=['is_trial_user'])

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
            except ValueError as exc:
                return Response({'error': str(exc)}, status=400)

            return Response({'status': 'success', 'message': 'Subscription activated'})

        elif payment_method == 'telebirr':
            # Initiate Telebirr payment
            response = self.initiate_telebirr_payment(user, tier)
            return response

        else:
            return Response({'error': 'Invalid payment method'}, status=400)

    def send_onevas_charge(self, user, tier):
        """DISABLED: Ethio Telecom SIM cards are only accessible for SMS OTP purposes.
        Onevas charging has been disabled to ensure phone numbers are used solely for OTP verification."""
        return Response(
            {'error': 'Onevas charging is disabled. Ethio Telecom SIM cards are only accessible for SMS OTP verification.'},
            status=status.HTTP_403_FORBIDDEN
        )

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


class TrialPopupViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
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


class CoinTransactionViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
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
            from api.integrations.telebirr.checkout import TelebirrService

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

    def _type_filter(self, request):
        """Build queryset filters from ?type= query param.

        type=ondemand     -> only OnDemand tiers
        type=subscription -> only recurring tiers (daily/weekly/monthly)
        (none)            -> no filter
        Returns dict with `sub_filter` (for UserSubscription / SubscriptionPayment via subscription__) and `tier_filter` (for SubscriptionTier).
        """
        t = (request.query_params.get('type') or '').lower()
        if t == 'ondemand':
            return {
                'sub_filter': {'tier__duration_type': 'ondemand'},
                'pay_filter': {'subscription__tier__duration_type': 'ondemand'},
                'tier_filter': {'duration_type': 'ondemand'},
            }
        if t == 'subscription':
            recurring = ['daily', 'weekly', 'monthly']
            return {
                'sub_filter': {'tier__duration_type__in': recurring},
                'pay_filter': {'subscription__tier__duration_type__in': recurring},
                'tier_filter': {'duration_type__in': recurring},
            }
        return {'sub_filter': {}, 'pay_filter': {}, 'tier_filter': {}}

    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """Get subscription analytics. Optional ?type=subscription|ondemand to scope."""
        if not self._is_admin(request):
            return Response({'error': 'Unauthorized'}, status=403)

        f = self._type_filter(request)

        sub_qs = UserSubscription.objects.filter(**f['sub_filter'])
        pay_qs = SubscriptionPayment.objects.filter(status='completed', **f['pay_filter'])

        total_subscriptions = sub_qs.count()
        active_subscriptions = sub_qs.filter(status='active').count()
        expired_subscriptions = sub_qs.filter(status='expired').count()

        # Revenue calculation
        total_revenue = sum(p.amount for p in pay_qs)

        # Trial users (only meaningful for the subscription view)
        if not f['tier_filter'] or f['tier_filter'].get('duration_type') != 'ondemand':
            trial_users = UserProfile.objects.filter(is_trial_user=True).count()
        else:
            trial_users = 0

        # Tier distribution
        tier_distribution = {}
        for tier in SubscriptionTier.objects.filter(**f['tier_filter']):
            count = sub_qs.filter(tier=tier, status='active').count()
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
        """Get real-time charging analytics. Optional ?type=subscription|ondemand."""
        if not self._is_admin(request):
            return Response({'error': 'Unauthorized'}, status=403)

        from datetime import timedelta

        from django.db.models import Count, Sum

        f = self._type_filter(request)
        sub_filter = f['sub_filter']
        pay_filter = f['pay_filter']

        # Get time ranges
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        # Active subscriptions by tier
        active_by_tier = UserSubscription.objects.filter(
            status='active', **sub_filter
        ).values('tier__name').annotate(
            count=Count('id'),
            total_revenue=Sum('tier__price_etb')
        ).order_by('-total_revenue')

        # Today's revenue
        today_payments = SubscriptionPayment.objects.filter(
            status='completed',
            period_start__date=today,
            **pay_filter,
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )

        # This week's revenue
        week_payments = SubscriptionPayment.objects.filter(
            status='completed',
            period_start__date__gte=week_ago,
            **pay_filter,
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )

        # This month's revenue
        month_payments = SubscriptionPayment.objects.filter(
            status='completed',
            period_start__date__gte=month_ago,
            **pay_filter,
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )

        # Cancellations this month (scoped by tier filter when provided)
        cancel_qs = SubscriptionHistory.objects.filter(
            action='cancelled',
            created_at__date__gte=month_ago,
        )
        if sub_filter:
            # SubscriptionHistory has its own tier FK
            tier_only = {k.replace('tier__', 'tier__'): v for k, v in sub_filter.items()}
            cancel_qs = cancel_qs.filter(**tier_only)
        month_cancellations = cancel_qs.count()

        # Expected monthly recurring revenue (MRR)
        active_subs = UserSubscription.objects.filter(status='active', **sub_filter)
        mrr = sum([sub.tier.price_etb for sub in active_subs if sub.tier])

        # Recent transactions
        recent_transactions = SubscriptionPayment.objects.filter(
            status='completed', **pay_filter,
        ).order_by('-created_at')[:20]

        recent_data = []
        for tx in recent_transactions:
            sub = tx.subscription
            tier = sub.tier if sub else None
            user_obj = (sub.user if sub and sub.user else tx.user) if hasattr(tx, 'user') else (sub.user if sub else None)
            phone = ''
            if sub and getattr(sub, 'onevas_phone_number', None):
                phone = sub.onevas_phone_number
            elif user_obj and hasattr(user_obj, 'profile') and getattr(user_obj.profile, 'phone_number', None):
                phone = user_obj.profile.phone_number

            recent_data.append({
                'id': str(tx.id),
                'amount': float(tx.amount),
                'currency': tx.currency,
                'payment_method': tx.payment_method,
                'tier': tier.name if tier else 'N/A',
                'duration_type': tx.duration_type or (tier.duration_type if tier else ''),
                'duration_days': tier.duration_days if tier else None,
                'user': user_obj.username if user_obj else 'N/A',
                'user_id': user_obj.id if user_obj else None,
                'email': user_obj.email if user_obj else '',
                'phone': phone,
                'period_start': tx.period_start.strftime('%Y-%m-%d %H:%M') if tx.period_start else '',
                'period_end': tx.period_end.strftime('%Y-%m-%d %H:%M') if tx.period_end else '',
                'date': tx.created_at.strftime('%Y-%m-%d %H:%M') if tx.created_at else (tx.period_start.strftime('%Y-%m-%d %H:%M') if tx.period_start else 'N/A'),
                'status': tx.status,
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


# ---------------------------------------------------------------------------
# One-Time Subscription Flow (mimics coin purchase)
# ---------------------------------------------------------------------------
# The live replacement for the old recurring-mandate flow: buy once, mimic
# a coin purchase, renew manually. api/views/wallet.py's telebirr_callback
# already delegates every 'SUB'-prefixed order here.

@api_view(['POST'])
@permission_classes([AllowAny])
def telebirr_one_time_initiate(request):
    """
    Initiate a one-time Telebirr payment for subscription (no recurring mandate).
    Mimics the coin purchase flow.

    Request body: {
        plan_type: 'daily' | 'weekly' | 'monthly',
        phone_number: string (required for unauthenticated users)
    }
    Returns: {
        raw_request: string (signed for SuperApp js_fun_start_pay),
        merch_order_id: string
    }
    """
    plan_type = request.data.get('plan_type')
    phone_number = request.data.get('phone_number')

    if not plan_type:
        return Response({'error': 'plan_type is required'}, status=status.HTTP_400_BAD_REQUEST)

    tier = SubscriptionTier.objects.filter(duration_type=plan_type, is_active=True).first()
    if not tier:
        return Response({'error': f'No active subscription tier found for plan type: {plan_type}'},
                        status=status.HTTP_400_BAD_REQUEST)

    if not request.user.is_authenticated and not phone_number:
        return Response({'error': 'phone_number is required for unauthenticated users'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        if request.user.is_authenticated:
            user_id = str(request.user.id)
        else:
            # Last 8 digits of phone number for uniqueness
            user_id = phone_number[-8:] if phone_number else 'ANON'
        merch_order_id = f'SUB{timezone.now().strftime("%Y%m%d%H%M%S")}{user_id}'

        amount = f'{float(tier.price_etb):.2f}'
        title = f'{tier.name} Subscription'

        result = telebirr_service.create_order_ondemand(
            title=title,
            amount=amount,
            merch_order_id=merch_order_id,
        )

        if not result.get('success'):
            logger.error('[TELEBIRR ONE-TIME] Failed to create Telebirr order: %s', result)
            return Response({'error': 'Failed to create Telebirr order', 'details': result.get('error')},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        raw_request = result.get('raw_request')
        prepay_id = result.get('prepay_id')

        now = timezone.now()
        end_date = now + timezone.timedelta(days=tier.duration_days) if tier.duration_days else None

        # Prevent duplicate/overlapping purchases. For authenticated users,
        # check by request.user directly. For unauthenticated (new SuperApp)
        # users, look up any account already linked to this phone number via
        # phone number variants, same normalization telebirr_auth uses.
        existing_active = None
        if request.user.is_authenticated:
            existing_active = UserSubscription.objects.filter(
                user=request.user,
                status='active',
                end_date__gt=timezone.now()
            ).first()
        elif phone_number:
            cleaned_phone = ''.join(filter(str.isdigit, phone_number))
            phone_variants = {cleaned_phone}
            if cleaned_phone.startswith('251'):
                phone_variants.add('0' + cleaned_phone[3:])
            elif cleaned_phone.startswith('0'):
                phone_variants.add('251' + cleaned_phone[1:])

            existing_profile = UserProfile.objects.filter(phone_number__in=phone_variants).first()
            if existing_profile:
                existing_active = UserSubscription.objects.filter(
                    user=existing_profile.user,
                    status='active',
                    end_date__gt=timezone.now()
                ).first()

        if existing_active:
            return Response({
                'error': 'You already have an active subscription. Please cancel it first or wait for it to expire.',
                'existing_subscription': {
                    'id': existing_active.id,
                    'tier': existing_active.tier.name,
                    'end_date': existing_active.end_date.isoformat() if existing_active.end_date else None
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        # For unauthenticated users, user is None; the webhook links/creates
        # the account once payment is confirmed.
        subscription = UserSubscription.objects.create(
            user=request.user if request.user.is_authenticated else None,
            tier=tier,
            payment_method='telebirr',
            duration_type=plan_type,
            status='pending',
            payment_reference=merch_order_id,
            telebirr_phone_number=phone_number if not request.user.is_authenticated else (
                request.user.profile.phone_number if hasattr(request.user, 'profile') and request.user.profile else None
            ),
            auto_renew=False,
            start_date=now,
            end_date=end_date,
        )

        logger.info('[TELEBIRR ONE-TIME] Created pending subscription %s (merch_order_id=%s)', subscription.id, merch_order_id)

        return Response({
            'success': True,
            'raw_request': raw_request,
            'merch_order_id': merch_order_id,
            'prepay_id': prepay_id,
            'plan_type': plan_type,
        })

    except Exception as e:
        logger.exception('[TELEBIRR ONE-TIME] Initiate error: %s', e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])  # Telebirr calls this without authentication
def telebirr_one_time_callback(request):
    """
    Handle Telebirr async payment notification for one-time subscription.
    Mimics the coin purchase callback (api/views/wallet.py::telebirr_callback).

    Telebirr is documented to retry callbacks, so a duplicate or concurrent
    delivery of the exact same notification is a real, expected case here
    too -- select_for_update() locks the matching pending row for the
    duration of the state transition; a second concurrent/retried delivery
    finds no pending row once the first has flipped the status and takes
    the "no subscription found" (already-processed) path instead of
    activating twice. The SMS send is deliberately outside the transaction
    (external HTTP call; never hold a DB lock across one -- see
    api/views/direct_debit.py's activate/cancel mandate views for the same
    rule applied elsewhere in this codebase).
    """
    notify = telebirr_service.verify_notify(request.data)

    if not notify.get('verified'):
        logger.warning('[TELEBIRR ONE-TIME] Invalid signature; acknowledging receipt but NOT processing')
        return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'received (signature not verified)'})

    merch_order_id = notify.get('merch_order_id')
    trade_status = notify.get('trade_status')
    payment_order_id = notify.get('payment_order_id')

    if not merch_order_id:
        return Response({'error': 'Missing merch_order_id'}, status=status.HTTP_400_BAD_REQUEST)

    activated_subscription = None
    try:
        with transaction.atomic():
            subscription = UserSubscription.objects.select_for_update().filter(
                payment_reference=merch_order_id,
                status='pending'
            ).first()

            if not subscription:
                logger.info('[TELEBIRR ONE-TIME] No pending subscription for merch_order_id=%s (already processed or unknown)', merch_order_id)
                return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'no subscription found'})

            if trade_status in ('Completed', 'SUCCESS'):
                # New (previously-anonymous) user: create/link the account
                # now that payment is confirmed.
                if not subscription.user:
                    from api.views.core import _normalize_ethiopian_phone

                    phone_number = subscription.telebirr_phone_number
                    if not phone_number:
                        logger.error('[TELEBIRR ONE-TIME] Cannot create user: no phone number on subscription %s', subscription.id)
                        return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'payment received but user creation failed'})

                    normalized_phone = _normalize_ethiopian_phone(phone_number)
                    if normalized_phone:
                        phone_number = normalized_phone

                    username = f'telebirr_{phone_number}'
                    existing_user = User.objects.filter(username=username).first()
                    if existing_user:
                        subscription.user = existing_user
                    else:
                        new_user = User.objects.create_user(
                            username=username,
                            phone_number=phone_number,
                            password=None,
                        )
                        subscription.user = new_user

                subscription.status = 'active'
                subscription.payment_order_id = payment_order_id
                subscription.save()

                SubscriptionHistory.objects.create(
                    user=subscription.user,
                    subscription=subscription,
                    tier=subscription.tier,
                    action='activated',
                    reason='One-time Telebirr payment completed'
                )

                logger.info('[TELEBIRR ONE-TIME] Subscription %s activated', subscription.id)
                activated_subscription = subscription
            else:
                logger.warning('[TELEBIRR ONE-TIME] Payment failed: %s', trade_status)
                subscription.status = 'failed'
                subscription.save()

        # Best-effort SMS, outside the transaction -- non-fatal if it fails,
        # the subscription is already activated.
        if activated_subscription is not None:
            try:
                phone_number = activated_subscription.telebirr_phone_number
                if not phone_number and activated_subscription.user and hasattr(activated_subscription.user, 'profile'):
                    phone_number = activated_subscription.user.profile.phone_number

                if phone_number:
                    superapp_sms_service.send_subscription_success(
                        phone_number=phone_number,
                        plan_name=activated_subscription.tier.name,
                        amount=activated_subscription.tier.price_etb,
                        duration_type=activated_subscription.duration_type,
                        end_date=activated_subscription.end_date,
                    )
            except Exception as sms_err:
                logger.warning('[TELEBIRR ONE-TIME] Failed to send SMS: %s', sms_err)

        return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'success'})

    except Exception as e:
        logger.exception('[TELEBIRR ONE-TIME] Callback error: %s', e)
        # Telebirr retries on non-2xx; acknowledge so a transient local
        # error doesn't trigger a retry storm on top of one we can't yet
        # process -- matches master's own choice here.
        return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'error processed'})


@api_view(['GET'])
@permission_classes([AllowAny])
def telebirr_one_time_query(request):
    """
    Query subscription status by merch_order_id. Used by the frontend to
    poll payment status.

    AllowAny: new SuperApp users have no auth token until AFTER payment
    succeeds and the webhook creates their account. merch_order_id is a
    unique, unguessable-enough token generated by us, so an unauthenticated
    request looks it up by that alone; an authenticated request stays
    scoped to request.user for safety.
    """
    merch_order_id = request.GET.get('merch_order_id')

    if not merch_order_id:
        return Response({'error': 'merch_order_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        if request.user.is_authenticated:
            subscription = UserSubscription.objects.filter(
                user=request.user,
                payment_reference=merch_order_id
            ).first()
        else:
            subscription = UserSubscription.objects.filter(
                payment_reference=merch_order_id
            ).first()

        if not subscription:
            return Response({'error': 'Subscription not found'}, status=status.HTTP_404_NOT_FOUND)

        # Self-healing: the async webhook may have been delayed or dropped.
        # If still pending, actively ask Telebirr for the real order status
        # rather than waiting forever. Locked the same way the webhook is,
        # so a self-heal here and a delayed webhook arriving concurrently
        # can't both activate the same subscription.
        if subscription.status == 'pending':
            try:
                query_result = telebirr_service.query_order(merch_order_id)

                if query_result.get('success') and query_result.get('is_paid'):
                    with transaction.atomic():
                        locked = UserSubscription.objects.select_for_update().filter(
                            pk=subscription.pk, status='pending'
                        ).first()
                        if locked is not None:
                            locked.status = 'active'
                            locked.payment_order_id = query_result.get('payment_order_id')
                            locked.save()

                            SubscriptionHistory.objects.create(
                                user=locked.user,
                                subscription=locked,
                                tier=locked.tier,
                                action='activated',
                                reason='Self-healed via active queryOrder (webhook was delayed/missing)'
                            )
                            subscription = locked

                            try:
                                phone_number = subscription.telebirr_phone_number or (
                                    subscription.user.profile.phone_number
                                    if subscription.user and hasattr(subscription.user, 'profile') and subscription.user.profile
                                    else None
                                )
                                if phone_number:
                                    superapp_sms_service.send_subscription_success(
                                        phone_number=phone_number,
                                        plan_name=subscription.tier.name,
                                        amount=subscription.tier.price_etb,
                                        duration_type=subscription.duration_type,
                                        end_date=subscription.end_date,
                                    )
                            except Exception as sms_err:
                                logger.warning('[TELEBIRR ONE-TIME] Self-heal SMS failed (non-fatal): %s', sms_err)
                elif query_result.get('success') and query_result.get('order_status') in ('PAY_FAILED', 'CLOSED', 'CANCELLED'):
                    with transaction.atomic():
                        locked = UserSubscription.objects.select_for_update().filter(
                            pk=subscription.pk, status='pending'
                        ).first()
                        if locked is not None:
                            locked.status = 'failed'
                            locked.save()
                            subscription = locked
            except Exception as query_err:
                logger.warning('[TELEBIRR ONE-TIME] Active queryOrder check failed (non-fatal, leaving pending): %s', query_err)

        return Response({
            'status': subscription.status,
            'subscription_id': str(subscription.id),
            'end_date': subscription.end_date.isoformat() if subscription.end_date else None,
            'plan_type': subscription.duration_type,
        })

    except Exception as e:
        logger.exception('[TELEBIRR ONE-TIME] Query error: %s', e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def check_superapp_subscription(request):
    """
    Check if a phone number has an active SuperApp (Telebirr) subscription.
    Used for SuperApp users to log in to the web app.
    """
    from api.views.core import _normalize_ethiopian_phone

    phone = request.data.get('phone', '').strip()
    if not phone:
        return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)

    normalized_phone = _normalize_ethiopian_phone(phone)
    if not normalized_phone:
        return Response({'error': 'Invalid Ethiopian phone number'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        subscription = UserSubscription.objects.filter(
            telebirr_phone_number__in=[normalized_phone, phone],
            payment_method='telebirr',
            status='active',
            end_date__gt=timezone.now(),
        ).first()

        if not subscription:
            return Response({'has_active_subscription': False, 'user_exists': False}, status=status.HTTP_200_OK)

        tier_type = subscription.tier.duration_type if subscription.tier else None
        onevas_config = ONEVAS_PRODUCTS.get(tier_type, {})
        return Response({
            'has_active_subscription': True,
            'user_exists': subscription.user is not None,
            'subscription_id': str(subscription.id),
            'tier_name': subscription.tier.name if subscription.tier else None,
            'tier_type': tier_type,
            'end_date': subscription.end_date.isoformat() if subscription.end_date else None,
            'application_key': onevas_config.get('application_key'),
            'product_number': onevas_config.get('product_id'),
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error('[SUPERAPP LOGIN] Error checking subscription: %s', e)
        return Response({'error': 'Failed to check subscription status'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def validate_subscription_token(request):
    """
    Validate a subscription_token and return the phone number it belongs to.
    Lets the frontend recover a phone number from a secure, single-use token
    instead of having it appear directly in a URL.
    """
    token = request.data.get('token', '').strip()
    if not token:
        return Response({'error': 'Token is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        subscription = UserSubscription.objects.filter(subscription_token=token, status='active').first()
        if not subscription:
            return Response({'error': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)

        if subscription.subscription_token_expires_at and timezone.now() > subscription.subscription_token_expires_at:
            return Response({'error': 'Token has expired'}, status=status.HTTP_400_BAD_REQUEST)

        phone = subscription.telebirr_phone_number or subscription.onevas_phone_number
        return Response({
            'phone': phone,
            'existing_user': subscription.user is not None,
            'subscription_id': str(subscription.id),
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error('[SUBSCRIPTION TOKEN] Error validating token: %s', e)
        return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def telebirr_ussd_subscription_status(request):
    """
    Public status check for a USSD Push subscription payment, keyed by
    originator_conversation_id (a random ID only known to the browser that
    initiated the payment). Used by the frontend to poll payment/subscription
    activation for ANONYMOUS (phone-only) users, since the authenticated
    /subscriptions/ endpoint cannot be used before login.
    """
    originator_conversation_id = request.query_params.get('originator_conversation_id')
    if not originator_conversation_id:
        return Response({'error': 'originator_conversation_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    payment = SubscriptionPayment.objects.filter(
        onevas_transaction_id=originator_conversation_id, payment_method='telebirr',
    ).first()

    if not payment:
        return Response({'found': False, 'status': 'pending', 'subscription_status': None, 'is_new_user': None, 'phone_number': None})

    subscription_status = payment.subscription.status if payment.subscription else None
    is_new_user = payment.metadata.get('is_new_user') if payment.metadata else None
    phone_number = payment.metadata.get('phone_number') if payment.metadata else (
        payment.user.profile.phone_number if payment.user and hasattr(payment.user, 'profile') else None
    )

    return Response({
        'found': True,
        'status': payment.status,
        'subscription_status': subscription_status,
        'is_new_user': is_new_user,
        'phone_number': phone_number,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def telebirr_ussd_subscription_initiate(request):
    """
    Initiate a USSD Push payment for a subscription (BuyGoodsForCustomer).
    Creates a pending SubscriptionPlan + SubscriptionPayment; activation
    happens only in telebirr_ussd_subscription_webhook once Telebirr
    confirms the payment -- never here.
    """
    from api.views.core import _normalize_ethiopian_phone

    tier_id = request.data.get('tier_id')
    phone_number = request.data.get('phone_number')

    if not tier_id:
        return Response({'error': 'tier_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        tier = SubscriptionTier.objects.get(id=tier_id, is_active=True)
    except SubscriptionTier.DoesNotExist:
        return Response({'error': 'Tier not found or inactive'}, status=status.HTTP_404_NOT_FOUND)

    if not phone_number:
        if not request.user.is_authenticated:
            return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)
        profile = getattr(request.user, 'profile', None)
        phone_number = profile.phone_number if profile else None

    if not phone_number:
        return Response({'error': 'Phone number not found'}, status=status.HTTP_400_BAD_REQUEST)

    normalized_phone = _normalize_ethiopian_phone(phone_number)
    if normalized_phone:
        phone_number = normalized_phone

    amount = f'{float(tier.price_etb):.2f}'

    subscription_webhook_url = getattr(settings, 'TELEBIRR_SUBSCRIPTION_USSD_RESULT_URL', '')
    result = telebirr_direct_debit_service.initiate_ussd_push_payment(
        amount=amount, phone_number=phone_number, coins=0,
        result_url=subscription_webhook_url or None,
    )

    if not result.get('success'):
        return Response(
            {'error': result.get('error', 'USSD Push payment initiation failed'), 'details': result},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    start_date = timezone.now()
    end_date = start_date + timedelta(days=tier.duration_days or 30)
    user_for_subscription = request.user if request.user.is_authenticated else None

    subscription = UserSubscription.objects.create(
        user=user_for_subscription, tier=tier, status='pending', duration_type=tier.duration_type,
        start_date=start_date, end_date=end_date, payment_method='telebirr', auto_renew=False,
    )

    payment_metadata = {} if user_for_subscription else {'phone_number': phone_number}
    payment = SubscriptionPayment.objects.create(
        user=user_for_subscription, subscription=subscription, amount=tier.price_etb, currency='ETB',
        status='pending', payment_method='telebirr', onevas_transaction_id=result.get('originator_conversation_id'),
        duration_type=tier.duration_type, period_start=start_date, period_end=end_date, metadata=payment_metadata,
    )

    return Response({
        'success': True,
        'originator_conversation_id': result.get('originator_conversation_id'),
        'conversation_id': result.get('conversation_id'),
        'message': result.get('message'),
        'tier': {
            'id': str(tier.id), 'name': tier.name, 'slug': tier.slug,
            'price_etb': str(tier.price_etb), 'duration_days': tier.duration_days,
        },
        'payment_id': str(payment.id),
    })


def _activate_ussd_subscription_payment(payment, tier):
    """Activate the subscription linked to a USSD Push payment. Called only
    from inside telebirr_ussd_subscription_webhook's row lock on `payment`."""
    user = payment.user
    subscription = payment.subscription

    if subscription and subscription.status == 'pending':
        subscription.status = 'active'
        subscription.tier = tier
        subscription.duration_type = tier.duration_type
        subscription.payment_method = 'telebirr'
        if not subscription.user:
            subscription.user = user
        subscription.save()
    else:
        existing = UserSubscription.objects.filter(user=user, status='active').first()
        if existing:
            now = timezone.now()
            existing.start_date = now
            if tier.duration_days:
                existing.end_date = now + timedelta(days=tier.duration_days)
            existing.tier = tier
            existing.duration_type = tier.duration_type
            existing.payment_method = 'telebirr'
            existing.save()
            subscription = existing
        else:
            now = timezone.now()
            end_date = now + timedelta(days=tier.duration_days) if tier.duration_days else None
            subscription = UserSubscription.objects.create(
                user=user, tier=tier, status='active', duration_type=tier.duration_type,
                start_date=now, end_date=end_date, payment_method='telebirr', auto_renew=False,
            )

    payment.subscription = subscription
    payment.status = 'completed'
    payment.save()

    SubscriptionHistory.objects.create(
        user=user, subscription=subscription, tier=tier, action='created',
        reason=f'USSD Push payment: {tier.name} subscription',
    )
    return subscription


@api_view(['POST'])
@permission_classes([AllowAny])  # Telebirr calls this webhook
def telebirr_ussd_subscription_webhook(request):
    """
    Handle the USSD Push payment result webhook from Telebirr for
    subscriptions -- a SOAP Result envelope with payment completion status.

    Locked for the rest of this request: Telebirr callbacks are documented
    to retry and this endpoint has no signature verification, so a duplicate
    or genuinely concurrent delivery of the same callback is a real, expected
    case. select_for_update() plus the status == 'pending' check is what
    stops a retry from double-activating a subscription or double-creating
    a user for the same payment.
    """
    from defusedxml import ElementTree as ET

    raw_body = request.body or b''
    logger.info('[USSD SUBSCRIPTION WEBHOOK] Received callback, len=%d', len(raw_body))

    try:
        root = ET.fromstring(raw_body)
        namespaces = {
            'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
            'api': 'http://cps.huawei.com/cpsinterface/api_resultmgr',
            'res': 'http://cps.huawei.com/cpsinterface/result',
        }

        header = root.find('.//res:Header', namespaces)
        originator_conversation_id = header.find('res:OriginatorConversationID', namespaces).text if header is not None else None

        body_el = root.find('.//res:Body', namespaces)
        result_type = body_el.find('res:ResultType', namespaces).text if body_el is not None else None
        result_code = body_el.find('res:ResultCode', namespaces).text if body_el is not None else None

        transaction_id = None
        transaction_result = body_el.find('res:TransactionResult', namespaces) if body_el is not None else None
        if transaction_result is not None:
            transaction_id_elem = transaction_result.find('res:TransactionID', namespaces)
            if transaction_id_elem is not None:
                transaction_id = transaction_id_elem.text

        logger.info(
            '[USSD SUBSCRIPTION WEBHOOK] originator=%s result_code=%s result_type=%s transaction_id=%s',
            originator_conversation_id, result_code, result_type, transaction_id,
        )

        if not originator_conversation_id:
            return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'no originator_conversation_id'})

        is_success = result_code == '0' and result_type == '0'
        activated_user = None

        with transaction.atomic():
            payment = SubscriptionPayment.objects.select_for_update().filter(
                onevas_transaction_id=originator_conversation_id, payment_method='telebirr', status='pending',
            ).first()

            if not payment:
                logger.info('[USSD SUBSCRIPTION WEBHOOK] No pending payment for %s (already processed or unknown)', originator_conversation_id)
                return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'no pending payment found'})

            if not is_success:
                payment.status = 'failed'
                payment.save()
                return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'received'})

            user = payment.user

            if not user and payment.metadata and payment.metadata.get('phone_number'):
                from api.views.core import _normalize_ethiopian_phone

                phone_number = payment.metadata.get('phone_number')
                normalized_phone = _normalize_ethiopian_phone(phone_number) or phone_number

                profile = UserProfile.objects.filter(phone_number=normalized_phone).first()
                if profile:
                    user = profile.user
                    payment.user = user
                    payment.metadata['is_new_user'] = False
                else:
                    username = f'user_{normalized_phone[-8:]}'
                    user = User.objects.create_user(username=username, password=None)
                    UserProfile.objects.filter(user=user).update(phone_number=normalized_phone)
                    payment.user = user
                    payment.metadata['is_new_user'] = True
                payment.save()
            elif user:
                payment.metadata['is_new_user'] = False
                payment.save()

            if not user:
                payment.status = 'failed'
                payment.save()
                return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'no user found'})

            tier = SubscriptionTier.objects.filter(is_active=True).filter(price_etb=payment.amount).first()
            if not tier:
                payment.status = 'failed'
                payment.save()
                return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'tier not found'})

            _activate_ussd_subscription_payment(payment, tier)
            activated_user = user

        # SMS/OTP dispatch is a real outbound HTTP call, so it runs outside
        # the lock above -- see the module-level docstring precedent in
        # api/views/direct_debit.py for why.
        if activated_user is not None:
            try:
                phone_number = getattr(getattr(activated_user, 'profile', None), 'phone_number', None)
                if phone_number:
                    from api.services.otp import OTPService

                    OTPService.send_otp(
                        phone_number, settings.ONEVAS_APPLICATION_KEY, settings.ONEVAS_PRODUCT_NUMBER,
                        action='subscription_login',
                    )
            except Exception as otp_error:
                logger.error('[USSD SUBSCRIPTION WEBHOOK] Error sending login OTP: %s', otp_error)

        return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'subscription activated'})

    except Exception as e:
        logger.exception('[USSD SUBSCRIPTION WEBHOOK] Error processing webhook: %s', e)
        return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'error processed'})
