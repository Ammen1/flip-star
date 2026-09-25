import uuid

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Gift(models.Model):
    """Configuration for virtual gifts that users can send to each other"""
    
    RARITY_CHOICES = [
        ('common', 'Common'),
        ('rare', 'Rare'),
        ('epic', 'Epic'),
        ('legendary', 'Legendary'),
    ]
    
    CATEGORY_CHOICES = [
        ('flowers', 'Flowers'),
        ('hearts', 'Hearts'),
        ('gems', 'Gems'),
        ('special', 'Special'),
        ('animals', 'Animals'),
        ('vehicles', 'Vehicles'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='gifts/', null=True, blank=True, help_text='Optional uploaded icon/image (overrides icon_name if set)')
    animated_image = models.ImageField(upload_to='gifts/animated/', null=True, blank=True, help_text='Animated version of the gift')

    # Lucide icon name for default rendering when no image is uploaded.
    # Frontend renders <LucideIcon name={icon_name} /> from lucide-react.
    # Example values: 'Heart', 'Star', 'Gift', 'Crown', 'Diamond', 'Flower', 'Cat'.
    icon_name = models.CharField(
        max_length=50,
        blank=True,
        default='Gift',
        help_text='lucide-react icon name (e.g., Heart, Star, Crown, Diamond)'
    )
    icon_color = models.CharField(
        max_length=20,
        blank=True,
        default='#FFD700',
        help_text='Hex color for the lucide icon (e.g., #FF0080 for hearts)'
    )
    coin_value = models.IntegerField(default=1, help_text='Cost in coins to send this gift')
    rarity = models.CharField(max_length=20, choices=RARITY_CHOICES, default='common')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='special')
    is_active = models.BooleanField(default=True, help_text='Whether this gift is available for sending')
    sort_order = models.IntegerField(default=0, help_text='Display order in gift selector')
    xp_reward = models.IntegerField(default=0, help_text='XP reward for sender')
    
    # Animation settings
    animation_type = models.CharField(max_length=50, blank=True, help_text='Animation type (e.g., particle, bounce, pulse)')
    animation_duration = models.FloatField(default=1.0, help_text='Animation duration in seconds')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sort_order', 'coin_value', 'name']
        indexes = [
            models.Index(fields=['is_active', 'sort_order']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['rarity']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.coin_value} coins)"


class GiftTransaction(models.Model):
    """Records when a user sends a gift to another user"""
    
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gifts_sent')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gifts_received')
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE, related_name='transactions')
    reel = models.ForeignKey('api.Reel', on_delete=models.SET_NULL, null=True, blank=True, related_name='gifts_received', help_text='The reel this gift was sent on')
    
    quantity = models.IntegerField(default=1, help_text='Number of gifts sent (combo)')
    total_coins = models.IntegerField(help_text='Total coins spent')
    
    # Gamification
    is_combo = models.BooleanField(default=False, help_text='Whether this was part of a combo')
    combo_multiplier = models.FloatField(default=1.0, help_text='Multiplier for combo gifts')
    
    # Social features
    message = models.TextField(blank=True, help_text='Optional message with the gift')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sender', '-created_at']),
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['gift', '-created_at']),
            models.Index(fields=['reel', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.sender.username} sent {self.quantity}x {self.gift.name} to {self.recipient.username}"


class GiftCombo(models.Model):
    """Tracks gift combos for gamification"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gift_combos')
    reel = models.ForeignKey('api.Reel', on_delete=models.CASCADE, related_name='gift_combos')
    
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE)
    combo_count = models.IntegerField(default=1, help_text='Number of gifts in combo')
    total_coins = models.IntegerField(help_text='Total coins spent in combo')
    
    started_at = models.DateTimeField(auto_now_add=True)
    last_gift_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, help_text='Whether combo can still be added to')
    
    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', '-started_at']),
            models.Index(fields=['reel', '-started_at']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.combo_count}x {self.gift.name} combo"


class UserGiftStats(models.Model):
    """Statistics for a user's gifting activity"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='gift_stats')
    
    # Sending stats
    total_gifts_sent = models.IntegerField(default=0)
    total_coins_sent = models.IntegerField(default=0)
    unique_recipients = models.IntegerField(default=0, help_text='Number of different users they gifted')
    
    # Receiving stats
    total_gifts_received = models.IntegerField(default=0)
    total_coins_received = models.IntegerField(default=0)
    unique_senders = models.IntegerField(default=0, help_text='Number of different users who gifted them')
    
    # Favorite gift
    favorite_gift_sent = models.ForeignKey(Gift, on_delete=models.SET_NULL, null=True, blank=True, related_name='favorite_senders')
    favorite_gift_received = models.ForeignKey(Gift, on_delete=models.SET_NULL, null=True, blank=True, related_name='favorite_receivers')
    
    # Achievements
    highest_combo = models.IntegerField(default=0, help_text='Highest combo achieved')
    total_combos = models.IntegerField(default=0)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'User Gift Stats'
    
    def __str__(self):
        return f"Gift stats for {self.user.username}"


class WinnerGiftPackage(models.Model):
    """Configuration for winner gift packages (data or cash)"""

    GIFT_TYPE_CHOICES = [
        ('data', 'Data Gift (MB)'),
        ('cash', 'Cash Gift (ETB)'),
    ]

    WINNER_TYPE_CHOICES = [
        ('daily', 'Daily Winner'),
        ('weekly', 'Weekly Winner'),
        ('monthly', 'Monthly Winner'),
        ('grand', 'Grand Winner'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('crm', 'CRM (Data Gift)'),
        ('telebirr_b2c', 'Telebirr B2C (Cash Gift)'),
    ]

    winner_type = models.CharField(max_length=20, choices=WINNER_TYPE_CHOICES, unique=True)
    gift_type = models.CharField(max_length=20, choices=GIFT_TYPE_CHOICES)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text='Amount in ETB or MB')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Winner Gift Package'
        verbose_name_plural = 'Winner Gift Packages'

    def __str__(self):
        return f'{self.get_winner_type_display()} - {self.get_gift_type_display()} ({self.amount})'


class WinnerGiftTransaction(models.Model):
    """Track winner gift distributions (Telebirr B2C cash or CRM data gifts).

    STATUS_CHOICES mirrors B2CPaymentTransaction/WithdrawalRequest: a
    Telebirr B2C payout only ever reaches 'processing' when this row is
    created by api/views/crm.py -- it is moved to 'success'/'failed' by
    telebirr_b2c_webhook once Telebirr itself confirms the payout, never by
    the initiating request. Master marks this 'success' immediately on a
    successful B2C *initiation*, which is the exact bug this project's B2C
    payout work (api/views/wallet.py::request_withdrawal,
    api/views/direct_debit.py::telebirr_b2c_webhook) was built to avoid.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped (Not Telebirr User)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    winner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='winner_gifts')
    winner_type = models.CharField(max_length=20)  # daily, weekly, monthly, grand
    gift_package = models.ForeignKey(WinnerGiftPackage, on_delete=models.PROTECT, null=True, blank=True)

    # Which competition this prize was won in. Nullable because rows predating
    # the prize-management work belong to no recorded campaign, and inventing
    # one for them would misreport what was paid and when.
    campaign = models.ForeignKey(
        'api.Campaign',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prize_deliveries',
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20)

    # Telebirr B2C specific
    receiver_msisdn = models.CharField(max_length=20, blank=True)
    originator_conversation_id = models.CharField(max_length=100, blank=True)
    conversation_id = models.CharField(max_length=100, blank=True)
    telebirr_transaction_id = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)

    # What stops a winner being paid twice.
    #
    # The database enforces it rather than the code remembering to: one prize
    # per winner, per tier, per campaign, as a UNIQUE column. Two callers
    # racing to award the same prize -- a retried bulk payout, an admin
    # pressing send while the scheduled job runs -- both build the same key
    # and the second INSERT is refused by Postgres, not by a check that might
    # have read stale state a millisecond earlier.
    #
    # Nullable because existing rows have no key and a UNIQUE column permits
    # many NULLs; they are simply outside the guarantee, which is honest.
    idempotency_key = models.CharField(max_length=200, unique=True, null=True, blank=True)

    #: Delivery attempts made. A retry increments this rather than creating a
    #: second row, so "paid once, tried four times" stays distinguishable
    #: from "paid four times".
    attempt_count = models.PositiveIntegerField(default=0)

    #: When the prize must be delivered by, from the competition's close --
    #: 10 days for Weekly and Monthly, 20 for the Grand Final.
    deadline_at = models.DateTimeField(null=True, blank=True)

    #: When it actually reached the winner. Set only by a confirmed delivery,
    #: never by initiating one: a Telebirr payout is not delivered until the
    #: B2C webhook says so.
    delivered_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Winner Gift Transaction'
        verbose_name_plural = 'Winner Gift Transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['winner', '-created_at']),
            models.Index(fields=['winner_type', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['originator_conversation_id']),
            models.Index(fields=['campaign', 'winner_type']),
            models.Index(fields=['status', 'deadline_at']),
        ]

    def __str__(self):
        return f'{self.winner.username} - {self.winner_type} gift ({self.status})'

    @property
    def is_settled(self):
        """Delivered, or deliberately not being delivered.

        A settled prize is never re-sent. Everything that could pay a winner
        checks this first.
        """
        return self.status in ('success', 'skipped')

    @property
    def is_overdue(self):
        """Past its delivery deadline and still not delivered."""
        if self.deadline_at is None or self.status == 'success':
            return False
        return timezone.now() > self.deadline_at

    @property
    def is_owed(self):
        """Won, and the winner still does not have it.

        True for a skipped prize as well as a pending one. A prize this
        system cannot deliver is still a debt to the person who won it --
        treating 'we could not send it' as closed is how a winner ends up
        owed something nobody is looking for.
        """
        return self.status != 'success'

    def mark_skipped(self, reason=''):
        """Not being delivered by this system, and why.

        Distinct from failed: failing means the attempt went wrong and
        retrying might work, skipping means there is no route at all -- most
        often a cash prize for somebody with no Telebirr account. The row
        exists so the debt stays visible and somebody can settle it another
        way, which is the whole difference between this and dropping the
        winner from the list.
        """
        self.status = 'skipped'
        self.error_message = reason
        self.save(update_fields=['status', 'error_message', 'updated_at'])

    def mark_success(self, telebirr_transaction_id=''):
        # Read before the write: only a genuine transition should notify.
        # This method is reached from a retry and from a provider callback
        # that may arrive more than once, and neither should tell the winner
        # their prize arrived a second time.
        was_already_delivered = self.status == 'success'

        self.status = 'success'
        if telebirr_transaction_id:
            self.telebirr_transaction_id = telebirr_transaction_id
        self.delivered_at = timezone.now()
        self.save(
            update_fields=[
                'status',
                'telebirr_transaction_id',
                'delivered_at',
                'updated_at',
            ]
        )

        if not was_already_delivered:
            self._notify_delivered()

    def _notify_delivered(self):
        """Tell the winner their prize has actually arrived.

        Best-effort: notify_system swallows its own errors, because a prize
        that has been paid must stay marked as paid whatever happens here.
        """
        from api.services.notifications import notify_system

        if self.payment_method == 'crm':
            what = 'Your data prize has been added to your line.'
        else:
            what = f'Your {self.amount} ETB prize has been paid out.'

        notify_system(self.winner, 'prize_delivered', what)

    def mark_failed(self, error_message=''):
        self.status = 'failed'
        self.error_message = error_message
        self.save(update_fields=['status', 'error_message', 'updated_at'])
