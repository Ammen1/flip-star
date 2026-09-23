import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.integrations.telebirr.checkout import telebirr_service
from api.integrations.telebirr.direct_debit import telebirr_direct_debit_service
from api.models import UserProfile
from api.models.payment_verification import PaymentVerificationSession
from api.models.subscription import (
    SubscriptionCoinTransaction as CoinTransaction,
)
from api.models.subscription import (
    SubscriptionHistory,
    SubscriptionPayment,
    SubscriptionTier,
    TrialPopupLog,
)
from api.models.subscription import (
    SubscriptionPlan as UserSubscription,
)
from api.services import payment_otp, payment_status
from api.services.payment_otp import OtpVerificationFailed
from api.services.subscription_access import (
    active_subscription_for,
    already_subscribed_payload,
    payment_pending_payload,
    pending_subscription_payment,
)
from api.services.superapp_sms_service import superapp_sms_service
from api.services.telebirr_subscription_sms import SUPERAPP as TELEBIRR_SMS_SUPERAPP
from api.services.telebirr_subscription_sms import USSD as TELEBIRR_SMS_USSD
from api.services.telebirr_subscription_sms import (
    notify_activated as notify_telebirr_subscription_activated,
)
from common.security import EncryptedPayloadMixin, encrypted_endpoint
from common.throttling import PhoneLookupAnonThrottle, PhoneLookupUserThrottle

logger = logging.getLogger(__name__)


# OneVAS has been removed. Its webhook view (/onevas/subscription|
# unsubscription|renewal|stop) and its settings lived here; TIMWE's datasync
# endpoint, api/views/timwe.py, is the subscription channel now. Subscriptions
# OneVAS created are still ordinary SubscriptionPlan rows and keep working.

# App Links (placeholders - update with actual URLs)
# WEB_APP_LINK = "https://api.uat.flipstar.et?subscription_tp=true"
WEB_APP_LINK = 'https://uat.flipstar.et/register?subscription_tp=true&phone={masked_phone}'
MOBILE_APP_LINK = 'https://play.google.com/store/apps/details?id=com.postworq.mobile'


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
            from api.models import Subscription

            print(
                f'[SUBSCRIPTION STATUS] Checking subscription for user: {request.user.username} (ID: {request.user.id})'
            )

            # Use the shared predicate so the status API and subscriber-only
            # endpoints cannot disagree about an active plan.
            active_subscription = active_subscription_for(user=request.user)

            print(
                f'[SUBSCRIPTION STATUS] UserSubscription active found: {active_subscription is not None}'
            )
            if active_subscription:
                print(
                    f'[SUBSCRIPTION STATUS] UserSubscription: ID={active_subscription.id}, status={active_subscription.status}, end_date={active_subscription.end_date}'
                )

            if active_subscription:
                return Response(
                    {
                        'has_subscription': True,
                        'status': 'ACTIVE',
                        'subscription': {
                            'id': str(active_subscription.id),
                            'tier': {
                                'id': str(active_subscription.tier.id)
                                if active_subscription.tier
                                else None,
                                'name': active_subscription.tier.name
                                if active_subscription.tier
                                else None,
                                'duration_type': active_subscription.tier.duration_type
                                if active_subscription.tier
                                else None,
                                'price_etb': float(active_subscription.tier.price_etb)
                                if active_subscription.tier
                                else 0,
                                # The one coin reward the backend still grants on a
                                # daily cadence: every completed charge on this tier
                                # credits this many coins automatically (see
                                # api/services/subscription_gift.py). The profile's
                                # Daily Streak feature reads it to tell the customer
                                # what their plan actually pays them per charge.
                                'charge_gift_coins': (
                                    active_subscription.tier.charge_gift_coins
                                    if active_subscription.tier
                                    else 0
                                ),
                            },
                            'status': active_subscription.status,
                            # A null start_date on an otherwise active plan made
                            # this line raise, and the whole endpoint 500.
                            'start_date': active_subscription.start_date.isoformat()
                            if active_subscription.start_date
                            else None,
                            'end_date': active_subscription.end_date.isoformat()
                            if active_subscription.end_date
                            else None,
                            'auto_renew': active_subscription.auto_renew,
                        },
                    }
                )

            # Fallback to old Subscription model
            old_subscription = Subscription.objects.filter(
                user=request.user, expires_at__gt=timezone.now()
            ).first()

            print(
                f'[SUBSCRIPTION STATUS] Old Subscription active found: {old_subscription is not None}'
            )
            if old_subscription:
                print(
                    f'[SUBSCRIPTION STATUS] Old Subscription: ID={old_subscription.id}, plan={old_subscription.plan}, expires_at={old_subscription.expires_at}'
                )

            if old_subscription:
                return Response(
                    {
                        'has_subscription': True,
                        'status': 'ACTIVE',
                        'subscription': {
                            'id': str(old_subscription.id),
                            'tier': {
                                'id': None,
                                'name': old_subscription.plan,
                                'duration_type': None,
                                'price_etb': 0,
                                'charge_gift_coins': 0,
                            },
                            'status': 'active',
                            'start_date': old_subscription.started_at.isoformat()
                            if old_subscription.started_at
                            else None,
                            'end_date': old_subscription.expires_at.isoformat()
                            if old_subscription.expires_at
                            else None,
                            'auto_renew': False,
                        },
                    }
                )

            # No active subscription found - check for any subscriptions
            any_subscription = UserSubscription.objects.filter(user=request.user)
            any_old_subscription = Subscription.objects.filter(user=request.user)

            print(f'[SUBSCRIPTION STATUS] Any UserSubscription count: {any_subscription.count()}')
            print(
                f'[SUBSCRIPTION STATUS] Any old Subscription count: {any_old_subscription.count()}'
            )

            if any_subscription.exists():
                for sub in any_subscription:
                    print(
                        f'[SUBSCRIPTION STATUS] UserSubscription: status={sub.status}, end_date={sub.end_date}'
                    )

            if any_old_subscription.exists():
                for sub in any_old_subscription:
                    print(
                        f'[SUBSCRIPTION STATUS] Old Subscription: plan={sub.plan}, expires_at={sub.expires_at}'
                    )

            body = {
                'has_subscription': False,
                'subscription': None,
                'has_had_subscription': any_subscription.exists() or any_old_subscription.exists(),
                'message': 'No active subscription found',
            }
            body.update(self._renewal_state(request.user))
            return Response(body, status=status.HTTP_200_OK)

        except Exception as e:
            print(f'[SUBSCRIPTION STATUS] Error: {e}')
            import traceback

            traceback.print_exc()
            return Response(
                {'error': str(e), 'has_subscription': False},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @staticmethod
    def _renewal_state(user):
        """What a subscriber with no active plan is waiting on. Never charges here.

        A lapsed short-code subscription whose renewal is due is queued, not
        charged inline: this endpoint is polled every 30 seconds and must not
        wait up to a minute on TIMWE. A renewal in flight or unconfirmed reads
        PAYMENT_PENDING -- never "no subscription", which would invite the
        subscriber to pay again. Any failure in here leaves the answer the
        endpoint always gave rather than turning it into a 500.
        """
        from api.services import subscription_renewal as renewal

        try:
            state = renewal.subscription_status(user)
            if state.state == renewal.EXPIRED and state.reason == renewal.REASON_DUE:
                if renewal.schedule_renewal(user, state.plan):
                    return {'status': 'PAYMENT_PENDING', 'renewal': {'state': 'scheduled'}}
                return {'status': 'EXPIRED', 'renewal': {'state': renewal.REASON_DUE}}
            if state.state == renewal.PAYMENT_PENDING:
                return {'status': 'PAYMENT_PENDING', 'renewal': {'state': state.reason}}
            if state.state == renewal.EXPIRED:
                return {'status': 'EXPIRED', 'renewal': {'state': state.reason}}
        except Exception:
            logger.exception('Subscription renewal state could not be read')
            return {'status': 'UNKNOWN'}
        return {'status': 'INACTIVE'}


class SubscriptionTierViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    """Manage subscription tiers"""

    # Split by action rather than a single permission_classes, because this is
    # a ModelViewSet and the two halves need opposite answers.
    #
    # Reads are the public price list. A visitor has to see what the plans cost
    # before signing up, so requiring a login to fetch them made the signup
    # flow impossible -- the client had no tier_id to send to
    # /subscription/telebirr/ussd/initiate/, which answered "tier_id is
    # required".
    #
    # Writes are the opposite. `IsAuthenticated` alone let ANY logged-in user
    # create, reprice or delete a subscription tier through the inherited
    # ModelViewSet routes. That was a live hole independent of this change;
    # IsAdminUser closes it. Do not collapse these back into one
    # permission_classes -- AllowAny here would publish the write routes too.
    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'active'):
            return [AllowAny()]
        return [IsAdminUser()]

    queryset = SubscriptionTier.objects.filter(is_active=True)
    serializer_class = None  # Add serializer later

    def get_queryset(self):
        return super().get_queryset().order_by('sort_order', 'price_etb')

    def list(self, request):
        """Get all active tiers.

        On-demand is left out for anyone who does not have an account yet. It
        is a pay-per-use top-up on an account that already exists -- it has no
        duration and grants nothing on its own -- so offering it as somebody's
        first subscription gives them a charge and no service. A first-time
        subscriber picks daily, weekly or monthly; the request that reaches us
        for them carries no user.

        Here rather than in each client, so the web app, the SuperApp and
        anything added later get the same answer to "what may I buy".
        """
        tiers = self.get_queryset()
        if not request.user.is_authenticated:
            tiers = tiers.exclude(duration_type='ondemand')
        data = [
            {
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
            }
            for tier in tiers
        ]
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
            if (
                profile.is_trial_user
                and profile.trial_end_date
                and profile.trial_end_date > timezone.now()
            ):
                return Response(
                    {
                        'status': 'trial',
                        'trial_end_date': profile.trial_end_date.isoformat(),
                        'days_remaining': (profile.trial_end_date - timezone.now()).days,
                    }
                )
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
            'next_renewal_date': subscription.next_renewal_date.isoformat()
            if subscription.next_renewal_date
            else None,
            'auto_renew': subscription.auto_renew,
        }
        return Response(data)

    @action(detail=False, methods=['post'])
    def subscribe(self, request):
        """Initiate subscription request"""
        tier_id = request.data.get('tier_id')
        # telebirr or coins. OneVAS airtime was a third option; it has been
        # removed, so 'onevas' -- once the default -- is now an invalid method.
        payment_method = request.data.get('payment_method')

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

        if payment_method == 'coins':
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
                        reference_type='subscription',
                    )

                    profile.is_trial_user = False
                    profile.save(update_fields=['is_trial_user'])

                    # Create subscription
                    subscription = UserSubscription.objects.create(
                        user=user, tier=tier, duration_type=tier.duration_type, status='pending'
                    )
                    subscription.activate()

                    # Record history
                    SubscriptionHistory.objects.create(
                        user=user,
                        subscription=subscription,
                        tier=tier,
                        action='created',
                        reason='Purchased with coins',
                        metadata={'payment_method': 'coins', 'amount': tier.price_coins},
                    )

                    # Create payment record
                    SubscriptionPayment.objects.create(
                        subscription=subscription,
                        user=user,
                        amount=tier.price_etb,
                        payment_method='coins',
                        duration_type=tier.duration_type,
                        period_start=subscription.start_date,
                        period_end=subscription.end_date
                        or timezone.now() + timedelta(days=tier.duration_days or 30),
                        status='completed',
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

    def initiate_telebirr_payment(self, user, tier):
        """Initiate Telebirr payment for subscription"""
        profile = user.profile

        try:
            response = telebirr_service.initiate_payment(
                amount=float(tier.price_etb),
                phone_number=profile.phone_number,
                user_id=user.id,
                package_id=tier.id,
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

                return Response(
                    {
                        'status': 'pending',
                        'message': 'Payment initiated. Please complete payment via Telebirr.',
                        'payment_url': response.get('payment_url'),
                        'transaction_id': response.get('transaction_id'),
                        'payment_id': str(payment.id),
                    }
                )
            else:
                return Response(
                    {'error': response.get('error', 'Payment initiation failed')}, status=400
                )

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
            reason=reason,
        )

        return Response({'status': 'success', 'message': 'Subscription cancelled'})

    @action(detail=False, methods=['get'])
    def history(self, request):
        """Get subscription history"""
        history = SubscriptionHistory.objects.filter(user=request.user).order_by('-created_at')

        data = [
            {
                'action': item.action,
                'tier_name': item.tier.name if item.tier else None,
                'reason': item.reason,
                'created_at': item.created_at.isoformat(),
            }
            for item in history
        ]

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
            user_action=user_action,
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

        data = [
            {
                'id': str(t.id),
                'transaction_type': t.transaction_type,
                'amount': t.amount,
                'balance_after': t.balance_after,
                'description': t.description,
                'created_at': t.created_at.isoformat(),
            }
            for t in transactions
        ]

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
                    description=f'Purchase {coins} coins',
                )

                if response.get('success'):
                    return Response(
                        {
                            'status': 'pending',
                            'message': f'Purchasing {coins} coins via Telebirr',
                            'payment_url': response.get('payment_url'),
                            'coins': coins,
                        }
                    )
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
        active_by_tier = (
            UserSubscription.objects.filter(status='active', **sub_filter)
            .values('tier__name')
            .annotate(count=Count('id'), total_revenue=Sum('tier__price_etb'))
            .order_by('-total_revenue')
        )

        # Today's revenue
        today_payments = SubscriptionPayment.objects.filter(
            status='completed',
            period_start__date=today,
            **pay_filter,
        ).aggregate(total=Sum('amount'), count=Count('id'))

        # This week's revenue
        week_payments = SubscriptionPayment.objects.filter(
            status='completed',
            period_start__date__gte=week_ago,
            **pay_filter,
        ).aggregate(total=Sum('amount'), count=Count('id'))

        # This month's revenue
        month_payments = SubscriptionPayment.objects.filter(
            status='completed',
            period_start__date__gte=month_ago,
            **pay_filter,
        ).aggregate(total=Sum('amount'), count=Count('id'))

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
            status='completed',
            **pay_filter,
        ).order_by('-created_at')[:20]

        recent_data = []
        for tx in recent_transactions:
            sub = tx.subscription
            tier = sub.tier if sub else None
            user_obj = (
                (sub.user if sub and sub.user else tx.user)
                if hasattr(tx, 'user')
                else (sub.user if sub else None)
            )
            phone = ''
            if sub and getattr(sub, 'onevas_phone_number', None):
                phone = sub.onevas_phone_number
            elif (
                user_obj
                and hasattr(user_obj, 'profile')
                and getattr(user_obj.profile, 'phone_number', None)
            ):
                phone = user_obj.profile.phone_number

            recent_data.append(
                {
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
                    'period_start': tx.period_start.strftime('%Y-%m-%d %H:%M')
                    if tx.period_start
                    else '',
                    'period_end': tx.period_end.strftime('%Y-%m-%d %H:%M') if tx.period_end else '',
                    'date': tx.created_at.strftime('%Y-%m-%d %H:%M')
                    if tx.created_at
                    else (tx.period_start.strftime('%Y-%m-%d %H:%M') if tx.period_start else 'N/A'),
                    'status': tx.status,
                }
            )

        return Response(
            {
                'active_subscriptions': {
                    'total': active_subs.count(),
                    'by_tier': list(active_by_tier),
                    'mrr': float(mrr),
                },
                'revenue': {
                    'today': {
                        'total': float(today_payments['total'] or 0),
                        'count': today_payments['count'] or 0,
                    },
                    'week': {
                        'total': float(week_payments['total'] or 0),
                        'count': week_payments['count'] or 0,
                    },
                    'month': {
                        'total': float(month_payments['total'] or 0),
                        'count': month_payments['count'] or 0,
                    },
                },
                'cancellations': {'month_count': month_cancellations},
                'recent_transactions': recent_data,
            }
        )

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


@api_view(['POST'])
@permission_classes([AllowAny])
@encrypted_endpoint
def telebirr_one_time_initiate(request):
    """
    Initiate a one-time Telebirr H5/SuperApp payment for a subscription plan.

    Only recurring plans (daily, weekly, monthly) are accepted here.
    On-demand is a coin top-up product, not a subscription, and must NOT be
    offered through this endpoint -- it has no duration_days, grants nothing
    on its own, and would leave a subscriber charged with no service.

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

    # On-demand is a coin top-up, not a recurring subscription. It has no
    # duration and cannot be activated through this H5/SuperApp flow.
    if plan_type == 'ondemand':
        return Response(
            {'error': 'On-demand purchases are not available through this endpoint.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Only allow the three recurring plan types.
    ALLOWED_PLAN_TYPES = ('daily', 'weekly', 'monthly')
    if plan_type not in ALLOWED_PLAN_TYPES:
        return Response(
            {
                'error': f'Invalid plan_type {plan_type!r}. Must be one of: '
                + ', '.join(ALLOWED_PLAN_TYPES)
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    tier = SubscriptionTier.objects.filter(duration_type=plan_type, is_active=True).first()
    if not tier:
        return Response(
            {'error': f'No active subscription tier found for plan type: {plan_type}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not request.user.is_authenticated and not phone_number:
        return Response(
            {'error': 'phone_number is required for unauthenticated users'},
            status=status.HTTP_400_BAD_REQUEST,
        )

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
            return Response(
                {'error': 'Failed to create Telebirr order', 'details': result.get('error')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

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
                user=request.user, status='active', end_date__gt=timezone.now()
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
                    user=existing_profile.user, status='active', end_date__gt=timezone.now()
                ).first()

        if existing_active:
            return Response(
                {
                    'error': 'You already have an active subscription. Please cancel it first or wait for it to expire.',
                    'existing_subscription': {
                        'id': existing_active.id,
                        'tier': existing_active.tier.name,
                        'end_date': existing_active.end_date.isoformat()
                        if existing_active.end_date
                        else None,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # For unauthenticated users, user is None; the webhook links/creates
        # the account once payment is confirmed.
        subscription = UserSubscription.objects.create(
            user=request.user if request.user.is_authenticated else None,
            tier=tier,
            payment_method='telebirr',
            duration_type=plan_type,
            status='pending',
            payment_reference=merch_order_id,
            telebirr_phone_number=phone_number
            if not request.user.is_authenticated
            else (
                request.user.profile.phone_number
                if hasattr(request.user, 'profile') and request.user.profile
                else None
            ),
            auto_renew=False,
            start_date=now,
            end_date=end_date,
        )

        logger.info(
            '[TELEBIRR ONE-TIME] Created pending subscription %s (merch_order_id=%s)',
            subscription.id,
            merch_order_id,
        )

        return Response(
            {
                'success': True,
                'raw_request': raw_request,
                'merch_order_id': merch_order_id,
                'prepay_id': prepay_id,
                'plan_type': plan_type,
            }
        )

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
        logger.warning(
            '[TELEBIRR ONE-TIME] Invalid signature; acknowledging receipt but NOT processing'
        )
        return Response(
            {'result': 'SUCCESS', 'code': '0', 'msg': 'received (signature not verified)'}
        )

    merch_order_id = notify.get('merch_order_id')
    trade_status = notify.get('trade_status')
    payment_order_id = notify.get('payment_order_id')

    if not merch_order_id:
        return Response({'error': 'Missing merch_order_id'}, status=status.HTTP_400_BAD_REQUEST)

    activated_subscription = None
    try:
        with transaction.atomic():
            subscription = (
                UserSubscription.objects.select_for_update()
                .filter(payment_reference=merch_order_id, status='pending')
                .first()
            )

            if not subscription:
                logger.info(
                    '[TELEBIRR ONE-TIME] No pending subscription for merch_order_id=%s (already processed or unknown)',
                    merch_order_id,
                )
                return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'no subscription found'})

            if trade_status in ('Completed', 'SUCCESS'):
                if not subscription.user:
                    from api.views.core import _normalize_ethiopian_phone

                    phone_number = subscription.telebirr_phone_number
                    if not phone_number:
                        logger.error(
                            '[TELEBIRR ONE-TIME] Cannot create user: no phone number on subscription %s',
                            subscription.id,
                        )
                        return Response(
                            {
                                'result': 'SUCCESS',
                                'code': '0',
                                'msg': 'payment received but user creation failed',
                            }
                        )

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

                subscription.payment_order_id = payment_order_id
                subscription.save()

                # Activate the subscription and grant the tier's bonus coins immediately.
                # activate() handles idempotency: it grants bonus_coins only once per period.
                subscription.activate()

                # Create a completed SubscriptionPayment to trigger the charge_gift_coins
                # grant via the post_save signal on SubscriptionPayment.
                SubscriptionPayment.objects.create(
                    user=subscription.user,
                    subscription=subscription,
                    amount=subscription.tier.price_etb,
                    currency='ETB',
                    status='completed',
                    payment_method='telebirr',
                    onevas_transaction_id=payment_order_id or merch_order_id,
                    duration_type=subscription.duration_type,
                    period_start=subscription.start_date,
                    period_end=subscription.end_date,
                    metadata={
                        'merch_order_id': merch_order_id,
                        'trade_status': trade_status,
                    },
                )

                SubscriptionHistory.objects.create(
                    user=subscription.user,
                    subscription=subscription,
                    tier=subscription.tier,
                    action='activated',
                    reason='One-time Telebirr payment completed',
                )

                logger.info(
                    '[TELEBIRR ONE-TIME] Subscription %s activated with coin grants',
                    subscription.id,
                )
                activated_subscription = subscription
            else:
                # The other direction of the same bug. This marked the
                # subscription `failed` for *anything* that was not
                # Completed -- a notify meaning "still waiting" included --
                # and activation only ever looks at rows still `pending`. So a
                # payment that then succeeded could never be applied: money
                # taken, nothing granted, and the customer told it failed.
                notified_state, notified_reason = payment_status.from_h5_order(
                    trade_status=trade_status
                )
                if payment_status.is_terminal(notified_state):
                    logger.warning(
                        '[TELEBIRR ONE-TIME] Payment %s (%s): %s',
                        notified_state,
                        notified_reason or 'unclassified',
                        trade_status,
                    )
                    subscription.status = 'failed'
                    subscription.save()
                else:
                    logger.info(
                        '[TELEBIRR ONE-TIME] Payment still in flight (%s); left pending',
                        trade_status,
                    )

        # Best-effort SMS, outside the transaction -- non-fatal if it fails,
        # the subscription is already activated.
        if activated_subscription is not None:
            try:
                phone_number = activated_subscription.telebirr_phone_number
                if (
                    not phone_number
                    and activated_subscription.user
                    and hasattr(activated_subscription.user, 'profile')
                ):
                    phone_number = activated_subscription.user.profile.phone_number

                if phone_number:
                    superapp_sms_service.send_subscription_success(
                        phone_number=phone_number,
                        plan_name=activated_subscription.tier.name,
                        amount=activated_subscription.tier.price_etb,
                        duration_type=activated_subscription.duration_type,
                        end_date=activated_subscription.end_date,
                        # Telebirr redelivers until acknowledged; without this
                        # every delivery queued another SMS.
                        idempotency_key=(
                            f'telebirr-sub-active:{TELEBIRR_SMS_SUPERAPP}:'
                            f'{activated_subscription.pk}'
                        ),
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


#: A subscription's status, as a payment state. The two vocabularies are not
#: the same thing -- 'expired' is a subscription that was paid for and has run
#: out, which is a *successful* payment -- so the mapping is written down
#: rather than inferred from the name.
SUBSCRIPTION_STATES = {
    'active': payment_status.SUCCESS,
    'expired': payment_status.SUCCESS,
    'grace_period': payment_status.SUCCESS,
    'pending': payment_status.PENDING,
    'failed': payment_status.FAILED,
    'cancelled': payment_status.CANCELLED,
}


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
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
                user=request.user, payment_reference=merch_order_id
            ).first()
        else:
            subscription = UserSubscription.objects.filter(payment_reference=merch_order_id).first()

        if not subscription:
            return Response({'error': 'Subscription not found'}, status=status.HTTP_404_NOT_FOUND)

        failure_reason = None
        if subscription.status == 'pending':
            try:
                query_result = telebirr_service.query_order(merch_order_id)

                if query_result.get('success') and query_result.get('is_paid'):
                    with transaction.atomic():
                        locked = (
                            UserSubscription.objects.select_for_update()
                            .filter(pk=subscription.pk, status='pending')
                            .first()
                        )
                        if locked is not None:
                            locked.status = 'active'
                            locked.payment_order_id = query_result.get('payment_order_id')
                            locked.save()

                            SubscriptionHistory.objects.create(
                                user=locked.user,
                                subscription=locked,
                                tier=locked.tier,
                                action='activated',
                                reason='Self-healed via active queryOrder (webhook was delayed/missing)',
                            )
                            subscription = locked

                            try:
                                phone_number = subscription.telebirr_phone_number or (
                                    subscription.user.profile.phone_number
                                    if subscription.user
                                    and hasattr(subscription.user, 'profile')
                                    and subscription.user.profile
                                    else None
                                )
                                if phone_number:
                                    superapp_sms_service.send_subscription_success(
                                        phone_number=phone_number,
                                        plan_name=subscription.tier.name,
                                        amount=subscription.tier.price_etb,
                                        duration_type=subscription.duration_type,
                                        end_date=subscription.end_date,
                                        # Same key as the callback path: the
                                        # self-heal and the webhook describe
                                        # one activation, so whichever runs
                                        # second finds the message already
                                        # queued instead of sending another.
                                        idempotency_key=(
                                            f'telebirr-sub-active:{TELEBIRR_SMS_SUPERAPP}:'
                                            f'{subscription.pk}'
                                        ),
                                    )
                            except Exception as sms_err:
                                logger.warning(
                                    '[TELEBIRR ONE-TIME] Self-heal SMS failed (non-fatal): %s',
                                    sms_err,
                                )
                elif query_result.get('success'):
                    # The same mapping the coin flows use, so "failed" means
                    # the same thing on both -- and an order_status this code
                    # has not seen stays pending rather than being called a
                    # failure it may not be.
                    queried_state, queried_reason = payment_status.from_h5_order(
                        order_status=query_result.get('order_status'),
                        trade_status=query_result.get('trade_status'),
                    )
                    if payment_status.is_terminal(queried_state):
                        with transaction.atomic():
                            locked = (
                                UserSubscription.objects.select_for_update()
                                .filter(pk=subscription.pk, status='pending')
                                .first()
                            )
                            if locked is not None:
                                locked.status = 'failed'
                                locked.save()
                                subscription = locked
                                failure_reason = queried_reason
            except Exception as query_err:
                logger.warning(
                    '[TELEBIRR ONE-TIME] Active queryOrder check failed (non-fatal, leaving pending): %s',
                    query_err,
                )

        # `status` stays for the clients already reading it; `state` is the
        # one vocabulary every payment flow answers in, and is what decides
        # whether a success screen may be shown.
        state = SUBSCRIPTION_STATES.get(subscription.status, payment_status.PENDING)
        return Response(
            payment_status.payload(
                state,
                failure_reason if state != payment_status.SUCCESS else None,
                status=subscription.status,
                subscription_id=str(subscription.id),
                end_date=subscription.end_date.isoformat() if subscription.end_date else None,
                plan_type=subscription.duration_type,
            )
        )

    except Exception as e:
        logger.exception('[TELEBIRR ONE-TIME] Query error: %s', e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PhoneLookupAnonThrottle, PhoneLookupUserThrottle])
def check_superapp_subscription(request):
    """
    Check if a phone number has an active SuperApp (Telebirr) subscription.
    Used for SuperApp users to log in to the web app.

    Unauthenticated by necessity -- the caller is deciding whether to show a
    login prompt and has no token yet. That makes it an oracle for "does this
    number subscribe", so it carries the phone_lookup throttle rather than
    accepting unlimited attempts.

    It deliberately returns NO OneVAS credentials. It used to include
    application_key and product_number so the browser could pass them to
    send-login-otp; that endpoint now resolves them from the tier itself.
    """
    from api.views.core import _normalize_ethiopian_phone

    phone = request.data.get('phone', '').strip()
    if not phone:
        return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)

    normalized_phone = _normalize_ethiopian_phone(phone)
    if not normalized_phone:
        return Response(
            {'error': 'Invalid Ethiopian phone number'}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        subscription = active_subscription_for(phone_number=phone, payment_method='telebirr')

        if not subscription:
            return Response(
                {'has_active_subscription': False, 'user_exists': False}, status=status.HTTP_200_OK
            )

        tier_type = subscription.tier.duration_type if subscription.tier else None
        return Response(
            {
                'has_active_subscription': True,
                'user_exists': subscription.user is not None,
                'subscription_id': str(subscription.id),
                'tier_name': subscription.tier.name if subscription.tier else None,
                'tier_type': tier_type,
                'end_date': subscription.end_date.isoformat() if subscription.end_date else None,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error('[SUPERAPP LOGIN] Error checking subscription: %s', e)
        return Response(
            {'error': 'Failed to check subscription status'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@permission_classes([AllowAny])
@encrypted_endpoint
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
        subscription = UserSubscription.objects.filter(
            subscription_token=token, status='active'
        ).first()
        if not subscription:
            return Response(
                {'error': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST
            )

        if (
            subscription.subscription_token_expires_at
            and timezone.now() > subscription.subscription_token_expires_at
        ):
            return Response({'error': 'Token has expired'}, status=status.HTTP_400_BAD_REQUEST)

        phone = subscription.telebirr_phone_number or subscription.onevas_phone_number
        return Response(
            {
                'phone': phone,
                'existing_user': subscription.user is not None,
                'subscription_id': str(subscription.id),
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error('[SUBSCRIPTION TOKEN] Error validating token: %s', e)
        return Response(
            {'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
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
        return Response(
            {'error': 'originator_conversation_id is required'}, status=status.HTTP_400_BAD_REQUEST
        )

    payment = SubscriptionPayment.objects.filter(
        onevas_transaction_id=originator_conversation_id,
        payment_method='telebirr',
    ).first()

    if not payment:
        return Response(
            {
                'found': False,
                'status': 'pending',
                'subscription_status': None,
                'is_new_user': None,
                'phone_number': None,
            }
        )

    subscription_status = payment.subscription.status if payment.subscription else None
    is_new_user = payment.metadata.get('is_new_user') if payment.metadata else None
    phone_number = (
        payment.metadata.get('phone_number')
        if payment.metadata
        else (
            payment.user.profile.phone_number
            if payment.user and hasattr(payment.user, 'profile')
            else None
        )
    )

    return Response(
        {
            'found': True,
            'status': payment.status,
            'subscription_status': subscription_status,
            'is_new_user': is_new_user,
            'phone_number': phone_number,
        }
    )


@api_view(['POST'])
@permission_classes([AllowAny])
# REQUIRED. api.js puts "/subscription/" in ENCRYPTED_ENDPOINT_PREFIXES and
# only excludes /subscription/check-superapp/, so the client encrypts this
# body. 59223b6f removed this decorator on the premise that "the frontend
# excludes these from encryption" -- true of check-superapp, not of this
# endpoint -- and the mismatch made the view read an envelope instead of a
# payload, answering 400 "tier_id is required".
#
# It failed intermittently, which is why it survived: the client only encrypts
# once isCryptoReady() is true, so a request sent before the server key was
# fetched went through in the clear and worked.
@encrypted_endpoint
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
            return Response(
                {'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST
            )
        profile = getattr(request.user, 'profile', None)
        phone_number = profile.phone_number if profile else None

    if not phone_number:
        return Response({'error': 'Phone number not found'}, status=status.HTTP_400_BAD_REQUEST)

    normalized_phone = _normalize_ethiopian_phone(phone_number)
    if normalized_phone:
        phone_number = normalized_phone

    # Refuse a second subscription before any money moves.
    #
    # The page checks too, but it cannot be relied on: in the telebirr
    # SuperApp the visitor is not authenticated, so /subscriptions/ 401s for
    # them and the plan chooser is all they ever see -- they can tap Subscribe
    # repeatedly and be charged each time. Resolving by phone here catches
    # that case, which is exactly the one the client cannot.
    existing = active_subscription_for(
        user=request.user if request.user.is_authenticated else None,
        phone_number=phone_number,
    )
    if existing is not None:
        return Response(
            already_subscribed_payload(existing),
            status=status.HTTP_409_CONFLICT,
        )

    # And refuse while a previous push is still unconfirmed.
    #
    # The check above only sees an *active* subscription. A payment whose
    # callback has not arrived leaves the subscription pending, so the caller
    # still looks like a non-subscriber and can be charged again -- which is
    # what happens whenever the telebirr result URL is unreachable.
    if (
        pending_subscription_payment(
            user=request.user if request.user.is_authenticated else None,
            phone_number=phone_number,
        )
        is not None
    ):
        return Response(payment_pending_payload(), status=status.HTTP_409_CONFLICT)

    # The last thing before the push, and the reason it can be sent at all.
    #
    # A USSD Push puts a PIN prompt on the subscriber's handset. Before this,
    # reaching this endpoint was enough to raise that prompt for any number a
    # caller named. Now the payer must have answered a code sent to that
    # number, for this tier.
    #
    # Deliberately after the refusals above rather than before them: the
    # session is SPENT by this call, so checking it first would burn a
    # verification on a request that was going to be refused anyway, and send
    # the payer back for another code they did not need.
    #
    # The session carries no user when the payer has no account yet, which is
    # the ordinary case here -- the number is the identity, and
    # consume_verified_session binds to it either way.
    try:
        payment_otp.consume_verified_session(
            session_id=request.data.get('verification_session_id'),
            purpose=PaymentVerificationSession.PURPOSE_SUBSCRIPTION,
            phone_number=phone_number,
            user=request.user if request.user.is_authenticated else None,
            tier_id=tier_id,
        )
    except OtpVerificationFailed as refused:
        return Response(
            {'error': refused.message, 'code': refused.code},
            status=status.HTTP_403_FORBIDDEN,
        )

    amount = f'{float(tier.price_etb):.2f}'

    subscription_webhook_url = getattr(settings, 'TELEBIRR_SUBSCRIPTION_USSD_RESULT_URL', '')
    result = telebirr_direct_debit_service.initiate_ussd_push_payment(
        amount=amount,
        phone_number=phone_number,
        coins=0,
        result_url=subscription_webhook_url or None,
    )

    if not result.get('success'):
        return Response(
            {
                'error': result.get('error', 'USSD Push payment initiation failed'),
                'details': result,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Telebirr's ResponseCode/ResponseDesc were parsed by the service and then
    # thrown away here, which left "did Telebirr accept the push?" unanswerable
    # from the logs -- the only trace of an initiate was our own "Initiating
    # USSD Push payment" line, logged BEFORE the call. When callbacks stop
    # arriving, this is the line that says whether the push was ever delivered.
    #
    # The detail goes in the MESSAGE, not extra={}. common/middleware/logging.py
    # emits a fixed whitelist -- transaction_id, operation, duration_ms,
    # provider, result -- and silently drops every other key, which is why an
    # earlier version of this line logged nothing useful.
    logger.info(
        'Telebirr USSD push accepted: ResponseCode=%s desc=%r tier=%s callback=%s',
        result.get('response_code'),
        result.get('message'),
        tier.name,
        subscription_webhook_url or '(unset -- fell back to the coin callback)',
        extra={
            'operation': 'telebirr_ussd_subscription_initiate',
            'transaction_id': result.get('originator_conversation_id'),
            'provider': 'telebirr',
            'result': 'push_accepted',
        },
    )

    start_date = timezone.now()
    end_date = start_date + timedelta(days=tier.duration_days or 30)
    user_for_subscription = request.user if request.user.is_authenticated else None

    subscription = UserSubscription.objects.create(
        user=user_for_subscription,
        tier=tier,
        status='pending',
        duration_type=tier.duration_type,
        start_date=start_date,
        end_date=end_date,
        payment_method='telebirr',
        auto_renew=False,
    )

    payment_metadata = {} if user_for_subscription else {'phone_number': phone_number}
    payment = SubscriptionPayment.objects.create(
        user=user_for_subscription,
        subscription=subscription,
        amount=tier.price_etb,
        currency='ETB',
        status='pending',
        payment_method='telebirr',
        onevas_transaction_id=result.get('originator_conversation_id'),
        duration_type=tier.duration_type,
        period_start=start_date,
        period_end=end_date,
        metadata=payment_metadata,
    )

    return Response(
        {
            'success': True,
            'originator_conversation_id': result.get('originator_conversation_id'),
            'conversation_id': result.get('conversation_id'),
            'message': result.get('message'),
            'tier': {
                'id': str(tier.id),
                'name': tier.name,
                'slug': tier.slug,
                'price_etb': str(tier.price_etb),
                'duration_days': tier.duration_days,
            },
            'payment_id': str(payment.id),
        }
    )


def _activate_ussd_subscription_payment(payment, tier):
    """Activate the subscription linked to a USSD Push payment. Called only
    from inside telebirr_ussd_subscription_webhook's row lock on `payment`."""
    user = payment.user
    subscription = payment.subscription

    if subscription and subscription.status == 'pending':
        subscription.tier = tier
        subscription.duration_type = tier.duration_type
        subscription.payment_method = 'telebirr'
        if not subscription.user:
            subscription.user = user
        subscription.save()
        # Activate the subscription to grant the tier's bonus coins immediately.
        # activate() handles idempotency: it grants bonus_coins only once per period.
        subscription.activate()
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
            # Activate the existing subscription to grant bonus coins for the new period.
            subscription.activate()
        else:
            now = timezone.now()
            end_date = now + timedelta(days=tier.duration_days) if tier.duration_days else None
            subscription = UserSubscription.objects.create(
                user=user,
                tier=tier,
                status='active',
                duration_type=tier.duration_type,
                start_date=now,
                end_date=end_date,
                payment_method='telebirr',
                auto_renew=False,
            )
            # Activate the new subscription to grant the tier's bonus coins.
            subscription.activate()

    payment.subscription = subscription
    payment.status = 'completed'
    payment.save()

    SubscriptionHistory.objects.create(
        user=user,
        subscription=subscription,
        tier=tier,
        action='created',
        reason=f'USSD Push payment: {tier.name} subscription',
    )

    # Payment confirmed and plan active -- the point at which there is
    # something true to tell the subscriber. Keyed on the payment, so a
    # redelivered webhook finds the existing message rather than sending a
    # second one. Never raises: a paid subscription is not undone by a
    # notification.
    notify_telebirr_subscription_activated(subscription, source=TELEBIRR_SMS_USSD, payment=payment)

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

    try:
        raw_body = request.body or b''
        logger.info('[USSD SUBSCRIPTION WEBHOOK] Received callback, len=%d', len(raw_body))
        root = ET.fromstring(raw_body)
        namespaces = {
            'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
            'api': 'http://cps.huawei.com/cpsinterface/api_resultmgr',
            'res': 'http://cps.huawei.com/cpsinterface/result',
        }

        header = root.find('.//res:Header', namespaces)
        originator_conversation_id = (
            header.find('res:OriginatorConversationID', namespaces).text
            if header is not None
            else None
        )

        body_el = root.find('.//res:Body', namespaces)
        result_type = (
            body_el.find('res:ResultType', namespaces).text if body_el is not None else None
        )
        result_code = (
            body_el.find('res:ResultCode', namespaces).text if body_el is not None else None
        )

        transaction_id = None
        transaction_result = (
            body_el.find('res:TransactionResult', namespaces) if body_el is not None else None
        )
        if transaction_result is not None:
            transaction_id_elem = transaction_result.find('res:TransactionID', namespaces)
            if transaction_id_elem is not None:
                transaction_id = transaction_id_elem.text

        logger.info(
            '[USSD SUBSCRIPTION WEBHOOK] originator=%s result_code=%s result_type=%s transaction_id=%s',
            originator_conversation_id,
            result_code,
            result_type,
            transaction_id,
        )

        if not originator_conversation_id:
            return Response(
                {'result': 'SUCCESS', 'code': '0', 'msg': 'no originator_conversation_id'}
            )

        is_success = result_code == '0' and result_type == '0'
        activated_user = None

        with transaction.atomic():
            payment = (
                SubscriptionPayment.objects.select_for_update()
                .filter(
                    onevas_transaction_id=originator_conversation_id,
                    payment_method='telebirr',
                    status='pending',
                )
                .first()
            )

            if not payment:
                logger.info(
                    '[USSD SUBSCRIPTION WEBHOOK] No pending payment for %s (already processed or unknown)',
                    originator_conversation_id,
                )
                return Response(
                    {'result': 'SUCCESS', 'code': '0', 'msg': 'no pending payment found'}
                )

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
                    metadata = payment.metadata or {}
                    metadata['is_new_user'] = False
                    payment.metadata = metadata
                else:
                    username = f'user_{normalized_phone[-8:]}'
                    user = User.objects.create_user(username=username, password=None)
                    UserProfile.objects.update_or_create(
                        user=user,
                        defaults={'phone_number': normalized_phone},
                    )
                    payment.user = user
                    metadata = payment.metadata or {}
                    metadata['is_new_user'] = True
                    payment.metadata = metadata
                payment.save()
            elif user:
                metadata = payment.metadata or {}
                metadata['is_new_user'] = False
                payment.metadata = metadata
                payment.save()

            if not user:
                payment.status = 'failed'
                payment.save()
                return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'no user found'})

            tier = (
                SubscriptionTier.objects.filter(is_active=True)
                .filter(price_etb=payment.amount)
                .first()
            )
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
                phone_number = getattr(
                    getattr(activated_user, 'profile', None), 'phone_number', None
                )
                if phone_number:
                    from api.services.otp import OTPService

                    OTPService.send_otp(phone_number, action='subscription_login')
            except Exception as otp_error:
                logger.error('[USSD SUBSCRIPTION WEBHOOK] Error sending login OTP: %s', otp_error)

        return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'subscription activated'})

    except Exception as e:
        logger.exception('[USSD SUBSCRIPTION WEBHOOK] Error processing webhook: %s', e)
        return Response({'result': 'SUCCESS', 'code': '0', 'msg': 'error processed'})
