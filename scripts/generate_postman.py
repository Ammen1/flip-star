"""Generate a Postman v2.1 collection by introspecting Django's URL resolver.

Introspection rather than hand-authoring: the collection is then guaranteed to
match the routes the application actually serves, including HTTP methods.
"""

import json
import os
import re
import sys
import uuid
from collections import OrderedDict

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)

# Resolve routes without needing a database, Redis or Vault.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
os.environ.setdefault('DB_ENGINE', 'django.db.backends.sqlite3')
os.environ.setdefault('DB_NAME', os.path.join(BACKEND_ROOT, 'db.sqlite3'))
os.environ.setdefault('USE_DOCKER_DB', 'true')
os.environ.setdefault('USE_LOCMEM_CACHE', 'true')
os.environ.setdefault('LOG_LEVEL', 'CRITICAL')
os.environ.pop('VAULT_ADDR', None)

import django  # noqa: E402

django.setup()

from django.urls import get_resolver  # noqa: E402
from django.urls.resolvers import URLPattern, URLResolver  # noqa: E402

BASE_URL = '{{baseUrl}}'

# --- Folder routing ---------------------------------------------------------
# Longest prefix wins, so /api/admin/wallet/ lands in Admin, not Wallet.
FOLDERS = [
    ('api/v1/admin/wallet/', 'Admin / Wallet'),
    ('api/v1/admin/campaigns/', 'Admin / Campaigns'),
    ('api/v1/admin/contest/', 'Admin / Contest'),
    ('api/v1/admin/legal/', 'Admin / Legal'),
    ('api/v1/admin/master-campaigns/', 'Admin / Master Campaigns'),
    ('api/v1/admin/subscriptions/', 'Admin / Subscriptions'),
    ('api/v1/admin/support/', 'Admin / Support'),
    ('api/v1/admin/reports/', 'Admin / Moderation'),
    ('api/v1/admin/moderation-actions/', 'Admin / Moderation'),
    ('api/v1/admin/settings/', 'Admin / Platform Settings'),
    ('api/v1/admin/api-keys/', 'Admin / Platform Settings'),
    ('api/v1/admin/logs/', 'Admin / Platform Settings'),
    ('api/v1/admin/security/', 'Admin / Platform Settings'),
    ('api/v1/admin/performance/', 'Admin / Platform Settings'),
    ('api/v1/admin/database/', 'Admin / Platform Settings'),
    ('api/v1/admin/notifications/', 'Admin / Platform Settings'),
    ('api/v1/admin/gifts/', 'Admin / Gifts'),
    ('api/v1/admin/', 'Admin / Core'),
    ('api/v1/auth/', 'Authentication'),
    ('api/v1/health', 'Health'),
    ('api/v1/wallet/', 'Wallet'),
    ('api/v1/coins/', 'Coins & Contest'),
    ('api/v1/subscriptions/', 'Subscriptions'),
    ('api/v1/subscription/', 'Subscriptions'),
    ('api/v1/onevas/', 'Webhooks (Onevas)'),
    ('api/v1/webhooks/', 'Webhooks (Telebirr)'),
    ('api/v1/direct-debit/', 'Payments / Direct Debit'),
    ('api/v1/charging/', 'Payments / Onevas Charging'),
    ('api/v1/campaigns/', 'Campaigns'),
    ('api/v1/boost/', 'Boost'),
    ('api/v1/gamification/', 'Gamification'),
    ('api/v1/gifts/', 'Gifts'),
    ('api/v1/gift-transactions/', 'Gifts'),
    ('api/v1/gift-stats/', 'Gifts'),
    ('api/v1/messages/', 'Messaging'),
    ('api/v1/notifications/', 'Notifications'),
    ('api/v1/push/', 'Notifications'),
    ('api/v1/reels/', 'Reels & Feed'),
    ('api/v1/posts/', 'Reels & Feed'),
    ('api/v1/explorer/', 'Reels & Feed'),
    ('api/v1/comments/', 'Comments'),
    ('api/v1/comment-replies/', 'Comments'),
    ('api/v1/saved/', 'Reels & Feed'),
    ('api/v1/profile', 'Profile & Social'),
    ('api/v1/follows/', 'Profile & Social'),
    ('api/v1/blocks/', 'Profile & Social'),
    ('api/v1/user-search/', 'Profile & Social'),
    ('api/v1/search/', 'Profile & Social'),
    ('api/v1/legal/', 'Legal'),
    ('api/v1/support/', 'Support'),
    ('api/v1/reports/', 'Moderation'),
    ('api/v1/leaderboard/', 'Coins & Contest'),
    ('api/v1/scores/', 'Coins & Contest'),
    ('api/v1/eligibility/', 'Coins & Contest'),
    ('api/v1/upload/', 'Coins & Contest'),
    ('api/v1/grand-finale', 'Coins & Contest'),
    ('api/v1/quests/', 'Gamification'),
    ('api/v1/competitions/', 'Campaigns'),
    ('api/v1/winners/', 'Campaigns'),
    ('api/v1/categories/', 'Reference Data'),
    ('api/v1/settings/', 'Reference Data'),
    ('api/v1/setup-admin/', 'Danger Zone'),
    ('api/v1/cleanup-reels/', 'Danger Zone'),
    ('api/v1/', 'Reference Data'),          # DRF browsable API root
]

# --- Request bodies, keyed by URL name --------------------------------------
BODIES = {
    'auth-register': {'username': 'newuser', 'email': 'newuser@example.com', 'password': '123456'},
    'auth-login': {'username': 'admin', 'password': 'Admin12345!'},
    'auth-login-with-phone': {'phone': '0912345678', 'password': '123456'},
    'auth-reset-password': {'email': 'user@example.com', 'new_password': '123456'},
    'auth-change-password': {'current_password': '123456', 'new_password': '654321'},
    'auth-send-otp': {'phone': '0912345678'},
    'auth-verify-otp': {'phone': '0912345678', 'code': '123456'},
    'auth-register-phone': {'phone': '0912345678', 'username': 'newuser', 'password': '123456', 'email': ''},
    'auth-login-subscription-otp': {'phone': '0912345678', 'username': 'newuser', 'otp': '123456', 'password': '123456'},
    'auth-check-phone-account': {'phone': '0912345678'},
    'auth-dev-create-subscription': {'phone': '0912345678'},
    'auth-forgot-password': {'email': 'user@example.com'},
    'auth-forgot-password-confirm': {'email': 'user@example.com', 'code': '123456', 'new_password': '654321'},
    'auth-forgot-password-phone': {'phone': '0912345678'},
    'auth-forgot-password-phone-verify': {'phone': '0912345678', 'code': '123456', 'new_password': '654321'},

    'wallet-withdraw': {'point_amount': 1000, 'payout_method': 'telebirr', 'payout_account': '0912345678', 'payout_account_name': 'Abebe Bekele'},
    'wallet-reinvest': {'points': 100},
    'telebirr-initiate': {'package_id': 1, 'phone_number': '251912345678'},
    'telebirr-callback': {'outTradeNo': 'TX1700000000000', 'tradeStatus': 'SUCCESS', 'transactionId': 'TB123456', 'totalAmount': '100.00', 'signature': '<rsa-signature>'},
    'admin-wallet-adjust-balance': {'user_id': 1, 'amount': 100, 'balance_type': 'earned', 'reason': 'Support credit'},
    'admin-wallet-withdrawal-action': {'action': 'approve', 'admin_notes': 'Verified', 'payout_reference': 'TB-REF-001'},

    'direct-debit-create': {'tier_id': '{{tierId}}', 'payer_msisdn': '251912345678', 'frequency': '05'},
    'direct-debit-activate': {'mandate_id': '{{mandateId}}'},
    'direct-debit-cancel': {'mandate_id': '{{mandateId}}'},
    'direct-debit-initiate': {'mandate_id': '{{mandateId}}', 'amount': '50.00'},
    'one-off-coin-purchase': {'payer_msisdn': '251912345678', 'amount': '50.00', 'coin_amount': 500},

    'on-demand-charging': {'tier_id': '{{tierId}}', 'phone_number': '251912345678'},
    'coin-purchase-on-demand': {'phone_number': '251912345678', 'coin_amount': 500},

    'onevas-subscription': {'phone_number': '251912345678', 'product_number': '10000302850', 'password': 'A'},
    'onevas-unsubscription': {'phone_number': '251912345678', 'product_number': '10000302850'},
    'onevas-renewal': {'phone_number': '251912345678', 'product_number': '10000302850'},
    'onevas-stop': {'phone_number': '251912345678', 'product_number': '10000302850', 'params': [{'name': 'keyword', 'value': 'STOP1'}]},

    'send-coin-gift': {'recipient_username': 'someuser', 'amount': 10, 'message': 'Nice post!'},
    'gift-creator': {'recipient_id': 2, 'coins': 20, 'reel_id': 1, 'message': 'Great work'},
    'send-gift': {'gift_id': 1, 'recipient_id': 2, 'reel_id': 1, 'quantity': 1, 'message': ''},
    'coin-purchase': {'package_id': 1, 'payment_method': 'telebirr'},
    'boost-post': {'reel_id': 1, 'duration_hours': 2},
    'extra-entry': {'campaign_id': 1},
    'subscription-upgrade': {'tier': 'gold', 'payment_method': 'telebirr'},

    'boost-create': {'reel_id': 1, 'duration_hours': 24, 'target_gender': 'all', 'target_age_min': 18, 'target_age_max': 45, 'target_location': ''},
    'boost-impression': {'reel_id': 1},
    'boost-engagement': {'reel_id': 1, 'engagement_type': 'like'},
    'boost-calculate-cost': {'duration_hours': 24, 'has_premium_targeting': False},

    'create-post': {'caption': 'My first post', 'hashtags': 'flipstar,ethiopia', 'campaign_id': ''},
    'create-campaign-post': {'campaign_id': 1, 'caption': 'Campaign entry', 'hashtags': 'contest'},
    'campaign-enter': {'reel_id': 1},
    'cast-vote': {'finalist_id': 2},
    'grand-vote': {'entry_id': 1, 'coins': 10},

    'create-report': {'target_type': 'reel', 'reported_reel': 1, 'report_type': 'spam', 'description': 'Repeated spam content'},
    'admin-report-moderate': {'action_taken': 'shadowban', 'reason_details': 'Confirmed spam', 'status': 'resolved'},

    'dm-conversations': {'user_id': 2},
    'dm-conv-messages': {'text': 'Hello!'},
    'dm-message': {'text': 'Edited message'},

    'push-subscribe': {'endpoint': 'https://fcm.googleapis.com/fcm/send/xyz', 'keys': {'p256dh': '<p256dh>', 'auth': '<auth>'}},
    'push-unsubscribe': {'endpoint': 'https://fcm.googleapis.com/fcm/send/xyz'},

    'support-requests': {'category': 'payment', 'subject': 'Withdrawal not received', 'message': 'Requested 3 days ago.'},
    'admin-support-request-update': {'status': 'in_progress', 'admin_response': 'Investigating.'},

    'legal-accept': {'version': '1.0'},
    'admin-legal-create': {'document_type': 'terms', 'title': 'Terms of Service', 'content': '<p>...</p>', 'version': '1.0'},

    'update-notification-settings': {'likes': True, 'comments': True, 'follows': True, 'messages': True, 'mentions': True},
    'update-privacy-settings': {'is_private': False, 'show_activity': True, 'allow_messages': True, 'allow_mentions': True},
    'mark-not-interested': {'reel_id': 1},
    'undo-not-interested': {'reel_id': 1},
    'track-view': {},
    'admin-bulk-action': {'user_ids': [1, 2], 'action': 'deactivate'},
    'admin-send-notification': {'title': 'Maintenance', 'message': 'Scheduled downtime tonight.', 'priority': 'high'},
    'admin-settings-update': {'platform_name': 'FlipStar', 'maintenance_mode': False},
    'admin-api-key-create': {'name': 'Analytics integration'},
    'admin-user-update': {'is_active': True, 'is_staff': False},
    'admin-subscription-upgrade': {'tier': 'gold', 'duration_days': 30},
    'admin-campaign-create': {'title': 'Weekly Dance Contest', 'description': 'Show your moves', 'campaign_type': 'weekly', 'prize_title': '10,000 ETB', 'prize_description': 'Cash prize', 'prize_value': 10000, 'winner_count': 3},
    'admin-generate-sub-campaigns': {'confirm': True},
    'admin-submit-judge-score': {'user_id': 2, 'creativity_score': 25, 'quality_score': 20, 'theme_score': 18, 'impact_score': 22, 'judge_comments': 'Strong entry'},
    'admin-qualify-finalists': {'percentage': 20},
    'judge-post': {'creativity': 25, 'quality': 12, 'theme_relevance': 8},
    'flash-toggle': {'is_active': True, 'multiplier': 1.5},
    'review-flag': {'status': 'cleared', 'notes': 'False positive'},
    'verify-phone': {'phone_number': '251912345678', 'verification_code': '123456'},
    'verify-age': {'date_of_birth': '2000-01-01'},
}

GENERIC_BODY = {}

# --- Path parameter example values -------------------------------------------
PARAM_EXAMPLES = {
    'user_id': '1', 'reel_id': '1', 'comment_id': '1', 'campaign_id': '1',
    'notification_id': '1', 'report_id': '1', 'action_id': '1', 'entry_id': '1',
    'withdrawal_id': '1', 'request_id': '1', 'document_id': '1', 'key_id': '1',
    'theme_id': '1', 'score_id': '1', 'flag_id': '1', 'conversation_id': '1',
    'message_id': '1', 'pk': '1', 'id': '1', 'document_type': 'terms',
}


def normalise(fragment):
    """Strip regex anchors so path() and re_path() fragments concatenate cleanly.

    DefaultRouter registers routes with re_path, so str(pattern.pattern) yields
    '^profile/$'. Without this, prefixes concatenate to 'api/^profile/$' and no
    folder rule matches.
    """
    return str(fragment).lstrip('^').rstrip('$')


def collect(resolver, prefix='', out=None):
    """Walk the URLconf, yielding (route, name, callback)."""
    out = out if out is not None else []
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            collect(pattern, prefix + normalise(pattern.pattern), out)
        elif isinstance(pattern, URLPattern):
            out.append((prefix + normalise(pattern.pattern), pattern.name, pattern.callback))
    return out


def methods_for(callback):
    """Determine the HTTP methods a view accepts."""
    # ViewSets routed by DefaultRouter carry an actions mapping.
    actions = getattr(callback, 'actions', None) or getattr(callback, 'initkwargs', {}).get('actions')
    if actions:
        return sorted({m.upper() for m in actions})

    cls = getattr(callback, 'cls', None)
    if cls is not None:
        allowed = getattr(cls, 'http_method_names', None)
        if allowed:
            concrete = [
                m.upper() for m in allowed
                if m not in ('options', 'head', 'trace') and hasattr(cls, m)
            ]
            if concrete:
                return sorted(concrete)
        # @api_view stores the decorated methods on the generated class.
        wrapped = getattr(cls, 'http_method_names', [])
        return sorted(m.upper() for m in wrapped if m not in ('options', 'head', 'trace')) or ['GET']

    return ['GET']


def is_public(callback):
    """True when the view allows unauthenticated access.

    Public endpoints must be marked `noauth` in the collection. Collection-level
    auth otherwise sends `Authorization: Token {{token}}`, and before login that
    renders as a bare `Token ` header, which DRF rejects with
    "Invalid token header. No credentials provided." — turning a working public
    endpoint into a 401.
    """
    cls = getattr(callback, 'cls', None)
    permissions = getattr(cls, 'permission_classes', None) if cls else None

    if permissions is None:
        # Plain Django view (not DRF) — no token auth involved.
        return True

    names = {p.__name__ for p in permissions}
    if not names:
        return True
    return names == {'AllowAny'}


def folder_for(route):
    for prefix, name in FOLDERS:
        if route.startswith(prefix):
            return name
    return 'Other'


def clean_route(route):
    """Convert Django path converters and DRF regex groups to Postman :param syntax."""
    # Named regex groups first: (?P<pk>[^/.]+) -> :pk
    # Must precede the generic <...> rule below, which would otherwise rewrite
    # the inner <pk> and leave the surrounding regex behind as literal text.
    route = re.sub(r'\(\?P<([^>]+)>[^)]*\)', r':\1', route)
    # path() converters: <int:user_id> -> :user_id
    route = re.sub(r'<[^:>]+:([^>]+)>', r':\1', route)
    route = re.sub(r'<([^>]+)>', r':\1', route)
    # DRF's optional format suffix adds noise Postman cannot use.
    route = route.replace(r'\.(?P<format>[a-z0-9]+)/?', '')
    return route.strip('^$')


def title_for(name, route, method):
    if name:
        return f"{method} {name.replace('-', ' ')}"
    return f'{method} /{route}'


def build_request(route, name, methods, public=False):
    items = []
    path_clean = clean_route(route)
    params = re.findall(r':([a-z_]+)', path_clean)

    for method in methods:
        header = [{'key': 'Accept', 'value': 'application/json'}]

        # Postman rebuilds the request URL from `path`, not `raw`, so the
        # trailing slash has to survive as an empty final segment. Dropping it
        # sends /api/auth/login, and Django's APPEND_SLASH cannot redirect a
        # POST without discarding the body -- it raises RuntimeError instead.
        segments = [p for p in path_clean.split('/') if p]
        if path_clean.endswith('/'):
            segments.append('')

        request = {
            'method': method,
            'header': header,
            'url': {
                'raw': f'{BASE_URL}/{path_clean}',
                'host': [BASE_URL],
                'path': segments,
            },
        }

        if params:
            request['url']['variable'] = [
                {'key': p, 'value': PARAM_EXAMPLES.get(p, '1'), 'description': f'{p} path parameter'}
                for p in params
            ]

        if method in ('POST', 'PUT', 'PATCH'):
            header.append({'key': 'Content-Type', 'value': 'application/json'})
            body = BODIES.get(name, GENERIC_BODY)
            request['body'] = {
                'mode': 'raw',
                'raw': json.dumps(body, indent=2),
                'options': {'raw': {'language': 'json'}},
            }

        if public:
            # Opt out of collection-level auth so an empty {{token}} cannot
            # produce a bare "Authorization: Token " header.
            request['auth'] = {'type': 'noauth'}

        item = {
            'name': title_for(name, path_clean, method),
            'request': request,
            'response': [],
        }

        # Capture the auth token automatically after a successful login.
        if name in ('auth-login', 'auth-login-with-phone', 'auth-register',
                    'auth-register-phone', 'auth-login-subscription-otp'):
            item['event'] = [{
                'listen': 'test',
                'script': {
                    'type': 'text/javascript',
                    'exec': [
                        'const res = pm.response.json();',
                        'if (res.token) {',
                        '    pm.collectionVariables.set("token", res.token);',
                        '    console.log("Saved token to collection variable");',
                        '}',
                        'pm.test("status is 2xx", () => pm.response.to.be.success);',
                    ],
                },
            }]

        items.append(item)
    return items


def main():
    routes = collect(get_resolver())

    folders = OrderedDict()
    total = 0
    public_count = [0]

    for route, name, callback in sorted(routes, key=lambda r: r[0]):
        if not route.startswith('api/'):
            continue
        # DRF's format-suffix routes (.json/.api) duplicate every router route
        # with a content-negotiation suffix. Useless noise in a collection.
        if '?P<format>' in route:
            continue
        methods = methods_for(callback)
        folder = folder_for(route)
        public = is_public(callback)
        folders.setdefault(folder, [])
        for item in build_request(route, name, methods, public=public):
            folders[folder].append(item)
            total += 1
            if public:
                public_count[0] += 1

    collection = {
        'info': {
            '_postman_id': str(uuid.uuid4()),
            'name': 'FlipStar Backend API',
            'description': (
                'Generated by introspecting the Django URL resolver, so every route here is one '
                'the application actually serves.\n\n'
                '## Setup\n'
                '1. Set `baseUrl` (defaults to http://127.0.0.1:8000).\n'
                '2. Run **Authentication > POST auth login**. The token is captured into the '
                '`token` collection variable automatically.\n'
                '3. Every other request inherits `Authorization: Token {{token}}`.\n\n'
                '## Notes\n'
                '- Auth is DRF Token, not Bearer/JWT.\n'
                '- Passwords are exactly 6 digits for app users; the seeded admin is an exception.\n'
                '- Webhook folders are called by Telebirr/Onevas, not by clients. They are '
                'included for testing and currently require no authentication.\n'
                '- Requests under **Danger Zone** are destructive and unauthenticated. '
                'See docs/security.md.\n'
            ),
            'schema': 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
        },
        'auth': {
            'type': 'apikey',
            'apikey': [
                {'key': 'key', 'value': 'Authorization', 'type': 'string'},
                {'key': 'value', 'value': 'Token {{token}}', 'type': 'string'},
                {'key': 'in', 'value': 'header', 'type': 'string'},
            ],
        },
        'variable': [
            {'key': 'baseUrl', 'value': 'http://127.0.0.1:8000', 'type': 'string'},
            {'key': 'token', 'value': '', 'type': 'string'},
            {'key': 'tierId', 'value': '', 'type': 'string'},
            {'key': 'mandateId', 'value': '', 'type': 'string'},
        ],
        'item': [
            {'name': folder, 'item': items}
            for folder, items in sorted(folders.items())
        ],
    }

    out_dir = os.path.join(BACKEND_ROOT, 'docs', 'postman')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'FlipStar-API.postman_collection.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(collection, fh, indent=2)

    print(f'Wrote {out_path}')
    print(f'  folders : {len(folders)}')
    print(f'  requests: {total}')
    print(f'  public  : {public_count[0]} marked noauth (AllowAny views)')
    print(f'  authed  : {total - public_count[0]} inherit Token {{{{token}}}}')
    for folder, items in sorted(folders.items()):
        print(f'    {folder:<32} {len(items)}')


if __name__ == '__main__':
    main()
