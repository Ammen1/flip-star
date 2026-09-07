"""
Pins the public URL contract.

The restructure moved every view module. These tests assert that each route
still resolves, still maps to a view with the same name, and still lives at the
same path -- which is what makes the change safe for the released mobile client.

If a test here fails, an API consumer breaks. Treat that as a release blocker,
not a test to update.
"""

import pytest
from django.urls import NoReverseMatch, resolve, reverse

pytestmark = pytest.mark.integration


#: (url name, expected path, expected view callable name)
#: Sampled across every view module touched by the restructure.
ROUTE_CONTRACT = [
    # auth
    ('auth-register', '/api/v1/auth/register/', 'register'),
    ('auth-login', '/api/v1/auth/login/', 'login'),
    ('auth-login-with-phone', '/api/v1/auth/login-with-phone/', 'login_with_phone'),
    ('auth-send-otp', '/api/v1/auth/send-phone-otp/', 'send_phone_otp'),
    ('auth-register-phone', '/api/v1/auth/register-with-phone/', 'register_with_phone'),
    ('auth-change-password', '/api/v1/auth/change-password/', 'change_password'),
    ('auth-delete-account', '/api/v1/auth/delete-account/', 'delete_account'),
    # health
    ('health-check', '/api/v1/health/', 'health_check'),
    ('health-check-deep', '/api/v1/health/deep/', 'health_check_deep'),
    # content
    ('create-post', '/api/v1/posts/create/', 'create_post'),
    ('search', '/api/v1/search/', 'search'),
    ('categories', '/api/v1/categories/', 'get_categories'),
    ('reels-trending', '/api/v1/reels/trending/', 'reels_trending'),
    ('reels-following', '/api/v1/reels/following/', 'reels_following'),
    ('reels-saved', '/api/v1/reels/saved/', 'reels_saved'),
    # wallet
    ('wallet-summary', '/api/v1/wallet/', 'wallet_summary'),
    ('wallet-transactions', '/api/v1/wallet/transactions/', 'wallet_transactions'),
    ('wallet-withdraw', '/api/v1/wallet/withdraw/', 'request_withdrawal'),
    ('wallet-reinvest', '/api/v1/wallet/reinvest/', 'reinvest_points'),
    ('telebirr-initiate', '/api/v1/wallet/telebirr/initiate/', 'telebirr_initiate_payment'),
    ('telebirr-callback', '/api/v1/wallet/telebirr-callback/', 'telebirr_callback'),
    # payments
    ('direct-debit-create', '/api/v1/direct-debit/create/', 'create_direct_debit_mandate'),
    ('direct-debit-activate', '/api/v1/direct-debit/activate/', 'activate_direct_debit_mandate'),
    (
        'telebirr-direct-debit-webhook',
        '/api/v1/webhooks/telebirr-direct-debit/',
        'telebirr_direct_debit_webhook',
    ),
    ('on-demand-charging', '/api/v1/charging/on-demand/', 'initiate_on_demand_charging'),
    # subscriptions
    ('subscription-status', '/api/v1/subscription/status/', 'UserSubscriptionStatusView'),
    ('subscription-tiers', '/api/v1/subscriptions/tiers/', 'SubscriptionTierViewSet'),
    ('onevas-subscription', '/api/v1/onevas/subscription/', 'OnevasWebhookView'),
    # gamification
    ('gamification-status', '/api/v1/gamification/status/', 'get_gamification_status'),
    ('claim-login-bonus', '/api/v1/gamification/login-bonus/', 'claim_login_bonus'),
    # campaigns
    ('campaigns-list', '/api/v1/campaigns/', 'user_campaigns_list'),
    ('campaigns-active', '/api/v1/campaigns/active/', 'get_active_campaigns'),
    ('create-campaign-post', '/api/v1/campaigns/posts/create/', 'create_campaign_post'),
    # boost
    ('boost-config', '/api/v1/boost/config/', 'get_boost_config'),
    ('boost-create', '/api/v1/boost/campaigns/', 'create_boost_campaign'),
    ('boost-eligible', '/api/v1/boost/eligible/', 'get_eligible_boosts'),
    # messaging
    ('dm-conversations', '/api/v1/messages/conversations/', 'list_or_create_conversations'),
    ('dm-unread-count', '/api/v1/messages/unread-count/', 'unread_dm_count'),
    # admin
    ('admin-dashboard', '/api/v1/admin/dashboard/', 'admin_dashboard_stats'),
    ('admin-users-list', '/api/v1/admin/users/', 'admin_users_list'),
    ('admin-wallet-config', '/api/v1/admin/wallet/config/', 'admin_wallet_config'),
    ('admin-settings', '/api/v1/admin/settings/', 'get_platform_settings'),
    # legal / support / push
    ('legal-all', '/api/v1/legal/', 'get_all_legal_documents'),
    ('support-requests', '/api/v1/support/requests/', 'my_support_requests'),
    ('push-public-key', '/api/v1/push/public-key/', 'push_public_key'),
]


@pytest.mark.parametrize('name,path,view_name', ROUTE_CONTRACT)
def test_route_reverses_to_expected_path(name, path, view_name):
    """Every named route still resolves to the same URL it did before."""
    assert reverse(name) == path


@pytest.mark.parametrize('name,path,view_name', ROUTE_CONTRACT)
def test_route_resolves_to_expected_view(name, path, view_name):
    """The URL still dispatches to a view with the same public name."""
    match = resolve(path)
    resolved = getattr(match.func, '__name__', None)

    if resolved in ('WrappedAPIView', 'view'):
        # DRF wraps @api_view functions and .as_view() results; unwrap them.
        resolved = (
            getattr(match.func, 'cls', None).__name__
            if getattr(match.func, 'cls', None)
            else getattr(match.func, '__wrapped__', match.func).__name__
        )

    assert resolved == view_name, f'{path} now dispatches to {resolved}, expected {view_name}'


#: Router basenames backed by a ModelViewSet, which generate a ``-list`` route.
COLLECTION_BASENAMES = [
    'profile',
    'reel',
    'quest',
    'subscription',
    'notification',
    'competition',
    'winner',
    'follow',
    'block',
    'comment',
    'comment-reply',
    'saved',
    'gift',
    'gift-transaction',
    'gift-stats',
]

#: Registered as plain ViewSets exposing only custom @action routes, so they
#: have no ``-list`` route by design.
ACTION_ONLY_BASENAMES = ['user-search', 'profile-photo']


@pytest.mark.parametrize('basename', COLLECTION_BASENAMES)
def test_router_collection_routes_still_mounted(basename):
    try:
        reverse(f'{basename}-list')
    except NoReverseMatch:  # pragma: no cover
        pytest.fail(f'router basename {basename!r} no longer resolves')


@pytest.mark.parametrize('basename', ACTION_ONLY_BASENAMES)
def test_action_only_viewsets_have_no_collection_route(basename):
    """Documents the asymmetry so a future reader does not "fix" it."""
    with pytest.raises(NoReverseMatch):
        reverse(f'{basename}-list')


def test_total_route_count_is_stable():
    """
    Guards against routes being silently added or dropped.

    279 is the count as of porting routes missing relative to the master
    branch: 3 Telebirr one-time-subscription routes, 2 direct-debit one-off
    routes, 1 privacy-policy route, 5 consent-tracking routes, 3 Telebirr B2C
    payout routes (initiate, list, webhook), 12 CRM gift / Telebirr B2C
    winner-gift routes (api/views/crm.py), 2 login-OTP routes, the
    router-registered drafts/ list+detail routes (api/views/core.py::DraftViewSet),
    leaderboard/global/ (api/views/campaign_user.py::global_leaderboard),
    5 SuperApp/USSD subscription routes (api/views/subscription.py:
    check_superapp_subscription, validate_subscription_token,
    telebirr_ussd_subscription_initiate/status/webhook), 2 admin reel
    moderation routes (api/views/admin.py: admin_reel_detail, admin_reel_moderate),
    2 client-log routes (api/views/client_log.py), 5 admin security-event
    routes (api/views/admin.py: admin_security_events, admin_log_security_event,
    admin_resolve_security_event, admin_mark_all_security_events_read, admin_security_stats),
    1 subscription-OTP-resend route (api/views/core.py::resend_subscription_otp,
    login_with_subscription_otp's companion for getting a fresh setup_otp),
    1 admin mandate-query route (api/views/direct_debit.py::query_mandate_from_telebirr,
    gated behind HasAdminPermission -- master left it IsAuthenticated-only
    despite taking an arbitrary payer_msisdn param), 4 admin
    privilege-management routes (api/views/admin.py: admin_user_role,
    admin_user_logs, admin_grant_admin, admin_privilege_audit -- the last
    gated behind HasAdminPermission('manage_admins') rather than master's
    bare IsAdminUser), 1 admin withdrawal-analytics route
    (api/views/wallet.py::admin_withdrawal_analytics), and 4 Telebirr
    SuperApp/USSD coin-purchase routes (api/views/wallet.py: telebirr_auth,
    telebirr_query_order, telebirr_ussd_purchase, telebirr_ussd_webhook --
    parallel to the existing H5/InApp telebirr_initiate_payment flow,
    keyed by originator_conversation_id and payment_method='telebirr_ussd'
    instead of merch_order_id/'telebirr' so the two never collide).
    +3 for the crypto test helpers (api/views/crypto.py: crypto_test_keypair,
    crypto_test_encrypt, crypto_test_decrypt). They are always routed, but the
    views raise Http404 unless settings.CRYPTO_TEST_ENDPOINTS_ENABLED is true,
    which defaults to False and is set only in the staging overlay. The count
    is therefore the same in every environment.

    +1 for the slashless alias of timwe/sync-order-relation (api/urls.py).
    The MA is configured without the trailing slash and APPEND_SLASH turns
    a slashless POST into a 301 that drops the body.

    +1 for the slashless alias of webhooks/telebirrB2C. Telebirr's registered
    Result Address omits the trailing slash and APPEND_SLASH turns a
    slashless POST into a 301 that drops the body.

    +2 for the slashless aliases of webhooks/telebirrUssdPurchase and
    webhooks/telebirrSubscriptionUssd, for the same reason. Telebirr registered
    `http://uat.flipstar.et:6082/api/webhooks/telebirrUssdPurchase` with no
    trailing slash, so every USSD confirmation was redirected and lost.

    +3 for webhooks/telebirrDirectDebit -- Telebirr's packet capture shows them
    posting the camelCase spelling, which was never routed at all (only
    kebab-case webhooks/telebirr-direct-debit was), plus the slashless variant
    of each spelling.

    +7 for the organization-scoped campaign surface
    (api/views/organization_campaigns.py: list, detail, update, delete, submit,
    approve, reject). These are separate from the admin campaign routes because
    those are is_staff-only and an ORGANIZATION-realm user is not staff. Every
    lookup in the new views resolves through visible_campaigns, so a campaign
    id belonging to another organization is not found rather than refused.

    +4 for the Super Admin organization surface
    (api/views/organizations.py: list/create, detail/update, campaigns-for-one,
    create-organization-admin). Gated on IsFlipstarUser -- creating
    organizations and appointing their administrators is platform-level, not
    something an organization may do for itself.

    +4 for the organization dashboard surface
    (api/views/organization_campaigns.py: dashboard, per-campaign analytics,
    leaderboard and posts). These exist so an organization dashboard has data
    to show without reaching the is_staff-only equivalents in
    campaign_admin.py, which carry no ownership check. Each resolves its
    campaign through get_campaign_for, and the dashboard aggregates are
    computed over visible_campaigns before counting -- a total taken across
    all campaigns would disclose another organization volume without
    rendering a row.

    +8 for coin management (api/views/coin_management.py): platform ceilings,
    the Super Admin organization overview, organization coin config (reachable
    both as /admin/organizations/<id>/coin-config/ and /organization/coin-config/,
    the same view -- an organization admin never names an organization, so the
    id is simply not read for them), campaign coin config, usage, reward
    transactions and the audit log.

    Update it deliberately when the API genuinely changes.
    """
    from api.urls import urlpatterns

    assert len(urlpatterns) == 331, (
        f'api/urls.py now declares {len(urlpatterns)} patterns. '
        'If this is intentional, update the expected count.'
    )
