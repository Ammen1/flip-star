from rest_framework import serializers
from .models_gift import Gift, GiftTransaction, GiftCombo, UserGiftStats
from django.contrib.auth.models import User


class GiftSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    animated_image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Gift
        fields = [
            'id', 'name', 'description', 'image', 'image_url', 'animated_image',
            'animated_image_url', 'icon_name', 'icon_color',
            'coin_value', 'rarity', 'category', 'is_active',
            'sort_order', 'xp_reward', 'animation_type', 'animation_duration',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None
    
    def get_animated_image_url(self, obj):
        if obj.animated_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.animated_image.url)
            return obj.animated_image.url
        return None


class GiftCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating gifts (admin only)"""
    class Meta:
        model = Gift
        fields = [
            'name', 'description', 'image', 'animated_image',
            'icon_name', 'icon_color',
            'coin_value', 'rarity', 'category', 'is_active', 'sort_order', 'xp_reward',
            'animation_type', 'animation_duration'
        ]


class GiftUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating gifts (admin only)"""
    class Meta:
        model = Gift
        fields = [
            'name', 'description', 'image', 'animated_image',
            'icon_name', 'icon_color',
            'coin_value', 'rarity', 'category', 'is_active', 'sort_order', 'xp_reward',
            'animation_type', 'animation_duration'
        ]


class GiftTransactionSerializer(serializers.ModelSerializer):
    gift_details = GiftSerializer(source='gift', read_only=True)
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    recipient_username = serializers.CharField(source='recipient.username', read_only=True)
    sender_profile_photo = serializers.SerializerMethodField()
    recipient_profile_photo = serializers.SerializerMethodField()
    
    class Meta:
        model = GiftTransaction
        fields = [
            'id', 'sender', 'sender_username', 'sender_profile_photo',
            'recipient', 'recipient_username', 'recipient_profile_photo',
            'gift', 'gift_details', 'reel', 'quantity', 'total_coins',
            'is_combo', 'combo_multiplier', 'message', 'created_at'
        ]
        read_only_fields = ['created_at', 'total_coins']
    
    def get_sender_profile_photo(self, obj):
        if obj.sender.profile.profile_photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.sender.profile.profile_photo.url)
            return obj.sender.profile.profile_photo.url
        return None
    
    def get_recipient_profile_photo(self, obj):
        if obj.recipient.profile.profile_photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.recipient.profile.profile_photo.url)
            return obj.recipient.profile.profile_photo.url
        return None


class SendGiftSerializer(serializers.Serializer):
    """Serializer for sending a gift"""
    gift_id = serializers.IntegerField()
    recipient_id = serializers.IntegerField()
    reel_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(default=1, min_value=1, max_value=999)
    message = serializers.CharField(required=False, allow_blank=True, max_length=500)


class GiftComboSerializer(serializers.ModelSerializer):
    gift_details = GiftSerializer(source='gift', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = GiftCombo
        fields = [
            'id', 'user', 'username', 'reel', 'gift', 'gift_details',
            'combo_count', 'total_coins', 'started_at', 'last_gift_at', 'is_active'
        ]
        read_only_fields = ['started_at', 'last_gift_at']


class UserGiftStatsSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    favorite_gift_sent_details = GiftSerializer(source='favorite_gift_sent', read_only=True)
    favorite_gift_received_details = GiftSerializer(source='favorite_gift_received', read_only=True)
    
    class Meta:
        model = UserGiftStats
        fields = [
            'user', 'username', 'total_gifts_sent', 'total_coins_sent',
            'unique_recipients', 'total_gifts_received', 'total_coins_received',
            'unique_senders', 'favorite_gift_sent', 'favorite_gift_sent_details',
            'favorite_gift_received', 'favorite_gift_received_details',
            'highest_combo', 'total_combos', 'updated_at'
        ]
        read_only_fields = ['updated_at']


class GiftLeaderboardSerializer(serializers.Serializer):
    """Serializer for gift leaderboard"""
    username = serializers.CharField()
    total_gifts_received = serializers.IntegerField()
    total_coins_received = serializers.IntegerField()
    rank = serializers.IntegerField()
