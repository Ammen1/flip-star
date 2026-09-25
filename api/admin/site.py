from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.db.models import Avg, Count
from django.shortcuts import render
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html

from api.models import (
    Category,
    Comment,
    CommentLike,
    CommentReply,
    Competition,
    Follow,
    Notification,
    NotificationPreference,
    Organization,
    Quest,
    Reel,
    Report,
    SavedPost,
    Subscription,
    UserProfile,
    UserQuest,
    Vote,
    Winner,
)
from api.models.campaign import (
    Campaign,
    CampaignEntry,
    CampaignNotification,
    CampaignVote,
    CampaignWinner,
)
from api.models.campaign_extended import (
    CampaignBadge,
    CampaignScoringConfig,
    CampaignTheme,
    Leaderboard,
    LeaderboardEntry,
    PostScore,
    SelectedWinner,
    UserCampaignStats,
    WinnerSelection,
)
from api.models.crm import CRMGiftPackage, CRMGiftTransaction
from api.models.gift import (
    Gift,
    GiftCombo,
    GiftTransaction,
    UserGiftStats,
    WinnerGiftPackage,
    WinnerGiftTransaction,
)
from api.models.legal import LegalDocument, LegalDocumentVersion, UserLegalAcceptance
from api.models.support import SupportRequest
from api.models.wallet import WalletConfig, WithdrawalRequest


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
        active_users_30d = User.objects.filter(
            last_login__gte=timezone.now() - timedelta(days=30)
        ).count()
        total_reels = Reel.objects.count()
        total_votes = Vote.objects.count()
        total_comments = Comment.objects.count()
        total_follows = Follow.objects.count()

        # Engagement metrics
        avg_votes_per_reel = (
            Vote.objects.values('reel')
            .annotate(count=Count('id'))
            .aggregate(avg=Avg('count'))['avg']
            or 0
        )
        avg_comments_per_reel = (
            Comment.objects.values('reel')
            .annotate(count=Count('id'))
            .aggregate(avg=Avg('count'))['avg']
            or 0
        )

        # Top users
        top_creators = User.objects.annotate(
            reel_count=Count('reels'), vote_count=Count('reels__reel_votes')
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
    fields = [
        'realm',
        'role',
        'organization',
        'profile_photo',
        'avatar',
        'bio',
        'xp',
        'level',
        'streak',
        'language',
    ]
    readonly_fields = ['xp', 'level', 'streak']

    # Invalid realm/role/organization combinations are refused here as well as
    # in the API. UserProfile.clean() carries the rules, and the inline's
    # ModelForm calls it -- so an administrator setting a MEMBER as a maker, or
    # an ORGANIZATION account with no organization, gets a field error instead
    # of a row the database will later reject.
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form._validate_unique = True
        return formset


class CustomUserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = [
        'username',
        'email',
        'get_realm',
        'get_role',
        'get_organization',
        'get_level',
        'get_xp',
        'get_followers',
        'get_reels_count',
        'is_active',
        'date_joined',
    ]
    # Realm and role first: they decide what an account can do, so they are
    # what an administrator most often needs to slice by.
    list_filter = [
        'profile__realm',
        'profile__role',
        'profile__organization',
        'is_active',
        'is_staff',
        'date_joined',
        'last_login',
    ]
    search_fields = ['username', 'email', 'first_name', 'last_name', 'profile__organization__name']

    def get_realm(self, obj):
        return obj.profile.realm if hasattr(obj, 'profile') else 'N/A'

    get_realm.short_description = 'Realm'
    get_realm.admin_order_field = 'profile__realm'

    def get_role(self, obj):
        # Shown as an em dash rather than blank so "no role" reads as a
        # deliberate state instead of missing data.
        role = obj.profile.role if hasattr(obj, 'profile') else None
        return role or '—'

    get_role.short_description = 'Role'
    get_role.admin_order_field = 'profile__role'

    def get_organization(self, obj):
        organization = obj.profile.organization if hasattr(obj, 'profile') else None
        return organization.name if organization else '—'

    get_organization.short_description = 'Organization'
    get_organization.admin_order_field = 'profile__organization__name'
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
    list_display = [
        'id',
        'report_type',
        'status',
        'reported_by',
        'reported_user',
        'created_at',
        'get_actions_link',
    ]
    list_filter = ['status', 'report_type', 'created_at']
    search_fields = ['reported_by__username', 'reported_user__username', 'description']
    readonly_fields = ['created_at', 'updated_at', 'resolved_at']
    actions = ['mark_reviewing', 'mark_resolved', 'mark_dismissed']
    fieldsets = (
        ('Report Information', {'fields': ('reported_by', 'report_type', 'description', 'status')}),
        ('Target Information', {'fields': ('reported_user', 'reported_reel')}),
        ('Resolution', {'fields': ('reviewed_by', 'resolution_notes', 'resolved_at')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
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
        return format_html(
            '<a class="button" href="{}">View</a>', f'/admin/api/report/{obj.id}/change/'
        )

    get_actions_link.short_description = 'Actions'


@admin.register(UserProfile, site=admin_site)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'level',
        'xp',
        'streak',
        'get_followers',
        'get_following',
        'last_checkin',
        'created_at',
    ]
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
            reels,
            votes,
            comments,
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
    list_display = [
        'id',
        'user',
        'get_thumbnail',
        'get_caption_preview',
        'votes',
        'get_comments_count',
        'get_saves_count',
        'created_at',
    ]
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
        # A video's picture is its thumbnail; processed files are stored as
        # full URLs, which served_url returns as they are (signed if private).
        from api.services.media_pipeline import served_url

        url = served_url(obj.thumbnail) or served_url(obj.image)
        if url:
            return format_html(
                '<img src="{}" width="100" height="100" style="object-fit: cover; border-radius: 8px;" />',
                url,
            )
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
        engagement_rate = (
            (obj.votes + comments + saves) / max(obj.user.followers.count(), 1)
        ) * 100
        return format_html(
            '<strong>Votes:</strong> {} | <strong>Comments:</strong> {} | <strong>Saves:</strong> {} | <strong>Engagement Rate:</strong> {:.2f}%',
            obj.votes,
            comments,
            saves,
            engagement_rate,
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
    list_display = [
        'id',
        'user',
        'reel',
        'get_text_preview',
        'get_likes_count',
        'get_replies_count',
        'created_at',
    ]
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
            quest.title = f'{quest.title} (Copy)'
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
    list_display = [
        'user',
        'email_notifications',
        'push_notifications',
        'sms_notifications',
        'phone',
    ]
    list_filter = ['email_notifications', 'push_notifications', 'sms_notifications']
    search_fields = ['user__username', 'phone']


@admin.register(Competition, site=admin_site)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = [
        'title',
        'start_date',
        'end_date',
        'is_active',
        'get_participants',
        'created_at',
    ]
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
    list_display = [
        'user',
        'competition',
        'reel',
        'votes_received',
        'prize_claimed',
        'announced_at',
    ]
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
        return (
            super().get_queryset(request).select_related('recipient', 'sender', 'reel', 'comment')
        )


# Campaign Extended Models
@admin.register(CampaignScoringConfig, site=admin_site)
class CampaignScoringConfigAdmin(admin.ModelAdmin):
    list_display = [
        'campaign',
        'get_campaign_type',
        'daily_top_scorer_percentage',
        'grand_judging_weight',
    ]
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
    list_display = [
        'user',
        'campaign',
        'total_score',
        'approved_posts',
        'overall_rank',
        'current_streak',
    ]
    list_filter = ['campaign']
    search_fields = ['user__username', 'campaign__title']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Leaderboard, site=admin_site)
class LeaderboardAdmin(admin.ModelAdmin):
    list_display = [
        'campaign',
        'period_type',
        'period_start',
        'period_end',
        'is_current',
        'is_finalized',
    ]
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
    list_display = [
        'title',
        'document_type',
        'version',
        'status',
        'effective_date',
        'requires_acceptance',
    ]
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
    list_display = [
        'sender',
        'recipient',
        'gift',
        'quantity',
        'total_coins',
        'is_combo',
        'created_at',
    ]
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
    list_display = [
        'user',
        'total_gifts_sent',
        'total_coins_sent',
        'total_gifts_received',
        'total_coins_received',
        'highest_combo',
    ]
    search_fields = ['user__username']
    readonly_fields = ['updated_at']
    ordering = ['-total_coins_received']


# ============ CONTENT CATEGORIES ============
@admin.register(Category, site=admin_site)
class CategoryAdmin(admin.ModelAdmin):
    """Admin-managed content categories for posts"""

    list_display = ['name', 'slug', 'icon', 'order', 'is_active', 'reel_count', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'slug', 'description']
    list_editable = ['order', 'is_active']
    readonly_fields = ['created_at', 'updated_at', 'reel_count']
    prepopulated_fields = {'slug': ('name',)}

    def reel_count(self, obj):
        return obj.reels.count()

    reel_count.short_description = 'Posts'


# ============ WALLET / COIN ECONOMY ADMIN ============
@admin.register(WalletConfig, site=admin_site)
class WalletConfigAdmin(admin.ModelAdmin):
    """Singleton config — only one row should exist (id=1)."""

    list_display = [
        'id',
        'welcome_bonus',
        'coins_per_birr',
        'withdrawal_min_coins',
        'withdrawal_fee_percent',
        'withdrawal_enabled',
        'updated_at',
    ]
    fieldsets = (
        (
            'Earning Rewards',
            {
                'fields': (
                    'welcome_bonus',
                    (
                        'daily_login_day1',
                        'daily_login_day2',
                        'daily_login_day3',
                        'daily_login_day4',
                    ),
                    ('daily_login_day5', 'daily_login_day6', 'daily_login_day7'),
                    'daily_post_bonus',
                    'campaign_join_reward',
                    ('receive_like_reward', 'receive_like_daily_cap'),
                    ('quality_comment_reward', 'quality_comment_daily_cap'),
                    'profile_complete_reward',
                    'referral_reward',
                    'campaign_winner_reward',
                )
            },
        ),
        (
            'Action Costs (campaign posts only)',
            {
                'description': 'Coins deducted from the user (earned + purchased) when they perform these actions on a campaign post. Set to 0 to make free.',
                'fields': (
                    ('cost_like', 'cost_comment', 'cost_share', 'cost_gift'),
                    ('cost_post_create', 'cost_post_create_long_video'),
                    ('cost_join_campaign', 'cost_extra_campaign_entry'),
                    ('cost_boost_2hr', 'cost_boost_24hr'),
                ),
            },
        ),
        (
            'Action Costs (non-campaign posts)',
            {
                'description': 'Coins deducted from the user (earned + purchased) when they perform these actions on a non-campaign post. Set to 0 to make free.',
                'fields': (
                    (
                        'cost_like_non_campaign',
                        'cost_comment_non_campaign',
                        'cost_share_non_campaign',
                        'cost_gift_non_campaign',
                    ),
                    ('cost_post_create_non_campaign', 'cost_post_create_long_video_non_campaign'),
                ),
            },
        ),
        ('Thresholds', {'fields': ('min_balance_to_post', 'min_balance_to_join_campaign')}),
        (
            'Withdrawal (Coin → Birr)',
            {
                'fields': (
                    'withdrawal_enabled',
                    ('withdrawal_min_coins', 'withdrawal_max_coins_per_request'),
                    ('coins_per_birr', 'withdrawal_fee_percent'),
                    'withdrawal_processing_days',
                )
            },
        ),
        (
            'Gifting Policy',
            {
                'fields': (
                    ('earned_coins_giftable', 'purchased_coins_giftable'),
                    ('earned_coins_withdrawable', 'purchased_coins_withdrawable'),
                )
            },
        ),
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
    list_display = [
        'id',
        'user',
        'coin_amount',
        'net_birr',
        'payout_method',
        'status',
        'created_at',
    ]
    list_filter = ['status', 'payout_method', 'created_at']
    search_fields = ['user__username', 'user__email', 'payout_account', 'payout_reference']
    readonly_fields = [
        'gross_birr',
        'fee_birr',
        'net_birr',
        'conversion_rate',
        'created_at',
        'reviewed_at',
        'completed_at',
    ]
    ordering = ['-created_at']
    fieldsets = (
        (
            'User & Amount',
            {
                'fields': (
                    'user',
                    'coin_amount',
                    'conversion_rate',
                    ('gross_birr', 'fee_birr', 'net_birr'),
                )
            },
        ),
        (
            'Payout Details',
            {
                'fields': (
                    'payout_method',
                    'payout_account',
                    'payout_account_name',
                    'payout_reference',
                )
            },
        ),
        (
            'Status & Review',
            {
                'fields': (
                    'status',
                    'admin_notes',
                    'rejection_reason',
                    'reviewed_at',
                    'reviewed_by',
                    'completed_at',
                )
            },
        ),
        ('Timestamps', {'fields': ('created_at',), 'classes': ('collapse',)}),
    )


# ============ SUPPORT REQUESTS ============
@admin.register(SupportRequest, site=admin_site)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'category', 'status', 'subject', 'created_at', 'handled_by']
    list_filter = ['status', 'category', 'created_at']
    search_fields = ['user__username', 'user__email', 'subject', 'message']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    fieldsets = (
        ('Request Information', {'fields': ('user', 'category', 'subject', 'message', 'status')}),
        ('Admin Response', {'fields': ('admin_response', 'handled_by')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    actions = ['mark_received', 'mark_pending', 'mark_in_progress', 'mark_solved', 'mark_closed']

    def mark_received(self, request, queryset):
        queryset.update(status='received')

    mark_received.short_description = 'Mark as Received'

    def mark_pending(self, request, queryset):
        queryset.update(status='pending')

    mark_pending.short_description = 'Mark as Pending'

    def mark_in_progress(self, request, queryset):
        queryset.update(status='in_progress', handled_by=request.user)

    mark_in_progress.short_description = 'Mark as In Progress'

    def mark_solved(self, request, queryset):
        queryset.update(status='solved', handled_by=request.user)

    mark_solved.short_description = 'Mark as Solved'

    def mark_closed(self, request, queryset):
        queryset.update(status='closed', handled_by=request.user)

    mark_closed.short_description = 'Mark as Closed'


# Register User with custom admin
admin_site.register(User, CustomUserAdmin)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Organizations, and who belongs to them.

    member_count is annotated rather than counted per row so the changelist
    stays one query regardless of how many organizations exist.
    """

    list_display = ['name', 'status', 'member_count', 'campaign_count', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _members=Count('members', distinct=True),
                _campaigns=Count('campaigns', distinct=True),
            )
        )

    def member_count(self, obj):
        return obj._members

    member_count.short_description = 'Members'
    member_count.admin_order_field = '_members'

    def campaign_count(self, obj):
        return obj._campaigns

    campaign_count.short_description = 'Campaigns'
    campaign_count.admin_order_field = '_campaigns'


# ============================================================================
# PRIZE MANAGEMENT AND DELIVERY
# ============================================================================
#
# What a prize is owed, whether it has been delivered, and what to do about
# it when it has not. None of these models had an admin registration at all,
# so the only way to answer "has the Grand Final winner been paid?" was a
# database query.


class PrizeStatusFilter(admin.SimpleListFilter):
    """The four questions an operator actually asks of this table."""

    title = 'delivery state'
    parameter_name = 'delivery_state'

    def lookups(self, request, model_admin):
        return [
            ('owed', 'Still owed (anything undelivered)'),
            ('pending', 'Awaiting delivery'),
            ('failed', 'Failed'),
            ('skipped', 'Undeliverable (no Telebirr account)'),
            ('success', 'Delivered'),
            ('overdue', 'Overdue (past deadline)'),
        ]

    def queryset(self, request, queryset):
        from api.services.prize_delivery import (
            failed_deliveries,
            overdue_deliveries,
            owed_deliveries,
            pending_deliveries,
            skipped_deliveries,
            successful_deliveries,
        )

        views = {
            'owed': owed_deliveries,
            'pending': pending_deliveries,
            'failed': failed_deliveries,
            'skipped': skipped_deliveries,
            'success': successful_deliveries,
            'overdue': overdue_deliveries,
        }
        view = views.get(self.value())
        if view is None:
            return queryset
        return queryset.filter(pk__in=view().values('pk'))


@admin.register(WinnerGiftPackage, site=admin_site)
class WinnerGiftPackageAdmin(admin.ModelAdmin):
    """What each tier pays.

    Read-only on the figures: the amounts are contractual and come from
    api/services/prize_structure.py, which writes over this row on every
    award. Editing them here would not change what a winner is paid, so the
    fields are not offered as if it would.
    """

    list_display = ['winner_type', 'gift_type', 'payment_method', 'amount', 'is_active']
    list_filter = ['gift_type', 'payment_method', 'is_active']
    readonly_fields = [
        'winner_type',
        'gift_type',
        'payment_method',
        'amount',
        'created_at',
        'updated_at',
    ]

    def has_add_permission(self, request):
        return False


@admin.register(WinnerGiftTransaction, site=admin_site)
class WinnerGiftTransactionAdmin(admin.ModelAdmin):
    """Every prize owed, and where its delivery got to."""

    list_display = [
        'winner',
        'winner_type',
        'amount',
        'payment_method',
        'delivery_state',
        'attempt_count',
        'deadline_display',
        'delivered_at',
    ]
    list_filter = [PrizeStatusFilter, 'winner_type', 'payment_method', 'status', 'created_at']
    search_fields = [
        'winner__username',
        'receiver_msisdn',
        'telebirr_transaction_id',
        'conversation_id',
        'originator_conversation_id',
        'idempotency_key',
    ]
    readonly_fields = [
        'id',
        'idempotency_key',
        'originator_conversation_id',
        'conversation_id',
        'telebirr_transaction_id',
        'attempt_count',
        'delivered_at',
        'created_at',
        'updated_at',
    ]
    list_select_related = ['winner', 'campaign']
    actions = ['retry_failed_deliveries']

    def delivery_state(self, obj):
        """Status, with overdue called out -- a 'processing' prize three days
        past its deadline is not the same as one sent this morning."""
        colours = {
            'success': 'green',
            'failed': 'red',
            'processing': 'orange',
            'pending': 'gray',
            'skipped': 'gray',
        }
        label = obj.get_status_display()
        if obj.is_overdue:
            return format_html(
                '<span style="color:red;font-weight:bold">{} (OVERDUE)</span>', label
            )
        return format_html(
            '<span style="color:{}">{}</span>', colours.get(obj.status, 'black'), label
        )

    delivery_state.short_description = 'Delivery'

    def deadline_display(self, obj):
        if not obj.deadline_at:
            return '--'
        return obj.deadline_at.strftime('%Y-%m-%d')

    deadline_display.short_description = 'Deliver by'
    deadline_display.admin_order_field = 'deadline_at'

    @admin.action(description='Retry failed deliveries')
    def retry_failed_deliveries(self, request, queryset):
        """Re-attempt on the same rows.

        Goes through the delivery service, so a prize that is already
        delivered or in flight is refused rather than paid again -- selecting
        the whole page and pressing retry cannot double-pay anybody.
        """
        from api.services.prize_delivery import retry

        retried = skipped = failed = 0
        for prize in queryset:
            ok, message = retry(prize)
            if ok:
                retried += 1
            elif 'already' in message:
                skipped += 1
            else:
                failed += 1

        self.message_user(
            request,
            f'{retried} re-attempted, {failed} failed again, '
            f'{skipped} skipped (already delivered or in flight).',
        )


@admin.register(CRMGiftPackage, site=admin_site)
class CRMGiftPackageAdmin(admin.ModelAdmin):
    """The data bundles available to provision, by OfferingId."""

    list_display = ['name', 'offering_id', 'charge_amount', 'trigger_condition', 'is_active']
    list_filter = ['is_active', 'trigger_condition']
    search_fields = ['name', 'offering_id']


@admin.register(CRMGiftTransaction, site=admin_site)
class CRMGiftTransactionAdmin(admin.ModelAdmin):
    """Data provisioning attempts, successful and otherwise."""

    list_display = [
        'phone_number',
        'offering_id',
        'status',
        'trigger_source',
        'campaign_id',
        'created_at',
        'completed_at',
    ]
    list_filter = ['status', 'trigger_source', 'created_at']
    search_fields = ['phone_number', 'transaction_id', 'offering_id', 'user__username']
    readonly_fields = ['transaction_id', 'created_at', 'completed_at']
    list_select_related = ['user', 'package']
