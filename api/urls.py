from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from api.views.boost import (
    calculate_boost_cost,
    cancel_boost_campaign,
    check_pacing_engine,
    create_boost_campaign,
    get_boost_campaign_detail,
    get_boost_config,
    get_eligible_boosts,
    get_user_boost_campaigns,
    pause_boost_campaign,
    record_boost_engagement,
    record_boost_impression,
    resume_boost_campaign,
)
from api.views.charging import (
    get_charging_analytics,
    get_charging_statistics,
    get_charging_transactions,
    initiate_on_demand_charging,
    purchase_coins_on_demand,
    search_charging_transactions,
)
from api.views.client_log import clear_pending_mandate, client_log
from api.views.core import (
    BlockViewSet,
    CompetitionViewSet,
    DraftViewSet,
    FollowViewSet,
    NotificationPreferenceViewSet,
    QuestViewSet,
    ReelViewSet,
    SubscriptionViewSet,
    UserProfileViewSet,
    UserSearchViewSet,
    WinnerViewSet,
    admin_moderate_report,
    admin_report_detail,
    admin_reports_list,
    admin_reports_stats,
    admin_undo_moderation_action,
    change_password,
    check_phone_account,
    create_post,
    create_report,
    delete_account,
    dev_create_subscription,
    download_data,
    forgot_password_confirm,
    forgot_password_phone_request,
    forgot_password_phone_verify,
    forgot_password_request,
    get_categories,
    get_notification_settings,
    get_privacy_settings,
    get_reels_by_hashtag,
    get_trending_hashtags,
    get_trending_reels,
    get_unread_notification_count,
    get_user_notifications,
    login,
    login_with_otp,
    login_with_phone,
    login_with_subscription_otp,
    mark_not_interested,
    mark_notifications_read,
    mark_single_notification_read,
    privacy_policy,
    register,
    register_with_phone,
    resend_subscription_otp,
    reset_password,
    search,
    send_login_otp,
    send_phone_otp,
    track_view,
    undo_not_interested,
    update_notification_settings,
    update_privacy_settings,
    verify_phone_otp,
)
from api.views.crm import (
    CRMGiftAuditLogViewSet,
    CRMGiftAwardViewSet,
    CRMGiftPackageViewSet,
    CRMGiftTransactionViewSet,
)
from api.views.crypto import (
    crypto_public_key,
    crypto_test_decrypt,
    crypto_test_encrypt,
    crypto_test_keypair,
)
from api.views.direct_debit import (
    activate_direct_debit_mandate,
    cancel_direct_debit_mandate,
    check_mandate_status,
    create_direct_debit_mandate,
    create_one_off_coin_purchase,
    create_one_off_subscription,
    initiate_b2c_payment,
    initiate_direct_debit,
    list_b2c_payments,
    list_user_mandates,
    query_mandate_from_telebirr,
    telebirr_b2c_webhook,
    telebirr_direct_debit_webhook,
)
from api.views.master_campaign import (
    generate_sub_campaigns,
    master_campaign_detail,
    master_campaign_list,
    master_campaign_participants,
    master_campaign_stats,
    test_generate_endpoint,
    update_generation_config,
)
from api.views.messaging import (
    conversation_messages,
    edit_or_delete_message,
    list_or_create_conversations,
    mark_conversation_read,
    search_users_for_dm,
    unread_dm_count,
)
from api.views.privacy import (
    get_consent_history,
    get_consent_status,
    get_eu_rights_summary,
    get_privacy_policy_summary,
    update_consent,
)
from api.views.push import push_public_key, push_subscribe, push_unsubscribe
from api.views.subscription import (
    AdminSubscriptionViewSet,
    CoinTransactionViewSet,
    SubscriptionTierViewSet,
    UserSubscriptionStatusView,
    check_superapp_subscription,
    telebirr_one_time_callback,
    telebirr_one_time_initiate,
    telebirr_one_time_query,
    telebirr_ussd_subscription_initiate,
    telebirr_ussd_subscription_status,
    telebirr_ussd_subscription_webhook,
    validate_subscription_token,
)
from api.views.subscription import (
    SubscriptionViewSet as NewSubscriptionViewSet,
)
from api.views.support import (
    admin_support_requests,
    admin_update_support_request,
    my_support_requests,
)
from api.views.timwe import timwe_sync_order_relation


@api_view(['GET', 'HEAD'])
@permission_classes([AllowAny])
def health_check(request):
    """Ultra-cheap liveness probe — does NOT touch the DB.

    Safe to call every 5-10 minutes from an external uptime monitor (e.g.
    cron-job.org, UptimeRobot) to keep Render's free-tier service warm.
    For full diagnostics including DB counts, hit /health/deep/ instead.
    """
    return Response({'status': 'ok'})


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check_deep(request):
    """Full diagnostic health check — DOES touch the DB. Don't use for keep-alive."""
    from django.conf import settings
    from django.contrib.auth.models import User

    from .models import Reel
    from .models.campaign import Campaign

    db_engine = settings.DATABASES['default']['ENGINE']
    db_name = settings.DATABASES['default'].get('NAME', 'unknown')
    db_host = settings.DATABASES['default'].get('HOST', 'localhost')

    user_count = User.objects.count()
    reel_count = Reel.objects.count()
    campaign_count = Campaign.objects.count()

    usernames = list(User.objects.values_list('username', flat=True)[:3])

    return Response(
        {
            'status': 'ok',
            'database': {
                'engine': db_engine,
                'name': db_name,
                'host': db_host[:30] + '...' if len(str(db_host)) > 30 else db_host,
            },
            'counts': {
                'users': user_count,
                'reels': reel_count,
                'campaigns': campaign_count,
            },
            'sample_usernames': usernames,
            'message': 'API is running',
        }
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def cleanup_broken_reels(request):
    """Delete all reels that don't have valid Cloudinary URLs, and clear broken campaign images"""

    from .models import Reel
    from .models.campaign import Campaign

    try:
        fixed_count = 0

        for reel in Reel.objects.all():
            image_name = reel.image.name if reel.image else ''
            media_name = reel.media.name if reel.media else ''

            image_ok = image_name.startswith('https://')
            media_ok = media_name.startswith('https://')

            changed = False
            if image_name and not image_ok:
                reel.image = None
                changed = True
            if media_name and not media_ok:
                reel.media = None
                changed = True

            if changed:
                reel.save()
                fixed_count += 1

        # Also clear broken campaign images (not https URLs)
        campaign_fixed = 0
        for campaign in Campaign.objects.all():
            img_name = campaign.image.name if campaign.image else ''
            if img_name and not img_name.startswith('https://'):
                campaign.image = None
                campaign.save()
                campaign_fixed += 1

        return Response(
            {
                'fixed_reels': fixed_count,
                'fixed_campaigns': campaign_fixed,
                'total_reels': Reel.objects.count(),
            }
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


from api.views.admin import (
    admin_analytics_export,
    admin_comment_delete,
    admin_comments_list,
    admin_dashboard_stats,
    admin_grant_admin,
    admin_log_security_event,
    admin_mark_all_security_events_read,
    admin_privilege_audit,
    admin_reel_boost,
    admin_reel_delete,
    admin_reel_detail,
    admin_reel_moderate,
    admin_reels_list,
    admin_resolve_security_event,
    admin_security_events,
    admin_security_stats,
    admin_subscription_upgrade,
    admin_user_delete,
    admin_user_detail,
    admin_user_logs,
    admin_user_role,
    admin_user_update,
    admin_users_list,
    admin_wipe_all_posts,
)
from api.views.campaign import (
    admin_announce_winners,
    admin_campaign_create,
    admin_campaign_delete,
    admin_campaign_entries,
    admin_campaign_update,
    admin_campaigns_list,
    user_campaign_detail,
    user_campaign_enter,
    user_campaign_vote,
    user_campaigns_list,
)
from api.views.campaign_admin import (
    admin_activate_theme,
    admin_campaign_analytics,
    admin_campaign_posts_pending,
    admin_campaign_theme_detail,
    admin_campaign_themes,
    admin_generate_leaderboard,
    admin_moderate_post,
    admin_select_winners,
    admin_update_post_scores,
    get_campaign_winners,
)
from api.views.campaign_admin import get_leaderboard as get_campaign_leaderboard
from api.views.campaign_user import (
    create_campaign_post,
    get_active_campaigns,
    get_campaign_detail_extended,
    get_campaign_feed,
    get_campaign_notifications,
    get_user_campaign_profile,
    global_leaderboard,
    update_consistency_scores,
    update_engagement_scores,
)
from api.views.coin_management import (
    campaign_coin_config,
    coin_config_audit,
    coin_usage_overview,
    organization_coin_config,
    organizations_coin_overview,
    platform_coin_limits,
    reward_transactions,
)
from api.views.contest import (
    admin_contest_dashboard,
    admin_judging_portal,
    anti_cheat_flags,
    boost_post,
    check_upload_eligibility,
    get_coin_balance,
    get_coin_packages,
    get_grand_finale,
    get_leaderboard,
    get_post_score,
    get_user_subscription,
    gift_creator,
    judge_post,
    purchase_coins,
    purchase_extra_entry,
    review_flag,
    send_gift,
    toggle_flash_challenge,
    upgrade_subscription,
    verify_age,
    verify_phone,
    vote_grand_finale,
)
from api.views.extended import (
    CommentReplyViewSet,
    CommentViewSet,
    ProfilePhotoViewSet,
    SavedPostViewSet,
)
from api.views.gamification import (
    check_in,
    claim_login_bonus,
    debug_gamification,
    get_gamification_status,
    get_gift_history,
    get_recent_activity,
    send_coin_gift,
)
from api.views.gift import (
    GiftTransactionViewSet,
    GiftViewSet,
    PublicGiftViewSet,
    UserGiftStatsViewSet,
)
from api.views.legal import (
    accept_legal_document,
    admin_legal_document_acceptances,
    admin_legal_document_archive,
    admin_legal_document_create,
    admin_legal_document_delete,
    admin_legal_document_detail,
    admin_legal_document_publish,
    admin_legal_document_update,
    admin_legal_documents_list,
    admin_legal_stats,
    get_all_legal_documents,
    get_legal_document,
    get_pending_acceptances,
    get_user_acceptances,
)
from api.views.organization_campaigns import (
    organization_campaign_analytics,
    organization_campaign_approve,
    organization_campaign_create,
    organization_campaign_delete,
    organization_campaign_detail,
    organization_campaign_leaderboard,
    organization_campaign_list,
    organization_campaign_posts,
    organization_campaign_reject,
    organization_campaign_submit,
    organization_campaign_update,
    organization_dashboard,
)
from api.views.organizations import (
    create_organization_admin,
    organization_campaigns,
    organization_detail,
    organization_list_create,
)
from api.views.reels import reels_following, reels_saved, reels_trending
from api.views.scoring import (
    admin_calculate_final_scores,
    admin_calculate_scores,
    admin_get_finalists,
    admin_qualify_finalists,
    admin_save_scores,
    admin_submit_judge_score,
    cast_vote,
    get_finalists_for_voting,
)
from api.views.scoring import admin_scoring_config as admin_scoring_config_full
from api.views.scoring import admin_update_scoring_config as admin_update_scoring_config_full
from api.views.scoring_config import get_scoring_config
from api.views.settings import (
    bulk_user_action,
    clear_system_logs,
    create_api_key,
    delete_api_key,
    get_admin_notifications,
    get_api_keys,
    get_database_stats,
    get_platform_performance,
    get_platform_settings,
    get_public_settings,
    get_security_overview,
    get_system_logs,
    mark_notification_read,
    send_platform_notification,
    toggle_api_key,
    update_platform_settings,
)
from api.views.sms_health import sms_health
from api.views.wallet import (
    admin_adjust_balance,
    admin_all_coin_transactions,
    admin_user_transactions,
    admin_user_wallet,
    admin_wallet_config,
    admin_withdrawal_action,
    admin_withdrawal_analytics,
    admin_withdrawals_list,
    cancel_withdrawal,
    my_withdrawals,
    public_wallet_config,
    reinvest_points,
    request_withdrawal,
    telebirr_auth,
    telebirr_callback,
    telebirr_initiate_payment,
    telebirr_query_order,
    telebirr_ussd_purchase,
    telebirr_ussd_webhook,
    wallet_summary,
    wallet_transactions,
    withdrawal_info,
)

router = DefaultRouter()
router.register(r'profile', UserProfileViewSet, basename='profile')
router.register(r'reels', ReelViewSet, basename='reel')
router.register(r'drafts', DraftViewSet, basename='draft')
router.register(r'quests', QuestViewSet, basename='quest')
router.register(r'subscription', SubscriptionViewSet, basename='subscription')
router.register(r'notifications', NotificationPreferenceViewSet, basename='notification')
router.register(r'competitions', CompetitionViewSet, basename='competition')
router.register(r'winners', WinnerViewSet, basename='winner')
router.register(r'follows', FollowViewSet, basename='follow')
router.register(r'blocks', BlockViewSet, basename='block')
router.register(r'user-search', UserSearchViewSet, basename='user-search')
router.register(r'comments', CommentViewSet, basename='comment')
router.register(r'comment-replies', CommentReplyViewSet, basename='comment-reply')
router.register(r'saved', SavedPostViewSet, basename='saved')
router.register(r'profile-photo', ProfilePhotoViewSet, basename='profile-photo')
router.register(r'admin/gifts', GiftViewSet, basename='admin-gift')
router.register(r'gifts', PublicGiftViewSet, basename='gift')
router.register(r'gift-transactions', GiftTransactionViewSet, basename='gift-transaction')
router.register(r'gift-stats', UserGiftStatsViewSet, basename='gift-stats')

from api.views.setup_admin import setup_admin

urlpatterns = [
    path('health/', health_check, name='health-check'),
    # SMS gateway state. Staff-only, and deliberately does not send a
    # test message -- see api/views/sms_health.py.
    path('admin/sms/health/', sms_health, name='sms-health'),
    path('health/deep/', health_check_deep, name='health-check-deep'),
    path('cleanup-reels/', cleanup_broken_reels, name='cleanup-reels'),
    path('auth/register/', register, name='auth-register'),
    path('auth/login/', login, name='auth-login'),
    path('auth/login-with-phone/', login_with_phone, name='auth-login-with-phone'),
    path('auth/reset-password/', reset_password, name='auth-reset-password'),
    path('auth/change-password/', change_password, name='auth-change-password'),
    path('auth/delete-account/', delete_account, name='auth-delete-account'),
    path('auth/privacy-policy/', privacy_policy, name='auth-privacy-policy'),
    path('privacy/consents/', get_consent_status, name='privacy-consents'),
    path('privacy/consents/update/', update_consent, name='privacy-consents-update'),
    path('privacy/consents/history/', get_consent_history, name='privacy-consents-history'),
    path('privacy/policy/summary/', get_privacy_policy_summary, name='privacy-policy-summary'),
    path('privacy/eu-rights/', get_eu_rights_summary, name='privacy-eu-rights'),
    path('auth/download-data/', download_data, name='auth-download-data'),
    path('client-log/', client_log, name='client-log'),
    path('client-log/clear-pending-mandate/', clear_pending_mandate, name='clear-pending-mandate'),
    path('auth/send-phone-otp/', send_phone_otp, name='auth-send-otp'),
    path('auth/verify-phone-otp/', verify_phone_otp, name='auth-verify-otp'),
    path('auth/register-with-phone/', register_with_phone, name='auth-register-phone'),
    path(
        'auth/login-with-subscription-otp/',
        login_with_subscription_otp,
        name='auth-login-subscription-otp',
    ),
    path(
        'auth/resend-subscription-otp/',
        resend_subscription_otp,
        name='auth-resend-subscription-otp',
    ),
    path('auth/send-login-otp/', send_login_otp, name='auth-send-login-otp'),
    path('auth/login-with-otp/', login_with_otp, name='auth-login-with-otp'),
    path('auth/check-phone-account/', check_phone_account, name='auth-check-phone-account'),
    path(
        'auth/dev-create-subscription/',
        dev_create_subscription,
        name='auth-dev-create-subscription',
    ),
    path('auth/forgot-password/', forgot_password_request, name='auth-forgot-password'),
    path(
        'auth/forgot-password/confirm/',
        forgot_password_confirm,
        name='auth-forgot-password-confirm',
    ),
    path(
        'auth/forgot-password-phone/',
        forgot_password_phone_request,
        name='auth-forgot-password-phone',
    ),
    path(
        'auth/forgot-password-phone/verify/',
        forgot_password_phone_verify,
        name='auth-forgot-password-phone-verify',
    ),
    path('setup-admin/', setup_admin, name='setup-admin'),
    path('posts/create/', create_post, name='create-post'),
    path('notifications/', get_user_notifications, name='user-notifications'),
    path(
        'notifications/unread-count/',
        get_unread_notification_count,
        name='notifications-unread-count',
    ),
    path('notifications/read/', mark_notifications_read, name='mark-notifications-read'),
    path(
        'notifications/<int:notification_id>/read/',
        mark_single_notification_read,
        name='notification-single-read',
    ),
    path('search/', search, name='search'),
    # Web Push (VAPID) endpoints
    path('push/public-key/', push_public_key, name='push-public-key'),
    path('crypto/public-key/', crypto_public_key, name='crypto-public-key'),
    # Test helpers, served only when settings.CRYPTO_TEST_ENDPOINTS_ENABLED
    # is true (404 otherwise). They do the client half of the encryption
    # server-side so Postman/curl can drive the encrypted endpoints -- which
    # is why they must stay off in production. See api/views/crypto.py.
    path('crypto/test/keypair/', crypto_test_keypair, name='crypto-test-keypair'),
    path('crypto/test/encrypt/', crypto_test_encrypt, name='crypto-test-encrypt'),
    path('crypto/test/decrypt/', crypto_test_decrypt, name='crypto-test-decrypt'),
    path('push/subscribe/', push_subscribe, name='push-subscribe'),
    path('push/unsubscribe/', push_unsubscribe, name='push-unsubscribe'),
    # Messaging endpoints
    path('messages/conversations/', list_or_create_conversations, name='dm-conversations'),
    path(
        'messages/conversations/<int:conversation_id>/messages/',
        conversation_messages,
        name='dm-conv-messages',
    ),
    path(
        'messages/conversations/<int:conversation_id>/read/',
        mark_conversation_read,
        name='dm-conv-read',
    ),
    path('messages/<int:message_id>/', edit_or_delete_message, name='dm-message'),
    path('messages/unread-count/', unread_dm_count, name='dm-unread-count'),
    path('messages/users/search/', search_users_for_dm, name='dm-user-search'),
    # Report endpoints
    path('reports/create/', create_report, name='create-report'),
    path('admin/reports/', admin_reports_list, name='admin-reports-list'),
    path('admin/reports/stats/', admin_reports_stats, name='admin-reports-stats'),
    path('admin/reports/<int:report_id>/', admin_report_detail, name='admin-report-detail'),
    path(
        'admin/reports/<int:report_id>/moderate/',
        admin_moderate_report,
        name='admin-report-moderate',
    ),
    path(
        'admin/moderation-actions/<int:action_id>/undo/',
        admin_undo_moderation_action,
        name='admin-undo-moderation-action',
    ),
    # Admin endpoints
    path('admin/dashboard/', admin_dashboard_stats, name='admin-dashboard'),
    path('admin/users/', admin_users_list, name='admin-users-list'),
    path('admin/users/<int:user_id>/', admin_user_detail, name='admin-user-detail'),
    path('admin/users/<int:user_id>/update/', admin_user_update, name='admin-user-update'),
    path('admin/users/<int:user_id>/delete/', admin_user_delete, name='admin-user-delete'),
    path('admin/users/<int:user_id>/admin-role/', admin_user_role, name='admin-user-role'),
    path('admin/users/<int:user_id>/logs/', admin_user_logs, name='admin-user-logs'),
    path('admin/users/<int:user_id>/grant-admin/', admin_grant_admin, name='admin-grant-admin'),
    path('admin/privilege-audit/', admin_privilege_audit, name='admin-privilege-audit'),
    path('admin/reels/', admin_reels_list, name='admin-reels-list'),
    path('admin/reels/<int:reel_id>/', admin_reel_detail, name='admin-reel-detail'),
    path('admin/reels/<int:reel_id>/moderate/', admin_reel_moderate, name='admin-reel-moderate'),
    path('admin/reels/<int:reel_id>/delete/', admin_reel_delete, name='admin-reel-delete'),
    path('admin/security-events/', admin_security_events, name='admin-security-events'),
    path('admin/security-events/log/', admin_log_security_event, name='admin-log-security-event'),
    path(
        'admin/security-events/<int:event_id>/resolve/',
        admin_resolve_security_event,
        name='admin-resolve-security-event',
    ),
    path(
        'admin/security-events/mark-all-read/',
        admin_mark_all_security_events_read,
        name='admin-mark-all-security-events-read',
    ),
    path('admin/security-stats/', admin_security_stats, name='admin-security-stats'),
    path('admin/reels/<int:reel_id>/boost/', admin_reel_boost, name='admin-reel-boost'),
    path(
        'admin/subscriptions/<int:user_id>/upgrade/',
        admin_subscription_upgrade,
        name='admin-subscription-upgrade',
    ),
    path('admin/comments/', admin_comments_list, name='admin-comments-list'),
    path(
        'admin/comments/<int:comment_id>/delete/', admin_comment_delete, name='admin-comment-delete'
    ),
    path('admin/analytics/export/', admin_analytics_export, name='admin-analytics-export'),
    path('admin/wipe-all-posts/', admin_wipe_all_posts, name='admin-wipe-all-posts'),
    # Settings & Configuration
    path('admin/settings/', get_platform_settings, name='admin-settings'),
    path('admin/settings/update/', update_platform_settings, name='admin-settings-update'),
    path('settings/public/', get_public_settings, name='public-settings'),
    # API Keys
    path('admin/api-keys/', get_api_keys, name='admin-api-keys'),
    path('admin/api-keys/create/', create_api_key, name='admin-api-key-create'),
    path('admin/api-keys/<int:key_id>/delete/', delete_api_key, name='admin-api-key-delete'),
    path('admin/api-keys/<int:key_id>/toggle/', toggle_api_key, name='admin-api-key-toggle'),
    # System Monitoring
    path('admin/logs/', get_system_logs, name='admin-logs'),
    path('admin/logs/clear/', clear_system_logs, name='admin-logs-clear'),
    path('admin/security/', get_security_overview, name='admin-security'),
    path('admin/performance/', get_platform_performance, name='admin-performance'),
    path('admin/database/', get_database_stats, name='admin-database'),
    # Notifications
    path('admin/notifications/', get_admin_notifications, name='admin-notifications'),
    path(
        'admin/notifications/<int:notification_id>/read/',
        mark_notification_read,
        name='admin-notification-read',
    ),
    path('admin/notifications/send/', send_platform_notification, name='admin-send-notification'),
    # Bulk Actions
    path('admin/users/bulk/', bulk_user_action, name='admin-bulk-action'),
    # Master Campaign Management (Admin)
    path('admin/master-campaigns/', master_campaign_list, name='admin-master-campaigns-list'),
    path(
        'admin/master-campaigns/<int:pk>/',
        master_campaign_detail,
        name='admin-master-campaign-detail',
    ),
    path(
        'admin/master-campaigns/<int:pk>/participants/',
        master_campaign_participants,
        name='admin-master-campaign-participants',
    ),
    path(
        'admin/master-campaigns/<int:pk>/stats/',
        master_campaign_stats,
        name='admin-master-campaign-stats',
    ),
    path(
        'admin/master-campaigns/<int:pk>/test/', test_generate_endpoint, name='admin-test-generate'
    ),
    path(
        'admin/master-campaigns/<int:pk>/generate/',
        generate_sub_campaigns,
        name='admin-generate-sub-campaigns',
    ),
    path(
        'admin/master-campaigns/<int:pk>/config/',
        update_generation_config,
        name='admin-update-generation-config',
    ),
    # Campaign Management (Admin)
    path('admin/campaigns/', admin_campaigns_list, name='admin-campaigns-list'),
    path('admin/campaigns/create/', admin_campaign_create, name='admin-campaign-create'),
    # Super Admin: organizations and their administrators. Platform-level,
    # gated on IsFlipstarUser -- an organization cannot create organizations or
    # appoint its own administrators.
    path('admin/organizations/', organization_list_create, name='admin-organization-list'),
    path(
        'admin/organizations/<int:organization_id>/',
        organization_detail,
        name='admin-organization-detail',
    ),
    path(
        'admin/organizations/<int:organization_id>/campaigns/',
        organization_campaigns,
        name='admin-organization-campaigns',
    ),
    path(
        'admin/organizations/<int:organization_id>/admins/',
        create_organization_admin,
        name='admin-organization-create-admin',
    ),
    # Organization-scoped campaign management. Separate from the admin
    # endpoints above, which are is_staff-only: every lookup below resolves
    # through visible_campaigns, so an id from another organization is not
    # found rather than merely refused.
    path(
        'organization/campaigns/',
        organization_campaign_list,
        name='organization-campaign-list',
    ),
    # Deliberately not under 'admin/': AdminPathGuardMiddleware refuses that
    # whole prefix to non-staff accounts, and an organization admin is not
    # staff. See organization_campaign_create for why the guard is left alone.
    path(
        'organization/campaigns/create/',
        organization_campaign_create,
        name='organization-campaign-create',
    ),
    path(
        'organization/campaigns/<int:campaign_id>/',
        organization_campaign_detail,
        name='organization-campaign-detail',
    ),
    path(
        'organization/campaigns/<int:campaign_id>/update/',
        organization_campaign_update,
        name='organization-campaign-update',
    ),
    path(
        'organization/campaigns/<int:campaign_id>/delete/',
        organization_campaign_delete,
        name='organization-campaign-delete',
    ),
    path(
        'organization/campaigns/<int:campaign_id>/submit/',
        organization_campaign_submit,
        name='organization-campaign-submit',
    ),
    path(
        'organization/campaigns/<int:campaign_id>/approve/',
        organization_campaign_approve,
        name='organization-campaign-approve',
    ),
    # ── Coin management ─────────────────────────────────────────────────────
    # One surface, two audiences. Super Admin names an organization; an
    # organization admin never does -- theirs comes from their account and an
    # organization id in the request is not read.
    path('admin/coin-limits/', platform_coin_limits, name='platform-coin-limits'),
    path(
        'admin/coin-management/organizations/',
        organizations_coin_overview,
        name='coin-organizations-overview',
    ),
    path(
        'admin/organizations/<int:organization_id>/coin-config/',
        organization_coin_config,
        name='admin-organization-coin-config',
    ),
    path('organization/coin-config/', organization_coin_config, name='organization-coin-config'),
    path(
        'campaigns/<int:campaign_id>/coin-config/',
        campaign_coin_config,
        name='campaign-coin-config',
    ),
    path('coin-usage/', coin_usage_overview, name='coin-usage-overview'),
    path('coin-rewards/', reward_transactions, name='coin-reward-transactions'),
    path('coin-audit/', coin_config_audit, name='coin-config-audit'),
    path('organization/dashboard/', organization_dashboard, name='organization-dashboard'),
    path(
        'organization/campaigns/<int:campaign_id>/analytics/',
        organization_campaign_analytics,
        name='organization-campaign-analytics',
    ),
    path(
        'organization/campaigns/<int:campaign_id>/leaderboard/',
        organization_campaign_leaderboard,
        name='organization-campaign-leaderboard',
    ),
    path(
        'organization/campaigns/<int:campaign_id>/posts/',
        organization_campaign_posts,
        name='organization-campaign-posts',
    ),
    path(
        'organization/campaigns/<int:campaign_id>/reject/',
        organization_campaign_reject,
        name='organization-campaign-reject',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/update/',
        admin_campaign_update,
        name='admin-campaign-update',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/delete/',
        admin_campaign_delete,
        name='admin-campaign-delete',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/entries/',
        admin_campaign_entries,
        name='admin-campaign-entries',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/announce-winners/',
        admin_announce_winners,
        name='admin-announce-winners',
    ),
    # Campaign Extended Admin
    path(
        'admin/campaigns/<int:campaign_id>/themes/',
        admin_campaign_themes,
        name='admin-campaign-themes',
    ),
    path(
        'admin/campaigns/themes/<int:theme_id>/',
        admin_campaign_theme_detail,
        name='admin-campaign-theme-detail',
    ),
    path(
        'admin/campaigns/themes/<int:theme_id>/activate/',
        admin_activate_theme,
        name='admin-activate-theme',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/posts/pending/',
        admin_campaign_posts_pending,
        name='admin-campaign-posts-pending',
    ),
    path(
        'admin/campaigns/posts/<int:score_id>/moderate/',
        admin_moderate_post,
        name='admin-moderate-post',
    ),
    path(
        'admin/campaigns/posts/<int:score_id>/scores/',
        admin_update_post_scores,
        name='admin-update-post-scores',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/leaderboard/generate/',
        admin_generate_leaderboard,
        name='admin-generate-leaderboard',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/winners/select/',
        admin_select_winners,
        name='admin-select-winners',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/analytics/',
        admin_campaign_analytics,
        name='admin-campaign-analytics',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/scoring-config/',
        admin_scoring_config_full,
        name='admin-scoring-config-full',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/scoring-config/update/',
        admin_update_scoring_config_full,
        name='admin-update-scoring-config-full',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/scoring/calculate/',
        admin_calculate_scores,
        name='admin-calculate-scores',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/scoring/save/',
        admin_save_scores,
        name='admin-save-scores',
    ),
    # Grand Campaign Phase 2 - Judge Scoring
    path(
        'admin/campaigns/<int:campaign_id>/finalists/',
        admin_get_finalists,
        name='admin-get-finalists',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/finalists/qualify/',
        admin_qualify_finalists,
        name='admin-qualify-finalists',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/judge-score/',
        admin_submit_judge_score,
        name='admin-submit-judge-score',
    ),
    path(
        'admin/campaigns/<int:campaign_id>/final-scores/calculate/',
        admin_calculate_final_scores,
        name='admin-calculate-final-scores',
    ),
    # Grand Campaign Phase 2 - Public Voting
    path(
        'campaigns/<int:campaign_id>/finalists/voting/',
        get_finalists_for_voting,
        name='get-finalists-voting',
    ),
    path('campaigns/<int:campaign_id>/vote/', cast_vote, name='cast-vote'),
    # Gamification
    path('gamification/status/', get_gamification_status, name='gamification-status'),
    path('gamification/debug/', debug_gamification, name='gamification-debug'),
    path('gamification/login-bonus/', claim_login_bonus, name='claim-login-bonus'),
    path('gamification/gift/', send_coin_gift, name='send-coin-gift'),
    path('gamification/gifts/history/', get_gift_history, name='gift-history'),
    path('gamification/activity/', get_recent_activity, name='recent-activity'),
    path('gamification/checkin/', check_in, name='check-in'),
    # Campaign (User)
    path('campaigns/', user_campaigns_list, name='campaigns-list'),
    path('campaigns/active/', get_active_campaigns, name='campaigns-active'),
    path('campaigns/<int:campaign_id>/', user_campaign_detail, name='campaign-detail'),
    path(
        'campaigns/<int:campaign_id>/extended/',
        get_campaign_detail_extended,
        name='campaign-detail-extended',
    ),
    path('campaigns/<int:campaign_id>/enter/', user_campaign_enter, name='campaign-enter'),
    path('campaigns/entries/<int:entry_id>/vote/', user_campaign_vote, name='campaign-vote'),
    path(
        'campaigns/<int:campaign_id>/leaderboard/',
        get_campaign_leaderboard,
        name='campaign-leaderboard',
    ),
    path('campaigns/<int:campaign_id>/winners/', get_campaign_winners, name='campaign-winners'),
    path('campaigns/<int:campaign_id>/feed/', get_campaign_feed, name='campaign-feed'),
    path(
        'campaigns/<int:campaign_id>/scoring-config/',
        get_scoring_config,
        name='campaign-scoring-config',
    ),
    path('campaigns/posts/create/', create_campaign_post, name='create-campaign-post'),
    path('campaigns/notifications/', get_campaign_notifications, name='campaign-notifications'),
    path('leaderboard/global/', global_leaderboard, name='global-leaderboard'),
    path('campaigns/profile/', get_user_campaign_profile, name='user-campaign-profile'),
    path(
        'campaigns/profile/<int:user_id>/',
        get_user_campaign_profile,
        name='user-campaign-profile-detail',
    ),
    path(
        'campaigns/<int:campaign_id>/engagement/update/',
        update_engagement_scores,
        name='update-engagement-scores',
    ),
    path(
        'campaigns/<int:campaign_id>/consistency/update/',
        update_consistency_scores,
        name='update-consistency-scores',
    ),
    # Reels Feeds
    path('reels/following/', reels_following, name='reels-following'),
    path('reels/saved/', reels_saved, name='reels-saved'),
    path('reels/trending/', reels_trending, name='reels-trending'),
    path('reels/not-interested/', mark_not_interested, name='mark-not-interested'),
    path('reels/not-interested/undo/', undo_not_interested, name='undo-not-interested'),
    path('reels/<int:reel_id>/view/', track_view, name='track-view'),
    # Notification and Privacy Settings
    path('notifications/me/', get_notification_settings, name='get-notification-settings'),
    path(
        'notifications/me/update/',
        update_notification_settings,
        name='update-notification-settings',
    ),
    path('profile/privacy/', get_privacy_settings, name='get-privacy-settings'),
    path('profile/privacy/update/', update_privacy_settings, name='update-privacy-settings'),
    path('explorer/trending/', get_trending_reels, name='explorer-trending'),
    path('explorer/trending-hashtags/', get_trending_hashtags, name='explorer-trending-hashtags'),
    path('explorer/hashtag/', get_reels_by_hashtag, name='explorer-hashtag'),
    path('categories/', get_categories, name='categories'),
    # Contest System - User
    path('subscription/details/', get_user_subscription, name='subscription-details'),
    path('subscription/upgrade/', upgrade_subscription, name='subscription-upgrade'),
    path('coins/packages/', get_coin_packages, name='coin-packages'),
    path('coins/balance/', get_coin_balance, name='coin-balance'),
    path('coins/purchase/', purchase_coins, name='coin-purchase'),
    path('coins/gift/', gift_creator, name='gift-creator'),
    path('coins/send-gift/', send_gift, name='send-gift'),
    path('coins/boost/', boost_post, name='boost-post'),
    path('coins/extra-entry/', purchase_extra_entry, name='extra-entry'),
    path('scores/<int:reel_id>/', get_post_score, name='post-score'),
    path('leaderboard/', get_leaderboard, name='leaderboard'),
    path('eligibility/phone/', verify_phone, name='verify-phone'),
    path('eligibility/age/', verify_age, name='verify-age'),
    path('upload/check/', check_upload_eligibility, name='check-upload'),
    path('grand-finale/', get_grand_finale, name='grand-finale'),
    path('grand-finale/vote/', vote_grand_finale, name='grand-vote'),
    # Contest System - Admin
    path('admin/contest/dashboard/', admin_contest_dashboard, name='admin-contest-dashboard'),
    path('admin/contest/flash-toggle/', toggle_flash_challenge, name='flash-toggle'),
    path('admin/contest/judging/', admin_judging_portal, name='admin-judging'),
    path('admin/contest/judge/<int:reel_id>/', judge_post, name='judge-post'),
    path('admin/contest/anti-cheat/', anti_cheat_flags, name='anti-cheat-flags'),
    path('admin/contest/review-flag/<int:flag_id>/', review_flag, name='review-flag'),
    # Legal Documents - Admin
    path('admin/legal/', admin_legal_documents_list, name='admin-legal-list'),
    path('admin/legal/stats/', admin_legal_stats, name='admin-legal-stats'),
    path('admin/legal/create/', admin_legal_document_create, name='admin-legal-create'),
    path('admin/legal/<int:document_id>/', admin_legal_document_detail, name='admin-legal-detail'),
    path(
        'admin/legal/<int:document_id>/update/',
        admin_legal_document_update,
        name='admin-legal-update',
    ),
    path(
        'admin/legal/<int:document_id>/delete/',
        admin_legal_document_delete,
        name='admin-legal-delete',
    ),
    path(
        'admin/legal/<int:document_id>/publish/',
        admin_legal_document_publish,
        name='admin-legal-publish',
    ),
    path(
        'admin/legal/<int:document_id>/archive/',
        admin_legal_document_archive,
        name='admin-legal-archive',
    ),
    path(
        'admin/legal/<int:document_id>/acceptances/',
        admin_legal_document_acceptances,
        name='admin-legal-acceptances',
    ),
    # ============ WALLET (User) ============
    path('wallet/', wallet_summary, name='wallet-summary'),
    path('wallet/transactions/', wallet_transactions, name='wallet-transactions'),
    path('wallet/config/', public_wallet_config, name='wallet-public-config'),
    path('wallet/withdrawal-info/', withdrawal_info, name='wallet-withdrawal-info'),
    path('wallet/withdraw/', request_withdrawal, name='wallet-withdraw'),
    path('wallet/withdrawals/', my_withdrawals, name='wallet-my-withdrawals'),
    path(
        'wallet/withdrawals/<int:withdrawal_id>/cancel/',
        cancel_withdrawal,
        name='wallet-cancel-withdrawal',
    ),
    path('wallet/reinvest/', reinvest_points, name='wallet-reinvest'),
    path('wallet/telebirr/initiate/', telebirr_initiate_payment, name='telebirr-initiate'),
    path('wallet/telebirr-callback/', telebirr_callback, name='telebirr-callback'),
    path('wallet/telebirr/auth/', telebirr_auth, name='telebirr-auth'),
    path('wallet/telebirr/query/', telebirr_query_order, name='telebirr-query'),
    path('wallet/telebirrUssdPurchase/', telebirr_ussd_purchase, name='telebirr-ussd-purchase'),
    path('webhooks/telebirrUssdPurchase/', telebirr_ussd_webhook, name='telebirr-ussd-webhook'),
    # Same view without the trailing slash. Telebirr registered
    # `http://uat.flipstar.et:6082/api/webhooks/telebirrUssdPurchase` -- no
    # slash -- and APPEND_SLASH answers a slashless POST with a 301. Their
    # Axis2 client does not replay the body on a redirect, so every
    # confirmation arrived as an empty GET and was dropped. Unnamed so
    # reverse() keeps returning the canonical slashed form.
    path('webhooks/telebirrUssdPurchase', telebirr_ussd_webhook),
    # ============ WALLET (Admin) ============
    path('admin/wallet/config/', admin_wallet_config, name='admin-wallet-config'),
    path('admin/wallet/user/<int:user_id>/', admin_user_wallet, name='admin-user-wallet'),
    path('admin/wallet/transactions/', admin_user_transactions, name='admin-user-transactions'),
    path(
        'admin/wallet/all-transactions/', admin_all_coin_transactions, name='admin-all-transactions'
    ),
    path('admin/wallet/adjust-balance/', admin_adjust_balance, name='admin-adjust-balance'),
    path('admin/wallet/withdrawals/', admin_withdrawals_list, name='admin-withdrawals-list'),
    path(
        'admin/wallet/withdrawals/<int:withdrawal_id>/action/',
        admin_withdrawal_action,
        name='admin-withdrawal-action',
    ),
    path(
        'admin/withdrawal-analytics/', admin_withdrawal_analytics, name='admin-withdrawal-analytics'
    ),
    # ============ SUBSCRIPTION SYSTEM ============
    # Subscription Status Check
    path('subscription/status/', UserSubscriptionStatusView.as_view(), name='subscription-status'),
    # The four OneVAS webhooks (onevas/subscription|unsubscription|renewal|
    # stop) were here. OneVAS has been removed; TIMWE's datasync below is the
    # subscription channel.
    #
    # TIMWE Master Aggregator datasync. One SOAP endpoint for subscribe,
    # unsubscribe and update -- the MA carries the operation in updateType
    # rather than in the URL.
    path(
        'timwe/sync-order-relation/',
        timwe_sync_order_relation,
        name='timwe-sync-order-relation',
    ),
    # Same view, without the trailing slash. NOT redundant: the MA is
    # configured to POST to `.../sync-order-relation` and APPEND_SLASH answers
    # a slashless POST with a 301, which SOAP clients either refuse to follow
    # or follow as a GET with the body discarded -- the failure looks like a
    # network problem from their side and like no traffic at all from ours.
    # Unnamed so reverse('timwe-sync-order-relation') keeps returning the
    # canonical slashed form.
    path(
        'timwe/sync-order-relation',
        timwe_sync_order_relation,
    ),
    # Subscription Tiers
    path(
        'subscriptions/tiers/',
        SubscriptionTierViewSet.as_view({'get': 'list'}),
        name='subscription-tiers',
    ),
    path(
        'subscriptions/tiers/active/',
        SubscriptionTierViewSet.as_view({'get': 'active'}),
        name='subscription-tiers-active',
    ),
    # User Subscriptions
    path(
        'subscriptions/',
        NewSubscriptionViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='subscriptions',
    ),
    path(
        'subscriptions/subscribe/',
        NewSubscriptionViewSet.as_view({'post': 'subscribe'}),
        name='subscription-subscribe',
    ),
    path(
        'subscriptions/unsubscribe/',
        NewSubscriptionViewSet.as_view({'post': 'unsubscribe'}),
        name='subscription-unsubscribe',
    ),
    path(
        'subscriptions/history/',
        NewSubscriptionViewSet.as_view({'get': 'history'}),
        name='subscription-history',
    ),
    # Telebirr one-time subscription (mimics coin purchase; api/views/wallet.py's
    # telebirr_callback delegates every 'SUB'-prefixed order here)
    path(
        'subscription/telebirr/one-time/initiate/',
        telebirr_one_time_initiate,
        name='telebirr-one-time-initiate',
    ),
    path(
        'subscription/telebirr/one-time/callback/',
        telebirr_one_time_callback,
        name='telebirr-one-time-callback',
    ),
    path(
        'subscription/telebirr/one-time/query/',
        telebirr_one_time_query,
        name='telebirr-one-time-query',
    ),
    path(
        'subscription/telebirr/ussd/initiate/',
        telebirr_ussd_subscription_initiate,
        name='telebirr-ussd-subscription-initiate',
    ),
    path(
        'subscription/telebirr/ussd/status/',
        telebirr_ussd_subscription_status,
        name='telebirr-ussd-subscription-status',
    ),
    path(
        'webhooks/telebirrSubscriptionUssd/',
        telebirr_ussd_subscription_webhook,
        name='telebirr-ussd-subscription-webhook',
    ),
    path('webhooks/telebirrSubscriptionUssd', telebirr_ussd_subscription_webhook),
    path(
        'subscription/validate-token/',
        validate_subscription_token,
        name='validate-subscription-token',
    ),
    path(
        'subscription/check-superapp/',
        check_superapp_subscription,
        name='check-superapp-subscription',
    ),
    # Telebirr Direct Debit
    path('direct-debit/create/', create_direct_debit_mandate, name='direct-debit-create'),
    path('direct-debit/activate/', activate_direct_debit_mandate, name='direct-debit-activate'),
    path('direct-debit/cancel/', cancel_direct_debit_mandate, name='direct-debit-cancel'),
    path('direct-debit/mandates/', list_user_mandates, name='direct-debit-mandates'),
    path('direct-debit/initiate/', initiate_direct_debit, name='direct-debit-initiate'),
    path(
        'direct-debit/one-off-coin-purchase/',
        create_one_off_coin_purchase,
        name='one-off-coin-purchase',
    ),
    path(
        'direct-debit/one-off-subscription/',
        create_one_off_subscription,
        name='one-off-subscription',
    ),
    path('direct-debit/check-status/', check_mandate_status, name='direct-debit-check-status'),
    path(
        'admin/direct-debit/query-mandate/', query_mandate_from_telebirr, name='admin-query-mandate'
    ),
    path(
        'webhooks/telebirr-direct-debit/',
        telebirr_direct_debit_webhook,
        name='telebirr-direct-debit-webhook',
    ),
    # Telebirr's own capture shows them POSTing
    # `/api/webhooks/telebirrDirectDebit/` -- camelCase, matching their other
    # Result Addresses. Only the kebab-case spelling above was ever served,
    # so their mandate confirmations hit the 404 handler. Both spellings,
    # both with and without the trailing slash.
    path('webhooks/telebirrDirectDebit/', telebirr_direct_debit_webhook),
    path('webhooks/telebirrDirectDebit', telebirr_direct_debit_webhook),
    path('webhooks/telebirr-direct-debit', telebirr_direct_debit_webhook),
    path('telebirr/b2c/initiate/', initiate_b2c_payment, name='telebirr-b2c-initiate'),
    path('telebirr/b2c/payments/', list_b2c_payments, name='telebirr-b2c-payments'),
    path('webhooks/telebirrB2C/', telebirr_b2c_webhook, name='telebirr-b2c-webhook'),
    # Same view without the trailing slash. Telebirr's registered Result
    # Address is `.../webhooks/telebirrB2C` and APPEND_SLASH answers a
    # slashless POST with a 301 -- their SOAP client does not follow it, so the
    # body is discarded and the payout confirmation is lost. Unnamed so
    # reverse() keeps returning the canonical slashed form.
    path('webhooks/telebirrB2C', telebirr_b2c_webhook),
    # CRM Gift Integration (data gifts) + Telebirr B2C winner gifts (cash)
    path(
        'admin/crm/packages/',
        CRMGiftPackageViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='admin-crm-packages',
    ),
    path(
        'admin/crm/packages/active/',
        CRMGiftPackageViewSet.as_view({'get': 'active'}),
        name='admin-crm-packages-active',
    ),
    path(
        'admin/crm/packages/<int:pk>/',
        CRMGiftPackageViewSet.as_view(
            {'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}
        ),
        name='admin-crm-package-detail',
    ),
    path(
        'admin/crm/transactions/',
        CRMGiftTransactionViewSet.as_view({'get': 'list'}),
        name='admin-crm-transactions',
    ),
    path(
        'admin/crm/transactions/<int:pk>/',
        CRMGiftTransactionViewSet.as_view({'get': 'retrieve', 'post': 'retry'}),
        name='admin-crm-transaction-detail',
    ),
    path(
        'admin/crm/audit-logs/',
        CRMGiftAuditLogViewSet.as_view({'get': 'list'}),
        name='admin-crm-audit-logs',
    ),
    path(
        'admin/crm/award/', CRMGiftAwardViewSet.as_view({'post': 'award'}), name='admin-crm-award'
    ),
    path(
        'admin/crm/award-by-phone/',
        CRMGiftAwardViewSet.as_view({'post': 'award_by_phone'}),
        name='admin-crm-award-phone',
    ),
    path(
        'admin/crm/campaign-winners/',
        CRMGiftAwardViewSet.as_view({'get': 'campaign_winners'}),
        name='admin-crm-campaign-winners',
    ),
    path(
        'admin/crm/award-campaign-winners/',
        CRMGiftAwardViewSet.as_view({'post': 'award_campaign_winners'}),
        name='admin-crm-award-campaign-winners',
    ),
    path(
        'admin/crm/send-b2c-gift/',
        CRMGiftAwardViewSet.as_view({'post': 'send_b2c_gift'}),
        name='admin-crm-send-b2c-gift',
    ),
    path(
        'admin/crm/send-b2c-bulk/',
        CRMGiftAwardViewSet.as_view({'post': 'send_b2c_bulk'}),
        name='admin-crm-send-b2c-bulk',
    ),
    # Coin Transactions
    path(
        'coins/transactions/',
        CoinTransactionViewSet.as_view({'get': 'list'}),
        name='coin-transactions',
    ),
    path(
        'coins/purchase/',
        CoinTransactionViewSet.as_view({'post': 'purchase'}),
        name='coin-purchase',
    ),
    # Admin Subscription Management
    path(
        'admin/subscriptions/',
        AdminSubscriptionViewSet.as_view({'get': 'list'}),
        name='admin-subscriptions',
    ),
    path(
        'admin/subscriptions/analytics/',
        AdminSubscriptionViewSet.as_view({'get': 'analytics'}),
        name='admin-subscriptions-analytics',
    ),
    path(
        'admin/subscriptions/revenue/',
        AdminSubscriptionViewSet.as_view({'get': 'revenue'}),
        name='admin-subscriptions-revenue',
    ),
    path(
        'admin/subscriptions/charging/',
        AdminSubscriptionViewSet.as_view({'get': 'charging_analytics'}),
        name='admin-subscriptions-charging',
    ),
    # ============ SUPPORT REQUESTS ============
    path('support/requests/', my_support_requests, name='support-requests'),
    path('admin/support/requests/', admin_support_requests, name='admin-support-requests'),
    path(
        'admin/support/requests/<int:request_id>/',
        admin_update_support_request,
        name='admin-support-request-update',
    ),
    path('admin/wallet/withdrawals/', admin_withdrawals_list, name='admin-wallet-withdrawals'),
    path(
        'admin/wallet/withdrawals/<int:withdrawal_id>/action/',
        admin_withdrawal_action,
        name='admin-wallet-withdrawal-action',
    ),
    path('admin/wallet/adjust-balance/', admin_adjust_balance, name='admin-wallet-adjust-balance'),
    # On-Demand Charging
    path('charging/on-demand/', initiate_on_demand_charging, name='on-demand-charging'),
    path('charging/on-demand/statistics/', get_charging_statistics, name='charging-statistics'),
    path(
        'charging/on-demand/transactions/', get_charging_transactions, name='charging-transactions'
    ),
    path('charging/on-demand/search/', search_charging_transactions, name='charging-search'),
    path('charging/on-demand/analytics/', get_charging_analytics, name='charging-analytics'),
    path('charging/coin-purchase/', purchase_coins_on_demand, name='coin-purchase-on-demand'),
    # Legal Documents - Public/User
    path('legal/', get_all_legal_documents, name='legal-all'),
    path('legal/<str:document_type>/', get_legal_document, name='legal-document'),
    path('legal/<str:document_type>/accept/', accept_legal_document, name='legal-accept'),
    path('legal/user/pending/', get_pending_acceptances, name='legal-pending'),
    path('legal/user/history/', get_user_acceptances, name='legal-history'),
    # ============ BOOST SYSTEM ============
    path('boost/config/', get_boost_config, name='boost-config'),
    path('boost/calculate-cost/', calculate_boost_cost, name='boost-calculate-cost'),
    path('boost/campaigns/', create_boost_campaign, name='boost-create'),
    path('boost/campaigns/my/', get_user_boost_campaigns, name='boost-my-campaigns'),
    path('boost/campaigns/<int:campaign_id>/', get_boost_campaign_detail, name='boost-detail'),
    path('boost/campaigns/<int:campaign_id>/cancel/', cancel_boost_campaign, name='boost-cancel'),
    path('boost/campaigns/<int:campaign_id>/pause/', pause_boost_campaign, name='boost-pause'),
    path('boost/campaigns/<int:campaign_id>/resume/', resume_boost_campaign, name='boost-resume'),
    path('boost/eligible/', get_eligible_boosts, name='boost-eligible'),
    path('boost/impression/', record_boost_impression, name='boost-impression'),
    path('boost/engagement/', record_boost_engagement, name='boost-engagement'),
    path('boost/pacing-check/', check_pacing_engine, name='boost-pacing-check'),
    path('', include(router.urls)),
]
