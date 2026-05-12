from rest_framework import serializers
from .models_subscription import (
    SubscriptionTier, Subscription, SubscriptionPayment, SubscriptionHistory,
    OnevasWebhookLog, PromoCode, UserPromoUsage, SubscriptionFeatureUsage,
    ExpiredSubscriptionAction, TrialPopupLog, SubscriptionCoinTransaction, AdminRole, SubscriptionReport
)


class SubscriptionTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionTier
        fields = '__all__'


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    tier = SubscriptionTierSerializer(read_only=True)
    
    class Meta:
        model = SubscriptionPlan
        fields = '__all__'


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPayment
        fields = '__all__'


class SubscriptionHistorySerializer(serializers.ModelSerializer):
    tier = SubscriptionTierSerializer(read_only=True)
    
    class Meta:
        model = SubscriptionHistory
        fields = '__all__'


class OnevasWebhookLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnevasWebhookLog
        fields = '__all__'


class PromoCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromoCode
        fields = '__all__'


class UserPromoUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPromoUsage
        fields = '__all__'


class SubscriptionFeatureUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionFeatureUsage
        fields = '__all__'


class ExpiredSubscriptionActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpiredSubscriptionAction
        fields = '__all__'


class TrialPopupLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrialPopupLog
        fields = '__all__'


class CoinTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoinTransaction
        fields = '__all__'


class AdminRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminRole
        fields = '__all__'


class SubscriptionReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionReport
        fields = '__all__'
