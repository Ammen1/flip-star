from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, F, Sum, Count, Case, When
from django.utils import timezone
from django.contrib.auth.models import User

from .models_gift import Gift, GiftTransaction, GiftCombo, UserGiftStats
from .serializers_gift import (
    GiftSerializer, GiftCreateSerializer, GiftUpdateSerializer,
    GiftTransactionSerializer, SendGiftSerializer, GiftComboSerializer,
    UserGiftStatsSerializer, GiftLeaderboardSerializer
)
from .models import UserProfile, Reel
from .models_contest import UserCoinBalance
from .models_wallet import WalletConfig


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


class PublicGiftViewSet(viewsets.ReadOnlyModelViewSet):
    """Public viewset for users to view available gifts"""
    permission_classes = [permissions.AllowAny]
    http_method_names = ['get', 'head', 'options', 'post']  # Explicitly allow GET, HEAD, OPTIONS, POST
    
    def get_queryset(self):
        if Gift.objects.count() == 0:
            self._create_default_gifts()
        return Gift.objects.filter(is_active=True).order_by('sort_order', 'coin_value', 'name')
        
    def _create_default_gifts(self):
        # Default gifts use lucide-react icon names — no image upload required.
        # Frontend renders these via the lucide-react library.
        default_gifts = [
            {'name': 'Rose',       'icon_name': 'Flower2',  'icon_color': '#EC4899', 'category': 'flowers',  'coin_value': 10,   'rarity': 'common',    'sort_order': 1},
            {'name': 'Heart',      'icon_name': 'Heart',    'icon_color': '#EF4444', 'category': 'hearts',   'coin_value': 50,   'rarity': 'common',    'sort_order': 2},
            {'name': 'Star',       'icon_name': 'Star',     'icon_color': '#F59E0B', 'category': 'special',  'coin_value': 100,  'rarity': 'rare',      'sort_order': 3},
            {'name': 'Teddy Bear', 'icon_name': 'Cat',      'icon_color': '#A78BFA', 'category': 'animals',  'coin_value': 200,  'rarity': 'rare',      'sort_order': 4},
            {'name': 'Diamond',    'icon_name': 'Diamond',  'icon_color': '#06B6D4', 'category': 'gems',     'coin_value': 500,  'rarity': 'epic',      'sort_order': 5},
            {'name': 'Crown',      'icon_name': 'Crown',    'icon_color': '#FBBF24', 'category': 'special',  'coin_value': 750,  'rarity': 'epic',      'sort_order': 6},
            {'name': 'Sports Car', 'icon_name': 'Car',      'icon_color': '#DC2626', 'category': 'vehicles', 'coin_value': 1000, 'rarity': 'legendary', 'sort_order': 7},
            {'name': 'Rocket',     'icon_name': 'Rocket',   'icon_color': '#8B5CF6', 'category': 'special',  'coin_value': 2000, 'rarity': 'legendary', 'sort_order': 8},
        ]
        for gift_data in default_gifts:
            Gift.objects.get_or_create(name=gift_data['name'], defaults=gift_data)
    
    serializer_class = GiftSerializer
    
    def list(self, request, *args, **kwargs):
        """Override list to return results in a consistent format"""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': queryset.count()
        })
        
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def send(self, request):
        """Send a gift to another user by username"""
        gift_id = request.data.get('gift_id')
        recipient_username = request.data.get('recipient_username')
        quantity = request.data.get('quantity', 1)
        message = request.data.get('message', '')
        
        try:
            recipient = User.objects.get(username=recipient_username)
        except User.DoesNotExist:
            return Response({'error': 'Recipient not found'}, status=status.HTTP_404_NOT_FOUND)
            
        data = {
            'gift_id': gift_id,
            'recipient_id': recipient.id,
            'quantity': quantity,
            'message': message,
        }
        
        # Instantiate GiftTransactionViewSet to reuse send_gift logic
        viewset = GiftTransactionViewSet()
        viewset.request = request
        viewset.format_kwarg = self.format_kwarg
        return viewset.send_gift(request, data)


class GiftTransactionViewSet(viewsets.ModelViewSet):
    """Viewset for gift transactions"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = GiftTransaction.objects.select_related('sender', 'recipient', 'gift', 'reel')
        
        # Filter by user (either sender or recipient)
        user = self.request.query_params.get('user')
        if user:
            queryset = queryset.filter(
                Q(sender_id=user) | Q(recipient_id=user)
            )
        
        # Filter by current user
        if not self.request.user.is_staff:
            queryset = queryset.filter(
                Q(sender=self.request.user) | Q(recipient=self.request.user)
            )
        
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
        gift_id = data['gift_id']
        recipient_id = data['recipient_id']
        reel_id = data.get('reel_id')
        quantity = data['quantity']
        message = data.get('message', '')
        
        # Validate gift
        try:
            gift = Gift.objects.get(id=gift_id, is_active=True)
        except Gift.DoesNotExist:
            return Response(
                {'error': 'Gift not found or not active'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate recipient
        try:
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'Recipient not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Prevent self-gifting
        if recipient == request.user:
            return Response(
                {'error': 'Cannot send gifts to yourself'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate reel if provided
        reel = None
        if reel_id:
            try:
                reel = Reel.objects.get(id=reel_id)
            except Reel.DoesNotExist:
                return Response(
                    {'error': 'Reel not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Check wallet config for gifting policy
        wallet_config = WalletConfig.get_config()
        
        # Get or create sender's coin balance
        sender_coin_balance, _ = UserCoinBalance.objects.get_or_create(user=request.user)
        
        total_cost = gift.coin_value * quantity
        
        # Check if purchased coins can be used for gifting
        if not wallet_config.purchased_coins_giftable:
            return Response(
                {'error': 'Purchased coins cannot be used for gifting at this time.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if sender has enough purchased coins
        if (sender_coin_balance.purchased_balance or 0) < total_cost:
            return Response(
                {
                    'error': f'Insufficient purchased coins. You need {total_cost} purchased coins but have {sender_coin_balance.purchased_balance or 0}. '
                    f'Your total balance is {sender_coin_balance.balance} (earned: {sender_coin_balance.earned_balance or 0}, purchased: {sender_coin_balance.purchased_balance or 0}). '
                    f'Only purchased coins can be used for gifting. Please top up your coins.',
                    'needs_recharge': True,
                    'required_coins': total_cost,
                    'current_purchased_coins': sender_coin_balance.purchased_balance or 0,
                    'current_earned_coins': sender_coin_balance.earned_balance or 0
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Deduct coins from purchased balance (restrict_earned=True for gifting)
        try:
            sender_coin_balance.spend_coins(
                amount=total_cost,
                transaction_type='gift_sent',
                restrict_earned=True,  # Only use purchased coins for gifting
                recipient=recipient,
                reel=reel,
                gift=gift
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        # Update sender profile stats
        sender_profile = request.user.profile
        sender_profile.coins_spent_total += total_cost
        sender_profile.gifts_sent_total += 1
        sender_profile.save()
        
        # Convert coins to points for recipient (gifts convert to points, not coins)
        wallet_config = WalletConfig.get_config()
        points_received = wallet_config.coins_to_points(total_cost)
        
        # Add points to recipient (not coins)
        recipient_profile = recipient.profile
        recipient_profile.points += points_received
        recipient_profile.points_earned_total += points_received
        recipient_profile.gifts_received_total += 1
        recipient_profile.save()
        
        # Handle combo logic
        is_combo = False
        combo_multiplier = 1.0
        
        if reel:
            # Check for existing active combo
            active_combo = GiftCombo.objects.filter(
                user=request.user,
                reel=reel,
                gift=gift,
                is_active=True
            ).first()
            
            if active_combo:
                # Update existing combo
                time_since_last = (timezone.now() - active_combo.last_gift_at).total_seconds()
                if time_since_last <= 5:  # 5 second window for combo
                    active_combo.combo_count += quantity
                    active_combo.total_coins += total_cost
                    active_combo.last_gift_at = timezone.now()
                    active_combo.save()
                    is_combo = True
                    combo_multiplier = 1.0 + (active_combo.combo_count * 0.1)  # 10% bonus per combo
                else:
                    # Combo expired, start new
                    active_combo.is_active = False
                    active_combo.save()
                    active_combo = None
            
            if not active_combo:
                # Create new combo
                new_combo = GiftCombo.objects.create(
                    user=request.user,
                    reel=reel,
                    gift=gift,
                    combo_count=quantity,
                    total_coins=total_cost
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
            message=message
        )
        
        # Update user gift stats
        self.update_gift_stats(request.user, recipient, gift, total_cost)
        
        # Create notification
        from .models import Notification
        Notification.objects.create(
            recipient=recipient,
            sender=request.user,
            notification_type='gift',
            reel=reel,
            message=f'{request.user.username} sent you {quantity}x {gift.name}!'
        )
        
        # Award XP to sender
        xp_reward = gift.xp_reward * quantity
        if xp_reward > 0:
            sender_profile.xp += xp_reward
            sender_profile.save()
        
        serializer = GiftTransactionSerializer(transaction, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update_gift_stats(self, sender, recipient, gift, coins):
        """Update gift statistics for both users"""
        # Sender stats
        sender_stats, _ = UserGiftStats.objects.get_or_create(user=sender)
        sender_stats.total_gifts_sent += 1
        sender_stats.total_coins_sent += coins
        
        # Update unique recipients
        unique_recipients = GiftTransaction.objects.filter(
            sender=sender
        ).values('recipient').distinct().count()
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
        
        sender_stats.save()
        
        # Recipient stats
        recipient_stats, _ = UserGiftStats.objects.get_or_create(user=recipient)
        recipient_stats.total_gifts_received += 1
        recipient_stats.total_coins_received += coins
        
        # Update unique senders
        unique_senders = GiftTransaction.objects.filter(
            recipient=recipient
        ).values('sender').distinct().count()
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
        
        recipient_stats.save()
    
    @action(detail=False, methods=['get'])
    def my_sent(self, request):
        """Get gifts sent by current user"""
        transactions = GiftTransaction.objects.filter(
            sender=request.user
        ).select_related('recipient', 'gift', 'reel').order_by('-created_at')
        serializer = GiftTransactionSerializer(transactions, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_received(self, request):
        """Get gifts received by current user"""
        transactions = GiftTransaction.objects.filter(
            recipient=request.user
        ).select_related('sender', 'gift', 'reel').order_by('-created_at')
        serializer = GiftTransactionSerializer(transactions, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def leaderboard(self, request):
        """Get gift leaderboard (most gifts received)"""
        leaderboard_data = UserGiftStats.objects.annotate(
            username=F('user__username')
        ).order_by('-total_coins_received')[:50]
        
        leaderboard = []
        for idx, stats in enumerate(leaderboard_data, 1):
            leaderboard.append({
                'rank': idx,
                'username': stats.username,
                'total_gifts_received': stats.total_gifts_received,
                'total_coins_received': stats.total_coins_received
            })
        
        serializer = GiftLeaderboardSerializer(leaderboard, many=True)
        return Response(serializer.data)


class UserGiftStatsViewSet(viewsets.ReadOnlyModelViewSet):
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
