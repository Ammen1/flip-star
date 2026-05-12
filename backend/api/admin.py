from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.db.models import Count, Sum, Q, Avg
from django.urls import path
from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta
from .models import UserProfile, Reel, Comment, CommentLike, CommentReply, SavedPost, Vote, Quest, UserQuest, Subscription, NotificationPreference, Competition, Winner, Follow, Report, Notification
from .models_campaign import Campaign, CampaignEntry, CampaignVote, CampaignWinner, CampaignNotification
from .models_campaign_extended import (
    CampaignScoringConfig, CampaignTheme, PostScore, UserCampaignStats, Leaderboard, LeaderboardEntry,
    WinnerSelection, SelectedWinner, CampaignBadge, GamificationActivity, JudgeScore, PublicVote, GrandFinalist
)
from .models_legal import LegalDocument, LegalDocumentVersion, UserLegalAcceptance
from .models_gift import Gift, GiftTransaction, GiftCombo, UserGiftStats
from .models_wallet import WalletConfig, WithdrawalRequest
from .admin_subscription import *

# Custom Admin Site Configuration
class SelfieStarAdminSite(admin.AdminSite):
    site_header = 'Selfie Star Admin Panel'
    site_title = 'Selfie Star Admin'
    index_title = 'Platform Management Dashboard'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('analytics/', self.admin_view(self.analytics_view), name='analytics'),
        ]
        return custom_urls + urls
    
    def analytics_view(self, request):
        # Platform Analytics
        total_users = User.objects.count()
        active_users_30d = User.objects.filter(last_login__gte=timezone.now() - timedelta(days=30)).count()
        total_reels = Reel.objects.count()
        total_votes = Vote.objects.count()
        total_comments = Comment.objects.count()
        total_follows = Follow.objects.count()
        
        # Engagement metrics
        avg_votes_per_reel = Vote.objects.values('reel').annotate(count=Count('id')).aggregate(avg=Avg('count'))['avg'] or 0
        avg_comments_per_reel = Comment.objects.values('reel').annotate(count=Count('id')).aggregate(avg=Avg('count'))['avg'] or 0
        
        # Top users
        top_creators = User.objects.annotate(
            reel_count=Count('reels'),
            vote_count=Count('reels__reel_votes')
        ).order_by('-vote_count')[:10]
        
        # Recent activity
        recent_reels = Reel.objects.select_related('user').order_by('-created_at')[:10]
        recent_users = User.objects.order_by('-date_joined')[:10]
        
        # Subscription stats
        subscription_stats = Subscription.objects.values('plan').annotate(count=Count('id'))
        
        context = {
            'total_users': total_users,
            'active_users_30d': active_users_30d,
            'total_reels': total_reels,
            'total_votes': total_votes,
            'total_comments': total_comments,
            'total_follows': total_follows,
            'avg_votes_per_reel': round(avg_votes_per_reel, 2),
            'avg_comments_per_reel': round(avg_comments_per_reel, 2),
            'top_creators': top_creators,
            'recent_reels': recent_reels,
            'recent_users': recent_users,
            'subscription_stats': subscription_stats,
            'title': 'Platform Analytics',
        }
        return render(request, 'admin/analytics.html', context)

admin_site = SelfieStarAdminSite(name='selfiestar_admin')

# Enhanced User Admin
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ['profile_photo', 'avatar', 'bio', 'xp', 'level', 'streak', 'language']
    readonly_fields = ['xp', 'level', 'streak']

class CustomUserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = ['username', 'email', 'get_level', 'get_xp', 'get_followers', 'get_reels_count', 'is_active', 'date_joined']
    list_filter = ['is_active', 'is_staff', 'date_joined', 'last_login']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    actions = ['activate_users', 'deactivate_users', 'upgrade_to_pro', 'reset_streak']
    
    def get_level(self, obj):
        return obj.profile.level if hasattr(obj, 'profile') else 'N/A'
    get_level.short_description = 'Level'
    get_level.admin_order_field = 'profile__level'
    
    def get_xp(self, obj):
        return obj.profile.xp if hasattr(obj, 'profile') else 'N/A'
    get_xp.short_description = 'XP'
    get_xp.admin_order_field = 'profile__xp'
    
    def get_followers(self, obj):
        return obj.followers.count()
    get_followers.short_description = 'Followers'
    
    def get_reels_count(self, obj):
        return obj.reels.count()
    get_reels_count.short_description = 'Reels'
    
    def activate_users(self, request, queryset):
        queryset.update(is_active=True)
    activate_users.short_description = 'Activate selected users'
    
    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_users.short_description = 'Deactivate selected users'
    
    def upgrade_to_pro(self, request, queryset):
        for user in queryset:
            subscription, created = Subscription.objects.get_or_create(user=user)
            subscription.plan = 'pro'
            subscription.expires_at = timezone.now() + timedelta(days=30)
            subscription.save()
    upgrade_to_pro.short_description = 'Upgrade to Pro (30 days)'
    
    def reset_streak(self, request, queryset):
        for user in queryset:
            if hasattr(user, 'profile'):
                user.profile.streak = 0
                user.profile.save()
    reset_streak.short_description = 'Reset streak to 0'

@admin.register(Report, site=admin_site)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'report_type', 'status', 'reported_by', 'reported_user', 'created_at', 'get_actions_link']
    list_filter = ['status', 'report_type', 'created_at']
    search_fields = ['reported_by__username', 'reported_user__username', 'description']
    readonly_fields = ['created_at', 'updated_at', 'resolved_at']
    actions = ['mark_reviewing', 'mark_resolved', 'mark_dismissed']
    fieldsets = (
        ('Report Information', {
            'fields': ('reported_by', 'report_type', 'description', 'status')
        }),
        ('Target Information', {
            'fields': ('reported_user', 'reported_reel')
        }),
        ('Resolution', {
            'fields': ('reviewed_by', 'resolution_notes', 'resolved_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def mark_reviewing(self, request, queryset):
        queryset.update(status='reviewing', reviewed_by=request.user)
    mark_reviewing.short_description = 'Mark as Under Review'
    
    def mark_resolved(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='resolved', reviewed_by=request.user, resolved_at=timezone.now())
    mark_resolved.short_description = 'Mark as Resolved'
    
    def mark_dismissed(self, request, queryset):
        queryset.update(status='dismissed', reviewed_by=request.user)
    mark_dismissed.short_description = 'Mark as Dismissed'
    
    def get_actions_link(self, obj):
        return format_html('<a class="button" href="{}">View</a>', f'/admin/api/report/{obj.id}/change/')
    get_actions_link.short_description = 'Actions'

@admin.register(UserProfile, site=admin_site)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'level', 'xp', 'streak', 'get_followers', 'get_following', 'last_checkin', 'created_at']
    list_filter = ['level', 'language', 'created_at']
    search_fields = ['user__username', 'user__email', 'bio']
    readonly_fields = ['created_at', 'updated_at', 'get_profile_stats']
    fieldsets = (
        ('User Info', {'fields': ('user', 'profile_photo', 'avatar', 'bio')}),
        ('Gamification', {'fields': ('xp', 'level', 'streak', 'last_checkin')}),
        ('Settings', {'fields': ('language',)}),
        ('Statistics', {'fields': ('get_profile_stats',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )
    actions = ['add_xp_100', 'add_xp_500', 'level_up', 'reset_stats']
    
    def get_followers(self, obj):
        return obj.user.followers.count()
    get_followers.short_description = 'Followers'
    
    def get_following(self, obj):
        return obj.user.following.count()
    get_following.short_description = 'Following'
    
    def get_profile_stats(self, obj):
        reels = obj.user.reels.count()
        votes = Vote.objects.filter(reel__user=obj.user).count()
        comments = obj.user.comments.count()
        return format_html(
            '<strong>Reels:</strong> {} | <strong>Total Votes Received:</strong> {} | <strong>Comments Made:</strong> {}',
            reels, votes, comments
        )
    get_profile_stats.short_description = 'Profile Statistics'
    
    def add_xp_100(self, request, queryset):
        for profile in queryset:
            profile.xp += 100
            profile.save()
    add_xp_100.short_description = 'Add 100 XP'
    
    def add_xp_500(self, request, queryset):
        for profile in queryset:
            profile.xp += 500
            profile.save()
    add_xp_500.short_description = 'Add 500 XP'
    
    def level_up(self, request, queryset):
        for profile in queryset:
            profile.level += 1
            profile.save()
    level_up.short_description = 'Level up (+1)'
    
    def reset_stats(self, request, queryset):
        queryset.update(xp=0, level=1, streak=0)
    reset_stats.short_description = 'Reset all stats'

@admin.register(Reel, site=admin_site)
class ReelAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'get_thumbnail', 'get_caption_preview', 'votes', 'get_comments_count', 'get_saves_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'caption', 'hashtags']
    readonly_fields = ['votes', 'created_at', 'get_engagement_stats', 'get_thumbnail']
    fieldsets = (
        ('Content', {'fields': ('user', 'image', 'media', 'get_thumbnail', 'caption', 'hashtags')}),
        ('Engagement', {'fields': ('votes', 'get_engagement_stats')}),
        ('Metadata', {'fields': ('created_at',)}),
    )
    actions = ['feature_reels', 'delete_with_moderation', 'boost_votes']
    date_hierarchy = 'created_at'
    
    def get_thumbnail(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" style="object-fit: cover; border-radius: 8px;" />', obj.image.url)
        return 'No image'
    get_thumbnail.short_description = 'Preview'
    
    def get_caption_preview(self, obj):
        return obj.caption[:50] + '...' if len(obj.caption) > 50 else obj.caption
    get_caption_preview.short_description = 'Caption'
    
    def get_comments_count(self, obj):
        return obj.comments.count()
    get_comments_count.short_description = 'Comments'
    
    def get_saves_count(self, obj):
        return obj.saved_by.count()
    get_saves_count.short_description = 'Saves'
    
    def get_engagement_stats(self, obj):
        comments = obj.comments.count()
        saves = obj.saved_by.count()
        engagement_rate = ((obj.votes + comments + saves) / max(obj.user.followers.count(), 1)) * 100
        return format_html(
            '<strong>Votes:</strong> {} | <strong>Comments:</strong> {} | <strong>Saves:</strong> {} | <strong>Engagement Rate:</strong> {:.2f}%',
            obj.votes, comments, saves, engagement_rate
        )
    get_engagement_stats.short_description = 'Engagement Statistics'
    
    def feature_reels(self, request, queryset):
        pass
    feature_reels.short_description = 'Feature selected reels'
    
    def delete_with_moderation(self, request, queryset):
        queryset.delete()
    delete_with_moderation.short_description = 'Delete (moderation)'
    
    def boost_votes(self, request, queryset):
        for reel in queryset:
            reel.votes += 10
            reel.save()
    boost_votes.short_description = 'Boost votes (+10)'

@admin.register(Comment, site=admin_site)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'reel', 'get_text_preview', 'get_likes_count', 'get_replies_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'text']
    readonly_fields = ['created_at', 'get_likes_count', 'get_replies_count']
    actions = ['delete_spam_comments', 'approve_comments']
    date_hierarchy = 'created_at'
    
    def get_text_preview(self, obj):
        return obj.text[:60] + '...' if len(obj.text) > 60 else obj.text
    get_text_preview.short_description = 'Comment'
    
    def get_likes_count(self, obj):
        return obj.comment_likes.count()
    get_likes_count.short_description = 'Likes'
    
    def get_replies_count(self, obj):
        return obj.replies.count()
    get_replies_count.short_description = 'Replies'
    
    def delete_spam_comments(self, request, queryset):
        queryset.delete()
    delete_spam_comments.short_description = 'Delete as spam'
    
    def approve_comments(self, request, queryset):
        pass
    approve_comments.short_description = 'Approve comments'

@admin.register(Vote, site=admin_site)
class VoteAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'reel', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username']
    date_hierarchy = 'created_at'

@admin.register(Quest, site=admin_site)
class QuestAdmin(admin.ModelAdmin):
    list_display = ['title', 'xp_reward', 'is_active', 'get_completion_count', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['title', 'description']
    actions = ['activate_quests', 'deactivate_quests', 'duplicate_quest']
    
    def get_completion_count(self, obj):
        return obj.userquest_set.filter(completed=True).count()
    get_completion_count.short_description = 'Completions'
    
    def activate_quests(self, request, queryset):
        queryset.update(is_active=True)
    activate_quests.short_description = 'Activate quests'
    
    def deactivate_quests(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_quests.short_description = 'Deactivate quests'
    
    def duplicate_quest(self, request, queryset):
        for quest in queryset:
            quest.pk = None
            quest.title = f"{quest.title} (Copy)"
            quest.save()
    duplicate_quest.short_description = 'Duplicate quest'

@admin.register(UserQuest, site=admin_site)
class UserQuestAdmin(admin.ModelAdmin):
    list_display = ['user', 'quest', 'completed', 'completed_at']
    list_filter = ['completed', 'completed_at']
    search_fields = ['user__username', 'quest__title']
    actions = ['mark_completed', 'mark_incomplete']
    
    def mark_completed(self, request, queryset):
        queryset.update(completed=True, completed_at=timezone.now())
    mark_completed.short_description = 'Mark as completed'
    
    def mark_incomplete(self, request, queryset):
        queryset.update(completed=False, completed_at=None)
    mark_incomplete.short_description = 'Mark as incomplete'

@admin.register(Subscription, site=admin_site)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'started_at', 'expires_at', 'is_active']
    list_filter = ['plan', 'started_at']
    search_fields = ['user__username']
    actions = ['upgrade_to_pro', 'upgrade_to_premium', 'extend_subscription']
    
    def is_active(self, obj):
        if obj.expires_at:
            return obj.expires_at > timezone.now()
        return obj.plan == 'free'
    is_active.boolean = True
    is_active.short_description = 'Active'
    
    def upgrade_to_pro(self, request, queryset):
        queryset.update(plan='pro', expires_at=timezone.now() + timedelta(days=30))
    upgrade_to_pro.short_description = 'Upgrade to Pro (30 days)'
    
    def upgrade_to_premium(self, request, queryset):
        queryset.update(plan='premium', expires_at=timezone.now() + timedelta(days=30))
    upgrade_to_premium.short_description = 'Upgrade to Premium (30 days)'
    
    def extend_subscription(self, request, queryset):
        for sub in queryset:
            if sub.expires_at:
                sub.expires_at += timedelta(days=30)
            else:
                sub.expires_at = timezone.now() + timedelta(days=30)
            sub.save()
    extend_subscription.short_description = 'Extend by 30 days'

@admin.register(NotificationPreference, site=admin_site)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'email_notifications', 'push_notifications', 'sms_notifications', 'phone']
    list_filter = ['email_notifications', 'push_notifications', 'sms_notifications']
    search_fields = ['user__username', 'phone']

@admin.register(Competition, site=admin_site)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ['title', 'start_date', 'end_date', 'is_active', 'get_participants', 'created_at']
    list_filter = ['is_active', 'start_date', 'end_date']
    search_fields = ['title', 'description']
    actions = ['activate_competitions', 'deactivate_competitions', 'announce_winners']
    date_hierarchy = 'start_date'
    
    def get_participants(self, obj):
        return obj.winners.count()
    get_participants.short_description = 'Winners'
    
    def activate_competitions(self, request, queryset):
        queryset.update(is_active=True)
    activate_competitions.short_description = 'Activate competitions'
    
    def deactivate_competitions(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_competitions.short_description = 'Deactivate competitions'
    
    def announce_winners(self, request, queryset):
        pass
    announce_winners.short_description = 'Announce winners'

@admin.register(Winner, site=admin_site)
class WinnerAdmin(admin.ModelAdmin):
    list_display = ['user', 'competition', 'reel', 'votes_received', 'prize_claimed', 'announced_at']
    list_filter = ['prize_claimed', 'competition', 'announced_at']
    search_fields = ['user__username', 'competition__title']
    actions = ['mark_prize_claimed', 'mark_prize_unclaimed']
    
    def mark_prize_claimed(self, request, queryset):
        queryset.update(prize_claimed=True)
    mark_prize_claimed.short_description = 'Mark prize as claimed'
    
    def mark_prize_unclaimed(self, request, queryset):
        queryset.update(prize_claimed=False)
    mark_prize_unclaimed.short_description = 'Mark prize as unclaimed'

@admin.register(Follow, site=admin_site)
class FollowAdmin(admin.ModelAdmin):
    list_display = ['follower', 'following', 'created_at']
    list_filter = ['created_at']
    search_fields = ['follower__username', 'following__username']
    date_hierarchy = 'created_at'

@admin.register(CommentLike, site=admin_site)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ['user', 'comment', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username']
    date_hierarchy = 'created_at'

@admin.register(CommentReply, site=admin_site)
class CommentReplyAdmin(admin.ModelAdmin):
    list_display = ['user', 'comment', 'get_text_preview', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'text']
    date_hierarchy = 'created_at'
    
    def get_text_preview(self, obj):
        return obj.text[:60] + '...' if len(obj.text) > 60 else obj.text
    get_text_preview.short_description = 'Reply'

@admin.register(SavedPost, site=admin_site)
class SavedPostAdmin(admin.ModelAdmin):
    list_display = ['user', 'reel', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username']
    date_hierarchy = 'created_at'

@admin.register(Campaign, site=admin_site)
class CampaignAdmin(admin.ModelAdmin):
    pass

@admin.register(CampaignEntry, site=admin_site)
class CampaignEntryAdmin(admin.ModelAdmin):
    pass

@admin.register(CampaignVote, site=admin_site)
class CampaignVoteAdmin(admin.ModelAdmin):
    pass

@admin.register(CampaignWinner, site=admin_site)
class CampaignWinnerAdmin(admin.ModelAdmin):
    pass

@admin.register(CampaignNotification, site=admin_site)
class CampaignNotificationAdmin(admin.ModelAdmin):
    pass

@admin.register(Notification, site=admin_site)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'sender', 'notification_type', 'message', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['recipient__username', 'sender__username', 'message']
    readonly_fields = ['created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('recipient', 'sender', 'reel', 'comment')

# Campaign Extended Models
@admin.register(CampaignScoringConfig, site=admin_site)
class CampaignScoringConfigAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'get_campaign_type', 'daily_top_scorer_percentage', 'grand_judging_weight']
    search_fields = ['campaign__title']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_campaign_type(self, obj):
        return obj.campaign.campaign_type if obj.campaign else '-'
    get_campaign_type.short_description = 'Type'

@admin.register(CampaignTheme, site=admin_site)
class CampaignThemeAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'title', 'week_number', 'is_active', 'start_date', 'end_date']
    list_filter = ['is_active', 'campaign']
    search_fields = ['title', 'campaign__title']
    ordering = ['campaign', 'week_number']

@admin.register(PostScore, site=admin_site)
class PostScoreAdmin(admin.ModelAdmin):
    list_display = ['user', 'campaign', 'theme', 'moderation_status', 'total_score', 'created_at']
    list_filter = ['moderation_status', 'campaign', 'theme']
    search_fields = ['user__username', 'campaign__title']
    readonly_fields = ['total_score', 'created_at', 'updated_at']

@admin.register(UserCampaignStats, site=admin_site)
class UserCampaignStatsAdmin(admin.ModelAdmin):
    list_display = ['user', 'campaign', 'total_score', 'approved_posts', 'overall_rank', 'current_streak']
    list_filter = ['campaign']
    search_fields = ['user__username', 'campaign__title']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Leaderboard, site=admin_site)
class LeaderboardAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'period_type', 'period_start', 'period_end', 'is_current', 'is_finalized']
    list_filter = ['period_type', 'is_current', 'is_finalized', 'campaign']
    ordering = ['-period_start']

@admin.register(LeaderboardEntry, site=admin_site)
class LeaderboardEntryAdmin(admin.ModelAdmin):
    list_display = ['leaderboard', 'rank', 'user', 'score', 'posts_count']
    list_filter = ['leaderboard']
    search_fields = ['user__username']
    ordering = ['leaderboard', 'rank']

@admin.register(WinnerSelection, site=admin_site)
class WinnerSelectionAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'selection_type', 'is_finalized', 'finalized_at', 'finalized_by']
    list_filter = ['selection_type', 'is_finalized', 'campaign']
    ordering = ['-created_at']

@admin.register(SelectedWinner, site=admin_site)
class SelectedWinnerAdmin(admin.ModelAdmin):
    list_display = ['selection', 'rank', 'user', 'final_score', 'selection_method', 'prize_claimed']
    list_filter = ['selection_method', 'prize_claimed']
    search_fields = ['user__username']
    ordering = ['selection', 'rank']

@admin.register(CampaignBadge, site=admin_site)
class CampaignBadgeAdmin(admin.ModelAdmin):
    list_display = ['user', 'campaign', 'badge_type', 'title', 'earned_at']
    list_filter = ['badge_type', 'campaign']
    search_fields = ['user__username', 'title']
    ordering = ['-earned_at']

# Legal Documents
@admin.register(LegalDocument, site=admin_site)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'document_type', 'version', 'status', 'effective_date', 'requires_acceptance']
    list_filter = ['document_type', 'status', 'requires_acceptance']
    search_fields = ['title', 'content']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-updated_at']

@admin.register(LegalDocumentVersion, site=admin_site)
class LegalDocumentVersionAdmin(admin.ModelAdmin):
    list_display = ['document', 'version', 'created_by', 'created_at']
    list_filter = ['document']
    ordering = ['-created_at']

@admin.register(UserLegalAcceptance, site=admin_site)
class UserLegalAcceptanceAdmin(admin.ModelAdmin):
    list_display = ['user', 'document', 'version_accepted', 'accepted_at', 'ip_address']
    list_filter = ['document', 'accepted_at']
    search_fields = ['user__username', 'user__email']
    ordering = ['-accepted_at']

# Gift System
@admin.register(Gift, site=admin_site)
class GiftAdmin(admin.ModelAdmin):
    list_display = ['name', 'coin_value', 'rarity', 'category', 'is_active', 'sort_order']
    list_filter = ['rarity', 'category', 'is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['sort_order', 'coin_value', 'name']

@admin.register(GiftTransaction, site=admin_site)
class GiftTransactionAdmin(admin.ModelAdmin):
    list_display = ['sender', 'recipient', 'gift', 'quantity', 'total_coins', 'is_combo', 'created_at']
    list_filter = ['is_combo', 'gift__category', 'created_at']
    search_fields = ['sender__username', 'recipient__username', 'gift__name']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

@admin.register(GiftCombo, site=admin_site)
class GiftComboAdmin(admin.ModelAdmin):
    list_display = ['user', 'gift', 'combo_count', 'total_coins', 'is_active', 'started_at']
    list_filter = ['is_active', 'gift__category']
    search_fields = ['user__username', 'gift__name']
    readonly_fields = ['started_at', 'last_gift_at']
    ordering = ['-started_at']

@admin.register(UserGiftStats, site=admin_site)
class UserGiftStatsAdmin(admin.ModelAdmin):
    list_display = ['user', 'total_gifts_sent', 'total_coins_sent', 'total_gifts_received', 'total_coins_received', 'highest_combo']
    search_fields = ['user__username']
    readonly_fields = ['updated_at']
    ordering = ['-total_coins_received']

# ============ WALLET / COIN ECONOMY ADMIN ============
@admin.register(WalletConfig, site=admin_site)
class WalletConfigAdmin(admin.ModelAdmin):
    """Singleton config — only one row should exist (id=1)."""
    list_display = ['id', 'welcome_bonus', 'coins_per_birr', 'withdrawal_min_coins',
                    'withdrawal_fee_percent', 'withdrawal_enabled', 'updated_at']
    fieldsets = (
        ('Earning Rewards', {
            'fields': (
                'welcome_bonus',
                ('daily_login_day1', 'daily_login_day2', 'daily_login_day3', 'daily_login_day4'),
                ('daily_login_day5', 'daily_login_day6', 'daily_login_day7'),
                'daily_post_bonus', 'campaign_join_reward',
                ('receive_like_reward', 'receive_like_daily_cap'),
                ('quality_comment_reward', 'quality_comment_daily_cap'),
                'profile_complete_reward', 'referral_reward', 'campaign_winner_reward',
            )
        }),
        ('Action Costs', {
            'fields': (
                ('cost_post_create', 'cost_like', 'cost_comment'),
                ('cost_join_campaign', 'cost_extra_campaign_entry'),
                ('cost_boost_2hr', 'cost_boost_24hr'),
            )
        }),
        ('Thresholds', {
            'fields': ('min_balance_to_post', 'min_balance_to_join_campaign')
        }),
        ('Withdrawal (Coin → Birr)', {
            'fields': (
                'withdrawal_enabled',
                ('withdrawal_min_coins', 'withdrawal_max_coins_per_request'),
                ('coins_per_birr', 'withdrawal_fee_percent'),
                'withdrawal_processing_days',
            )
        }),
        ('Gifting Policy', {
            'fields': (
                ('earned_coins_giftable', 'purchased_coins_giftable'),
                ('earned_coins_withdrawable', 'purchased_coins_withdrawable'),
            )
        }),
        ('Expiry', {'fields': ('earned_coins_expire_days',)}),
        ('Audit', {'fields': ('updated_at', 'updated_by'), 'classes': ('collapse',)}),
    )
    readonly_fields = ['updated_at']

    def has_add_permission(self, request):
        # Allow only one row
        return not WalletConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WithdrawalRequest, site=admin_site)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'coin_amount', 'net_birr', 'payout_method',
                    'status', 'created_at']
    list_filter = ['status', 'payout_method', 'created_at']
    search_fields = ['user__username', 'user__email', 'payout_account', 'payout_reference']
    readonly_fields = ['gross_birr', 'fee_birr', 'net_birr', 'conversion_rate',
                       'created_at', 'reviewed_at', 'completed_at']
    ordering = ['-created_at']
    fieldsets = (
        ('User & Amount', {
            'fields': ('user', 'coin_amount', 'conversion_rate',
                       ('gross_birr', 'fee_birr', 'net_birr'))
        }),
        ('Payout Details', {
            'fields': ('payout_method', 'payout_account', 'payout_account_name', 'payout_reference')
        }),
        ('Status & Review', {
            'fields': ('status', 'admin_notes', 'rejection_reason',
                       'reviewed_at', 'reviewed_by', 'completed_at')
        }),
        ('Timestamps', {'fields': ('created_at',), 'classes': ('collapse',)}),
    )


# Register User with custom admin
admin_site.register(User, CustomUserAdmin)
