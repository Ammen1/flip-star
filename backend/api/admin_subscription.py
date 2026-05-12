from django.contrib import admin
from .models_subscription import (
    SubscriptionTier, SubscriptionPlan, SubscriptionPayment, SubscriptionHistory,
    OnevasWebhookLog, PromoCode, UserPromoUsage, SubscriptionFeatureUsage,
    ExpiredSubscriptionAction, TrialPopupLog, SubscriptionCoinTransaction, AdminRole, SubscriptionReport
)


@admin.register(SubscriptionTier)
class SubscriptionTierAdmin(admin.ModelAdmin):
    list_display = ['name', 'duration_type', 'price_etb', 'onevas_code', 'is_active', 'sort_order']
    list_filter = ['duration_type', 'is_active']
    search_fields = ['name', 'slug', 'onevas_code']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'slug', 'description', 'duration_type', 'duration_days')
        }),
        ('Pricing', {
            'fields': ('price_etb', 'price_coins')
        }),
        ('Onevas Configuration', {
            'fields': ('onevas_code', 'spid', 'service_id', 'product_id', 'application_key', 'short_code')
        }),
        ('Features', {
            'fields': ('features', 'privileges')
        }),
        ('Limits', {
            'fields': ('max_posts_per_day', 'max_reels_per_day', 'max_campaigns_per_month',
                      'max_likes_per_day', 'max_comments_per_day', 'max_follows_per_day')
        }),
        ('Special Features', {
            'fields': ('priority_support', 'custom_themes', 'analytics_access', 'api_access',
                      'ad_free', 'watermark_free', 'hd_quality', 'download_videos')
        }),
        ('Settings', {
            'fields': ('is_active', 'sort_order')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['user', 'tier', 'status', 'duration_type', 'start_date', 'end_date', 'auto_renew']
    list_filter = ['status', 'duration_type', 'auto_renew']
    search_fields = ['user__username', 'onevas_subscription_id', 'onevas_phone_number']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['user', 'tier']


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ['user', 'subscription', 'amount', 'currency', 'status', 'payment_method', 'created_at']
    list_filter = ['status', 'payment_method', 'duration_type']
    search_fields = ['user__username', 'onevas_transaction_id']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['subscription', 'user']


@admin.register(SubscriptionHistory)
class SubscriptionHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'tier', 'created_at']
    list_filter = ['action']
    search_fields = ['user__username']
    readonly_fields = ['created_at']
    raw_id_fields = ['user', 'subscription', 'tier']


@admin.register(OnevasWebhookLog)
class OnevasWebhookLogAdmin(admin.ModelAdmin):
    list_display = ['webhook_type', 'processed', 'response_status', 'retry_count', 'created_at']
    list_filter = ['webhook_type', 'processed', 'response_status']
    search_fields = ['error_message']
    readonly_fields = ['created_at']


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'discount_type', 'discount_value', 'current_uses', 'max_uses', 'is_active']
    list_filter = ['discount_type', 'is_active']
    search_fields = ['code', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(UserPromoUsage)
class UserPromoUsageAdmin(admin.ModelAdmin):
    list_display = ['user', 'promo_code', 'subscription', 'used_at']
    search_fields = ['user__username', 'promo_code__code']
    raw_id_fields = ['user', 'promo_code', 'subscription']


@admin.register(SubscriptionFeatureUsage)
class SubscriptionFeatureUsageAdmin(admin.ModelAdmin):
    list_display = ['user', 'feature_name', 'usage_count', 'period_start', 'period_end']
    search_fields = ['user__username', 'feature_name']
    raw_id_fields = ['user', 'subscription']


@admin.register(ExpiredSubscriptionAction)
class ExpiredSubscriptionActionAdmin(admin.ModelAdmin):
    list_display = ['user', 'action_type', 'action_status', 'scheduled_at', 'executed_at']
    list_filter = ['action_type', 'action_status']
    search_fields = ['user__username']
    readonly_fields = ['created_at']
    raw_id_fields = ['user', 'subscription']


@admin.register(TrialPopupLog)
class TrialPopupLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'trigger_action', 'trigger_screen', 'user_action', 'created_at']
    list_filter = ['trigger_action', 'user_action']
    search_fields = ['user__username']
    readonly_fields = ['created_at']
    raw_id_fields = ['user']


@admin.register(SubscriptionCoinTransaction)
class SubscriptionCoinTransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'transaction_type', 'amount', 'balance_after', 'created_at']
    list_filter = ['transaction_type']
    search_fields = ['user__username', 'reference_id']
    readonly_fields = ['created_at']
    raw_id_fields = ['user']


@admin.register(AdminRole)
class AdminRoleAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active']
    search_fields = ['user__username']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['user']


@admin.register(SubscriptionReport)
class SubscriptionReportAdmin(admin.ModelAdmin):
    list_display = ['report_type', 'title', 'date_from', 'date_to', 'generated_by', 'created_at']
    list_filter = ['report_type']
    search_fields = ['title']
    readonly_fields = ['created_at']
    raw_id_fields = ['generated_by']
