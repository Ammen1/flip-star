from django.contrib.auth.models import User
from django.db import transaction as db_transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.models import Reel, UserProfile
from api.models.contest import UserCoinBalance
from api.models.gift import Gift, GiftCombo, GiftTransaction, UserGiftStats
from api.models.wallet import WalletConfig
from api.serializers.gift import (
    GiftCreateSerializer,
    GiftLeaderboardSerializer,
    GiftSerializer,
    GiftTransactionSerializer,
    GiftUpdateSerializer,
    SendGiftSerializer,
    UserGiftStatsSerializer,
)
from api.services.coin_purchase import insufficient_coins_payload
from common.security import EncryptedPayloadMixin


class GiftViewSet(viewsets.ModelViewSet):
    """Admin viewset for managing gifts"""

    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        queryset = Gift.objects.all()
        category = self.request.query_params.get('category')
        rarity = self.request.query_params.get('rarity')
        is_active = self.request.query_params.get('is_active')

        if category:
            queryset = queryset.filter(category=category)
        if rarity:
            queryset = queryset.filter(rarity=rarity)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return GiftCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return GiftUpdateSerializer
        return GiftSerializer

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get all active gifts for the gift selector"""
        gifts = Gift.objects.filter(is_active=True).order_by('sort_order', 'coin_value', 'name')
        serializer = GiftSerializer(gifts, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_category(self, request):
        """Get gifts grouped by category"""
        gifts = Gift.objects.filter(is_active=True).order_by('category', 'sort_order', 'coin_value')
        serializer = GiftSerializer(gifts, many=True, context={'request': request})

        # Group by category
        grouped = {}
        for gift in serializer.data:
            category = gift['category']
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(gift)

        return Response(grouped)


class PublicGiftViewSet(EncryptedPayloadMixin, viewsets.ReadOnlyModelViewSet):
    """Public viewset for users to view available gifts"""

    permission_classes = [permissions.AllowAny]
    http_method_names = [
        'get',
        'head',
        'options',
        'post',
    ]  # Explicitly allow GET, HEAD, OPTIONS, POST

    def get_queryset(self):
        if Gift.objects.count() == 0:
            self._create_default_gifts()
        return Gift.objects.filter(is_active=True).order_by('sort_order', 'coin_value', 'name')

    def _create_default_gifts(self):
        # Default gifts use lucide-react icon names — no image upload required.
        # Frontend renders these via the lucide-react library.
        default_gifts = [
            {
                'name': 'Rose',
                'icon_name': 'Flower2',
                'icon_color': '#EC4899',
                'category': 'flowers',
                'coin_value': 10,
                'rarity': 'common',
                'sort_order': 1,
            },
            {
                'name': 'Heart',
                'icon_name': 'Heart',
                'icon_color': '#EF4444',
                'category': 'hearts',
                'coin_value': 50,
                'rarity': 'common',
                'sort_order': 2,
            },
            {
                'name': 'Star',
                'icon_name': 'Star',
                'icon_color': '#F59E0B',
                'category': 'special',
                'coin_value': 100,
                'rarity': 'rare',
                'sort_order': 3,
            },
            {
                'name': 'Teddy Bear',
                'icon_name': 'Cat',
                'icon_color': '#A78BFA',
                'category': 'animals',
                'coin_value': 200,
                'rarity': 'rare',
                'sort_order': 4,
            },
            {
                'name': 'Diamond',
                'icon_name': 'Diamond',
                'icon_color': '#06B6D4',
                'category': 'gems',
                'coin_value': 500,
                'rarity': 'epic',
                'sort_order': 5,
            },
            {
                'name': 'Crown',
                'icon_name': 'Crown',
                'icon_color': '#FBBF24',
                'category': 'special',
                'coin_value': 750,
                'rarity': 'epic',
                'sort_order': 6,
            },
            {
                'name': 'Sports Car',
                'icon_name': 'Car',
                'icon_color': '#DC2626',
                'category': 'vehicles',
                'coin_value': 1000,
                'rarity': 'legendary',
                'sort_order': 7,
            },
            {
                'name': 'Rocket',
                'icon_name': 'Rocket',
                'icon_color': '#8B5CF6',
                'category': 'special',
                'coin_value': 2000,
                'rarity': 'legendary',
                'sort_order': 8,
            },
        ]
        for gift_data in default_gifts:
            Gift.objects.get_or_create(name=gift_data['name'], defaults=gift_data)

    serializer_class = GiftSerializer

    def list(self, request, *args, **kwargs):
        """Override list to return results in a consistent format"""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({'results': serializer.data, 'count': queryset.count()})

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def send(self, request):
        """Send a gift to another user by username or phone number"""
        gift_id = request.data.get('gift_id')
        recipient_username = request.data.get('recipient_username')
        phone_number = request.data.get('phone_number')
        quantity = request.data.get('quantity', 1)
        message = request.data.get('message', '')
        reel_id = request.data.get('reel_id')

        # Validate that at least one identifier is provided
        if not recipient_username and not phone_number:
            return Response(
                {'error': 'Either recipient_username or phone_number is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Look up recipient by phone number if provided
        if phone_number:
            # Normalize phone number
            phone_number = phone_number.replace(' ', '').replace('-', '').replace('+', '')
            if not phone_number.startswith('251'):
                phone_number = '251' + phone_number

            try:
                recipient = User.objects.get(profile__phone_number=phone_number)
            except User.DoesNotExist:
                return Response(
                    {'error': 'User with this phone number not found'},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            # Look up recipient by username
            try:
                recipient = User.objects.get(username=recipient_username)
            except User.DoesNotExist:
                return Response({'error': 'Recipient not found'}, status=status.HTTP_404_NOT_FOUND)

        data = {
            'gift_id': gift_id,
            'recipient_id': recipient.id,
            'quantity': quantity,
            'message': message,
            'reel_id': reel_id,
        }

        # Instantiate GiftTransactionViewSet to reuse send_gift logic
        viewset = GiftTransactionViewSet()
        viewset.request = request
        viewset.format_kwarg = self.format_kwarg
        return viewset.send_gift(request, data)


class GiftTransactionViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    """Viewset for gift transactions"""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = GiftTransaction.objects.select_related('sender', 'recipient', 'gift', 'reel')

        # Filter by user (either sender or recipient)
        user = self.request.query_params.get('user')
        if user:
            queryset = queryset.filter(Q(sender_id=user) | Q(recipient_id=user))

        # Filter by current user
        if not self.request.user.is_staff:
            queryset = queryset.filter(Q(sender=self.request.user) | Q(recipient=self.request.user))

        # Filter by reel
        reel_id = self.request.query_params.get('reel')
        if reel_id:
            queryset = queryset.filter(reel_id=reel_id)

        return queryset.order_by('-created_at')

    serializer_class = GiftTransactionSerializer

    def create(self, request, *args, **kwargs):
        """Send a gift to another user"""
        serializer = SendGiftSerializer(data=request.data)
        if serializer.is_valid():
            return self.send_gift(request, serializer.validated_data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def send_gift(self, request, data):
        # Gifting is subscriber-only. Checked here rather than in `create`
        # so the rule holds for every caller of this method, not only the
        # one route that happens to reach it today.
        from api.services import contribution_limits
        from api.services.subscription_access import subscriber_action_refusal

        refusal = subscriber_action_refusal(request.user, 'gift')
        if refusal is not None:
            return Response(refusal, status=status.HTTP_403_FORBIDDEN)

        gift_id = data['gift_id']
        recipient_id = data['recipient_id']
        reel_id = data.get('reel_id')
        quantity = data['quantity']
        message = data.get('message', '')

        print(f'[GIFT_SEND] reel_id from request: {reel_id}')

        # Validate gift
        try:
            gift = Gift.objects.get(id=gift_id, is_active=True)
        except Gift.DoesNotExist:
            return Response(
                {'error': 'Gift not found or not active'}, status=status.HTTP_404_NOT_FOUND
            )

        # Validate recipient
        try:
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist:
            return Response({'error': 'Recipient not found'}, status=status.HTTP_404_NOT_FOUND)

        # Prevent self-gifting
        if recipient == request.user:
            return Response(
                {'error': 'Cannot send gifts to yourself'}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validate reel if provided
        reel = None
        if reel_id:
            try:
                reel = Reel.objects.get(id=reel_id)
            except Reel.DoesNotExist:
                return Response({'error': 'Reel not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check wallet config for gifting policy
        wallet_config = WalletConfig.get_config()

        # Get or create sender's coin balance
        sender_coin_balance, _ = UserCoinBalance.objects.get_or_create(user=request.user)

        total_cost = gift.coin_value * quantity

        # Convert coins to points for restriction checks
        points_cost = wallet_config.coins_to_points(total_cost)

        # Check minimum points per transaction
        if points_cost < wallet_config.gift_min_points_per_transaction:
            return Response(
                {
                    'error': f'Minimum {wallet_config.gift_min_points_per_transaction} points required per gift transaction',
                    'min_points': wallet_config.gift_min_points_per_transaction,
                    'points_cost': points_cost,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check maximum points per transaction
        if points_cost > wallet_config.gift_max_points_per_transaction:
            return Response(
                {
                    'error': f'Maximum {wallet_config.gift_max_points_per_transaction} points allowed per gift transaction',
                    'max_points': wallet_config.gift_max_points_per_transaction,
                    'points_cost': points_cost,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check daily limit to specific recipient (Voting Cap)
        from datetime import timedelta

        twenty_four_hours_ago = timezone.now() - timedelta(hours=24)

        gifts_to_recipient_today = (
            GiftTransaction.objects.filter(
                sender=request.user, recipient=recipient, created_at__gte=twenty_four_hours_ago
            ).aggregate(total=Sum('total_coins'))['total']
            or 0
        )

        points_to_recipient_today = wallet_config.coins_to_points(gifts_to_recipient_today)

        if (
            points_to_recipient_today + points_cost
            > wallet_config.gift_max_points_to_recipient_per_day
        ):
            return Response(
                {
                    'error': f'Maximum {wallet_config.gift_max_points_to_recipient_per_day} points can be sent to one recipient per day',
                    'max_points': wallet_config.gift_max_points_to_recipient_per_day,
                    'points_sent_today': points_to_recipient_today,
                    'points_cost': points_cost,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check total daily outgoing limit
        total_gifts_today = (
            GiftTransaction.objects.filter(
                sender=request.user, created_at__gte=twenty_four_hours_ago
            ).aggregate(total=Sum('total_coins'))['total']
            or 0
        )

        points_sent_today = wallet_config.coins_to_points(total_gifts_today)

        if points_sent_today + points_cost > wallet_config.gift_max_total_points_sent_per_day:
            return Response(
                {
                    'error': f'Maximum {wallet_config.gift_max_total_points_sent_per_day} points can be sent per day total',
                    'max_points': wallet_config.gift_max_total_points_sent_per_day,
                    'points_sent_today': points_sent_today,
                    'points_cost': points_cost,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if purchased coins can be used for gifting
        if not wallet_config.purchased_coins_giftable:
            return Response(
                {'error': 'Purchased coins cannot be used for gifting at this time.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Can the sender actually pay for this gift?
        #
        # `giftable_balance` is the single definition of what may fund a gift,
        # shared with spend_coins. This check used to read `purchased_balance`,
        # which also counts airtime coins that spend_coins then refuses -- so a
        # user holding airtime coins passed here and hit a raw ValueError from
        # inside the spend instead of a considered response.
        giftable = sender_coin_balance.giftable_balance
        bonus = sender_coin_balance.bonus_balance or 0

        if giftable < total_cost:
            # Bonus coins get their own answer. A user holding 500 bonus coins
            # and being told they have insufficient coins would reasonably think
            # the balance was wrong, so the response says which coins cannot pay
            # and why, and carries the numbers behind that decision.
            if bonus > 0:
                return Response(
                    {
                        'success': False,
                        'code': 'BONUS_COINS_NOT_ELIGIBLE_FOR_GIFT',
                        'message': (
                            'Subscription bonus coins cannot be used to send gifts. '
                            'Please use purchased coins.'
                        ),
                        'purchased_coins': giftable,
                        'bonus_coins': bonus,
                        'required_coins': total_cost,
                        # Kept so existing clients, which read `error` and the
                        # insufficient-coins shape, still render something useful.
                        'error': (
                            'Subscription bonus coins cannot be used to send gifts. '
                            'Please use purchased coins.'
                        ),
                        'required': total_cost,
                        'available': giftable,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                insufficient_coins_payload(
                    total_cost,
                    giftable,
                    message=(
                        f'You need {total_cost} purchased coins to send this gift and have '
                        f'{giftable}. Only coins bought via Telebirr can be gifted.'
                    ),
                    current_purchased_coins=sender_coin_balance.purchased_balance or 0,
                    current_earned_coins=sender_coin_balance.earned_balance or 0,
                    total_balance=sender_coin_balance.balance,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Deduct the coins, record the combo and create the transaction as
        # one unit. None of it was in a transaction before: spend_coins took
        # the coins, and any failure after that -- the combo write, the
        # transaction insert itself -- left the sender charged with no gift
        # and nothing to reconcile against, since GiftTransaction is the only
        # record that the gift ever happened.
        try:
            with db_transaction.atomic():
                # One contributor may give one creator 500 coins in a
                # rolling 24 hours. Inside the transaction, with the
                # sender's balance row locked first, so two gifts arriving
                # together cannot both read the same total and both pass.
                contribution_limits.lock_sender(request.user)
                over_limit = contribution_limits.refusal(request.user, recipient, total_cost)
                if over_limit is not None:
                    return Response(over_limit, status=status.HTTP_400_BAD_REQUEST)

                sender_coin_balance.spend_coins(
                    amount=total_cost,
                    transaction_type='gift_sent',
                    restrict_earned=True,  # Only use purchased coins for gifting
                    recipient=recipient,
                    reel=reel,
                    description=f'Sent {gift.name} to @{recipient.username}',
                )

                # Update sender profile stats. Pure lifetime counters (not a spendable
                # balance -- coins_spent_total mirrors what spend_coins already
                # accounted for above), so an atomic F() UPDATE is enough: no lost
                # updates when two gifts from the same sender land at once, and no
                # explicit transaction/lock needed for a single UPDATE statement.
                sender_profile = request.user.profile
                UserProfile.objects.filter(pk=sender_profile.pk).update(
                    coins_spent_total=F('coins_spent_total') + total_cost,
                    gifts_sent_total=F('gifts_sent_total') + 1,
                )

                # Convert coins to points for recipient (gifts convert to points, not coins)
                wallet_config = WalletConfig.get_config()
                points_received = wallet_config.coins_to_points(total_cost)

                # Add points to recipient (not coins). Row-locked via add_points --
                # see UserProfile._apply_delta's docstring: two gifts landing on the
                # same recipient at once must not lose one of the credits.
                recipient_profile = recipient.profile
                recipient_profile.add_points(points_received, reason='gift_received')
                UserProfile.objects.filter(pk=recipient_profile.pk).update(
                    gifts_received_total=F('gifts_received_total') + 1
                )

                # Log gift_received as a CoinTransaction for the recipient's activity feed
                # coins field stores the points received (1 coin = 1 point conversion)
                from api.models.contest import CoinTransaction

                CoinTransaction.objects.create(
                    user=recipient,
                    transaction_type='gift_received',
                    coins=points_received,
                    recipient=request.user,  # The sender (stored as "other party")
                    reel=reel,
                    description=f'Received {gift.name} from @{request.user.username}',
                )

                # Handle combo logic
                is_combo = False
                combo_multiplier = 1.0

                if reel:
                    # Check for existing active combo
                    active_combo = GiftCombo.objects.filter(
                        user=request.user, reel=reel, gift=gift, is_active=True
                    ).first()

                    if active_combo:
                        # Update existing combo
                        time_since_last = (
                            timezone.now() - active_combo.last_gift_at
                        ).total_seconds()
                        if time_since_last <= 5:  # 5 second window for combo
                            active_combo.combo_count += quantity
                            active_combo.total_coins += total_cost
                            active_combo.last_gift_at = timezone.now()
                            active_combo.save()
                            is_combo = True
                            combo_multiplier = 1.0 + (
                                active_combo.combo_count * 0.1
                            )  # 10% bonus per combo
                        else:
                            # Combo expired, start new
                            active_combo.is_active = False
                            active_combo.save()
                            active_combo = None

                    if not active_combo:
                        # Create new combo
                        GiftCombo.objects.create(
                            user=request.user,
                            reel=reel,
                            gift=gift,
                            combo_count=quantity,
                            total_coins=total_cost,
                        )
                        if quantity > 1:
                            is_combo = True
                            combo_multiplier = 1.0 + (quantity * 0.1)

                # Create gift transaction
                transaction = GiftTransaction.objects.create(
                    sender=request.user,
                    recipient=recipient,
                    gift=gift,
                    reel=reel,
                    quantity=quantity,
                    total_coins=total_cost,
                    is_combo=is_combo,
                    combo_multiplier=combo_multiplier,
                    message=message,
                )

        except ValueError as e:
            # spend_coins raises this for an insufficient balance. The atomic
            # block has already rolled back, so the sender's coins are intact
            # and no partial gift row survives.
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Update user gift stats
        self.update_gift_stats(request.user, recipient, gift, total_cost)

        # Create notification
        from api.models import Notification

        Notification.objects.create(
            recipient=recipient,
            sender=request.user,
            notification_type='gift',
            reel=reel,
            message=f'{request.user.username} sent you {quantity}x {gift.name}!',
        )

        # Award XP to sender. Atomic F() UPDATE, scoped to just this column --
        # a plain sender_profile.save() here would silently overwrite the
        # coins_spent_total/gifts_sent_total UPDATE above with sender_profile's
        # stale in-memory copy of those fields.
        xp_reward = gift.xp_reward * quantity
        if xp_reward > 0:
            UserProfile.objects.filter(pk=sender_profile.pk).update(xp=F('xp') + xp_reward)

        # Charge admin-configurable extra coin cost when gifting on a campaign post
        # (separate from gift coin_value; default 0). Deducts from earned + purchased.
        if reel and reel.is_campaign_post and reel.user != request.user:
            extra_cost = wallet_config.cost_gift
            if extra_cost and extra_cost > 0:
                try:
                    sender_coin_balance.spend_coins(
                        extra_cost,
                        'campaign_gift_fee',
                        reel=reel,
                        description=f'Campaign gift fee on post #{reel.id}',
                    )
                except ValueError as e:
                    # Surface the error but do not roll back the gift (transaction already recorded)
                    print(f'[CAMPAIGN_GIFT_FEE] Could not charge fee: {e}')

        serializer = GiftTransactionSerializer(transaction, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update_gift_stats(self, sender, recipient, gift, coins):
        """Update gift statistics for both users.

        total_gifts_sent/total_coins_sent (and the received counterparts) are
        plain lifetime counters, so they're incremented with an atomic F()
        UPDATE -- immune to lost updates when two gifts from/to the same user
        land at once, no explicit transaction/lock needed for a single UPDATE.
        unique_recipients/unique_senders and favorite_gift_sent/
        favorite_gift_received are recomputed from a fresh COUNT/comparison
        each call rather than incremented, so they're self-correcting even
        if two concurrent calls race to write them last; they're saved via
        update_fields scoped to just those two columns so that race can never
        clobber the F()-incremented counters above.
        """
        # Sender stats
        UserGiftStats.objects.get_or_create(user=sender)
        UserGiftStats.objects.filter(user=sender).update(
            total_gifts_sent=F('total_gifts_sent') + 1,
            total_coins_sent=F('total_coins_sent') + coins,
        )
        sender_stats = UserGiftStats.objects.get(user=sender)

        # Update unique recipients
        unique_recipients = (
            GiftTransaction.objects.filter(sender=sender).values('recipient').distinct().count()
        )
        sender_stats.unique_recipients = unique_recipients

        # Update favorite gift sent
        if sender_stats.favorite_gift_sent:
            current_count = GiftTransaction.objects.filter(
                sender=sender, gift=sender_stats.favorite_gift_sent
            ).count()
            gift_count = GiftTransaction.objects.filter(sender=sender, gift=gift).count()
            if gift_count > current_count:
                sender_stats.favorite_gift_sent = gift
        else:
            sender_stats.favorite_gift_sent = gift

        sender_stats.save(update_fields=['unique_recipients', 'favorite_gift_sent'])

        # Recipient stats
        UserGiftStats.objects.get_or_create(user=recipient)
        UserGiftStats.objects.filter(user=recipient).update(
            total_gifts_received=F('total_gifts_received') + 1,
            total_coins_received=F('total_coins_received') + coins,
        )
        recipient_stats = UserGiftStats.objects.get(user=recipient)

        # Update unique senders
        unique_senders = (
            GiftTransaction.objects.filter(recipient=recipient).values('sender').distinct().count()
        )
        recipient_stats.unique_senders = unique_senders

        # Update favorite gift received
        if recipient_stats.favorite_gift_received:
            current_count = GiftTransaction.objects.filter(
                recipient=recipient, gift=recipient_stats.favorite_gift_received
            ).count()
            gift_count = GiftTransaction.objects.filter(recipient=recipient, gift=gift).count()
            if gift_count > current_count:
                recipient_stats.favorite_gift_received = gift
        else:
            recipient_stats.favorite_gift_received = gift

        recipient_stats.save(update_fields=['unique_senders', 'favorite_gift_received'])

    @action(detail=False, methods=['get'])
    def my_sent(self, request):
        """Get gifts sent by current user"""
        transactions = (
            GiftTransaction.objects.filter(sender=request.user)
            .select_related('recipient', 'gift', 'reel')
            .order_by('-created_at')
        )
        serializer = GiftTransactionSerializer(
            transactions, many=True, context={'request': request}
        )
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_received(self, request):
        """Get gifts received by current user"""
        transactions = (
            GiftTransaction.objects.filter(recipient=request.user)
            .select_related('sender', 'gift', 'reel')
            .order_by('-created_at')
        )
        serializer = GiftTransactionSerializer(
            transactions, many=True, context={'request': request}
        )
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def leaderboard(self, request):
        """Get gift leaderboard (most gifts received)"""
        leaderboard_data = UserGiftStats.objects.annotate(username=F('user__username')).order_by(
            '-total_coins_received'
        )[:50]

        leaderboard = []
        for idx, stats in enumerate(leaderboard_data, 1):
            leaderboard.append(
                {
                    'rank': idx,
                    'username': stats.username,
                    'total_gifts_received': stats.total_gifts_received,
                    'total_coins_received': stats.total_coins_received,
                }
            )

        serializer = GiftLeaderboardSerializer(leaderboard, many=True)
        return Response(serializer.data)


class UserGiftStatsViewSet(EncryptedPayloadMixin, viewsets.ReadOnlyModelViewSet):
    """Viewset for user gift statistics"""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return UserGiftStats.objects.all()
        return UserGiftStats.objects.filter(user=self.request.user)

    serializer_class = UserGiftStatsSerializer

    @action(detail=False, methods=['get'])
    def my_stats(self, request):
        """Get current user's gift statistics"""
        stats, created = UserGiftStats.objects.get_or_create(user=request.user)
        serializer = UserGiftStatsSerializer(stats, context={'request': request})
        return Response(serializer.data)
