"""Audit H-07: the server must not be steered at an arbitrary outbound host.

Covers the endpoint allow-list, the outbound timeout, redirect refusal, and the
move off the request path -- plus the original behaviour, so a legitimate
browser subscription is not collateral damage.
"""

import json
from unittest.mock import patch

import pytest
import requests
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from api.integrations.push.endpoints import (
    DEFAULT_ALLOWED_PUSH_HOSTS,
    PushEndpointRejected,
    host_is_allowed,
    validate_push_endpoint,
)
from api.integrations.push.webpush import PUSH_TIMEOUT_SECONDS
from api.models import PushSubscription

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

FCM = 'https://fcm.googleapis.com/fcm/send/abc123'
MOZ = 'https://updates.push.services.mozilla.com/wpush/v2/gAAAAA'
APPLE = 'https://web.push.apple.com/QDbc123'
WNS = 'https://db5p.notify.windows.com/w/?token=abc'


# ── the allow-list accepts what real browsers produce ────────────────────────


@pytest.mark.parametrize('endpoint', [FCM, MOZ, APPLE, WNS])
def test_real_browser_push_endpoints_are_accepted(endpoint):
    assert validate_push_endpoint(endpoint) == endpoint


def test_subdomain_entries_match_only_on_a_dot_boundary():
    assert host_is_allowed('db5p.notify.windows.com')
    assert not host_is_allowed(
        'evilnotify.windows.com'
    ), 'a suffix entry must not match a host that merely ends with the string'


def test_the_suffix_itself_is_not_a_valid_host():
    assert not host_is_allowed('notify.windows.com')


def test_trailing_dot_and_case_are_normalised():
    assert host_is_allowed('FCM.GoogleAPIs.com.')


# ── the allow-list rejects everything else ───────────────────────────────────


@pytest.mark.parametrize(
    ('endpoint', 'reason'),
    [
        ('https://evil.example.com/push', 'endpoint_host_not_allowed'),
        (
            'https://vault.flipstar-staging.svc.cluster.local:8200/v1/secret',
            'endpoint_port_not_allowed',
        ),
        ('https://vault.flipstar-staging.svc.cluster.local/v1/secret', 'endpoint_host_not_allowed'),
        ('https://localhost/push', 'endpoint_host_not_allowed'),
        ('https://127.0.0.1/push', 'endpoint_host_not_routable'),
        ('https://[::1]/push', 'endpoint_host_not_routable'),
        ('https://10.0.0.5/push', 'endpoint_host_not_routable'),
        ('https://192.168.1.1/push', 'endpoint_host_not_routable'),
        ('https://172.16.0.1/push', 'endpoint_host_not_routable'),
        ('https://169.254.169.254/latest/meta-data/', 'endpoint_host_not_routable'),
        ('https://[fd00::1]/push', 'endpoint_host_not_routable'),
        ('http://fcm.googleapis.com/fcm/send/x', 'endpoint_scheme_not_https'),
        ('file:///etc/passwd', 'endpoint_malformed'),
        ('gopher://fcm.googleapis.com/x', 'endpoint_scheme_not_https'),
        ('https://fcm.googleapis.com@evil.example.com/push', 'endpoint_has_credentials'),
        ('https://fcm.googleapis.com:8200/push', 'endpoint_port_not_allowed'),
        ('not a url at all', 'endpoint_malformed'),
        ('', 'endpoint_required'),
        ('   ', 'endpoint_required'),
    ],
)
def test_unacceptable_endpoints_are_rejected(endpoint, reason):
    with pytest.raises(PushEndpointRejected) as exc:
        validate_push_endpoint(endpoint)
    assert exc.value.reason == reason


@pytest.mark.parametrize('value', [None, 12345, {'endpoint': FCM}, ['x']])
def test_non_string_endpoints_are_rejected(value):
    with pytest.raises(PushEndpointRejected) as exc:
        validate_push_endpoint(value)
    assert exc.value.reason == 'endpoint_required'


def test_overlong_endpoint_is_rejected_before_the_database_sees_it():
    with pytest.raises(PushEndpointRejected) as exc:
        validate_push_endpoint('https://fcm.googleapis.com/fcm/send/' + 'a' * 700)
    assert exc.value.reason == 'endpoint_too_long'


def test_an_empty_allowlist_setting_falls_back_to_the_defaults(settings):
    """Empty must not mean "allow everything" -- that is finding M-11's shape."""
    settings.PUSH_ALLOWED_ENDPOINT_HOSTS = []
    assert validate_push_endpoint(FCM) == FCM
    with pytest.raises(PushEndpointRejected):
        validate_push_endpoint('https://evil.example.com/push')


def test_the_allowlist_can_be_narrowed_by_configuration(settings):
    settings.PUSH_ALLOWED_ENDPOINT_HOSTS = ['fcm.googleapis.com']
    assert validate_push_endpoint(FCM) == FCM
    with pytest.raises(PushEndpointRejected) as exc:
        validate_push_endpoint(MOZ)
    assert exc.value.reason == 'endpoint_host_not_allowed'


def test_widening_the_allowlist_still_cannot_reach_a_private_address(settings):
    """The IP checks are why widening the list is not a blank cheque."""
    settings.PUSH_ALLOWED_ENDPOINT_HOSTS = ['10.0.0.5']
    with pytest.raises(PushEndpointRejected) as exc:
        validate_push_endpoint('https://10.0.0.5/push')
    assert exc.value.reason == 'endpoint_host_not_routable'


def test_default_allowlist_contains_no_wildcard_and_no_ip():
    for entry in DEFAULT_ALLOWED_PUSH_HOSTS:
        assert '*' not in entry
        assert not entry.strip('.').replace('.', '').isdigit()


# ── the API surface ──────────────────────────────────────────────────────────


# push_subscribe is an @encrypted_endpoint, so these have to go through the
# sealed-envelope transport -- a plain JSON body is rejected with
# "decryption_failed" before the view runs, which is correct and is also why the
# first draft of these tests failed for the wrong reason.


@pytest.fixture()
def auth_client(encrypted_client_keys):
    user = User.objects.create_user(username='pusher', password='x')
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user, encrypted_client_keys


def _post_encrypted(client, keys, path, body):
    from common.security.e2e_encryption import encrypt_payload
    from common.security.encrypted_transport import CLIENT_PUBLIC_KEY_HEADER_NAME

    server_public, client_public, client_private = keys
    sealed = encrypt_payload(body, server_public, client_private)
    header = 'HTTP_' + CLIENT_PUBLIC_KEY_HEADER_NAME.upper().replace('-', '_')
    return client.post(
        path,
        sealed.to_dict(),
        format='json',
        **{header: client_public},
    )


def _open_envelope(response, keys):
    """Return the response body, decrypting it when it came back sealed."""
    from common.security.e2e_encryption import decrypt_payload

    server_public, _client_public, client_private = keys
    payload = response.json()
    if not isinstance(payload, dict) or 'encrypted' not in payload:
        return payload
    return json.loads(
        decrypt_payload(
            payload['encrypted'],
            payload['nonce'],
            server_public,
            payload['checksum'],
            client_private,
        )
    )


def _subscribe(client, keys, endpoint, *, include_keys=True):
    body = {'endpoint': endpoint}
    if include_keys:
        body['keys'] = {'p256dh': 'p' * 20, 'auth': 'a' * 16}
    return _post_encrypted(client, keys, '/api/v1/push/subscribe/', body)


def test_subscribe_stores_a_legitimate_endpoint(auth_client):
    client, user, keys = auth_client
    response = _subscribe(client, keys, FCM)
    assert response.status_code == 200, _open_envelope(response, keys)
    stored = PushSubscription.objects.get(user=user)
    assert stored.endpoint == FCM


def test_subscribe_refuses_an_internal_destination(auth_client):
    client, _user, keys = auth_client
    response = _subscribe(
        client, keys, 'https://vault.flipstar-staging.svc.cluster.local/v1/secret'
    )
    assert response.status_code == 400
    assert _open_envelope(response, keys)['code'] == 'endpoint_host_not_allowed'
    assert PushSubscription.objects.count() == 0, 'a rejected endpoint must not be persisted'


def test_subscribe_refuses_the_cloud_metadata_address(auth_client):
    client, _user, keys = auth_client
    response = _subscribe(client, keys, 'https://169.254.169.254/latest/meta-data/')
    assert response.status_code == 400
    assert _open_envelope(response, keys)['code'] == 'endpoint_host_not_routable'
    assert PushSubscription.objects.count() == 0


def test_subscribe_refuses_a_plaintext_http_endpoint(auth_client):
    client, _user, keys = auth_client
    response = _subscribe(client, keys, 'http://fcm.googleapis.com/fcm/send/x')
    assert response.status_code == 400
    assert _open_envelope(response, keys)['code'] == 'endpoint_scheme_not_https'


def test_the_rejection_does_not_echo_the_url_back(auth_client):
    client, _user, keys = auth_client
    response = _subscribe(client, keys, 'https://evil.example.com/pwn?secret=abc')
    assert 'evil.example.com' not in json.dumps(_open_envelope(response, keys))


def test_subscribe_still_requires_the_keys(auth_client):
    client, _user, keys = auth_client
    response = _subscribe(client, keys, FCM, include_keys=False)
    assert response.status_code == 400


def test_subscribe_rejects_a_plaintext_request(auth_client):
    """Regression: the endpoint must not accept an unsealed body."""
    client, _user, _keys = auth_client
    response = client.post(
        '/api/v1/push/subscribe/',
        {'endpoint': FCM, 'keys': {'p256dh': 'p' * 20, 'auth': 'a' * 16}},
        format='json',
    )
    assert response.status_code == 400


def test_subscribe_requires_authentication(encrypted_client_keys):
    response = _subscribe(APIClient(), encrypted_client_keys, FCM)
    assert response.status_code in (401, 403)


# ── the sender ───────────────────────────────────────────────────────────────


@pytest.fixture()
def vapid(settings):
    settings.VAPID_PRIVATE_KEY = 'x' * 43  # non-empty so _vapid_claims() returns
    settings.VAPID_SUBJECT = 'mailto:ops@example.com'
    return settings


def _sub(user, endpoint):
    return PushSubscription.objects.create(
        user=user, endpoint=endpoint, p256dh='p' * 20, auth='a' * 16
    )


def test_send_passes_a_finite_timeout(vapid):
    """pywebpush's own default is 10000 seconds; None waits forever."""
    from api.integrations.push.webpush import send_web_push_to_user

    user = User.objects.create_user(username='s_timeout', password='x')
    _sub(user, FCM)

    with patch('pywebpush.webpush') as wp:
        send_web_push_to_user(user, {'title': 't', 'body': 'b'})

    assert wp.call_args.kwargs['timeout'] == PUSH_TIMEOUT_SECONDS
    assert 0 < PUSH_TIMEOUT_SECONDS <= 30


def test_send_uses_a_session_that_refuses_redirects(vapid):
    from api.integrations.push.webpush import send_web_push_to_user

    user = User.objects.create_user(username='s_redir', password='x')
    _sub(user, FCM)

    with patch('pywebpush.webpush') as wp:
        send_web_push_to_user(user, {'title': 't'})

    session = wp.call_args.kwargs['requests_session']
    assert isinstance(session, requests.Session)
    with patch.object(requests.Session, 'request') as inner:
        session.request('POST', 'https://fcm.googleapis.com/x')
    assert inner.call_args.kwargs['allow_redirects'] is False


def test_send_revalidates_stored_rows_and_skips_a_bad_one(vapid):
    """A row written before H-07, or by anything but push_subscribe."""
    from api.integrations.push.webpush import send_web_push_to_user

    user = User.objects.create_user(username='s_stored', password='x')
    PushSubscription.objects.create(
        user=user, endpoint='https://169.254.169.254/x', p256dh='p' * 20, auth='a' * 16
    )
    _sub(user, FCM)

    with patch('pywebpush.webpush') as wp:
        delivered = send_web_push_to_user(user, {'title': 't'})

    assert delivered == 1, 'only the allow-listed subscription should be contacted'
    called = [c.kwargs['subscription_info']['endpoint'] for c in wp.call_args_list]
    assert called == [FCM]
    assert '169.254.169.254' not in ' '.join(called)


def test_a_timeout_is_logged_and_does_not_propagate(vapid):
    from api.integrations.push.webpush import send_web_push_to_user

    user = User.objects.create_user(username='s_to', password='x')
    _sub(user, FCM)

    with patch('pywebpush.webpush', side_effect=requests.Timeout('too slow')):
        delivered = send_web_push_to_user(user, {'title': 't'})
    assert delivered == 0


def test_a_failed_push_does_not_propagate(vapid):
    from api.integrations.push.webpush import send_web_push_to_user

    user = User.objects.create_user(username='s_fail', password='x')
    _sub(user, FCM)

    with patch('pywebpush.webpush', side_effect=RuntimeError('boom')):
        assert send_web_push_to_user(user, {'title': 't'}) == 0


def test_a_410_still_deletes_the_expired_subscription(vapid):
    """Original behaviour: the browser revoked it, so drop the row."""
    from pywebpush import WebPushException

    from api.integrations.push.webpush import send_web_push_to_user

    user = User.objects.create_user(username='s_410', password='x')
    _sub(user, FCM)

    class _Resp:
        status_code = 410
        reason = 'Gone'
        text = ''

    exc = WebPushException('gone', response=_Resp())
    with patch('pywebpush.webpush', side_effect=exc):
        send_web_push_to_user(user, {'title': 't'})

    assert not PushSubscription.objects.filter(user=user).exists()


def test_no_vapid_key_is_still_a_silent_no_op(settings):
    from api.integrations.push.webpush import send_web_push_to_user

    settings.VAPID_PRIVATE_KEY = ''
    user = User.objects.create_user(username='s_novapid', password='x')
    _sub(user, FCM)
    with patch('pywebpush.webpush') as wp:
        assert send_web_push_to_user(user, {'title': 't'}) == 0
    wp.assert_not_called()


def test_the_private_key_is_derived_once_not_once_per_subscription(vapid):
    from api.integrations.push import webpush as mod

    user = User.objects.create_user(username='s_key', password='x')
    _sub(user, FCM)
    _sub(user, MOZ)

    with patch.object(mod, '_resolve_private_key', wraps=mod._resolve_private_key) as key:
        with patch('pywebpush.webpush'):
            mod.send_web_push_to_user(user, {'title': 't'})

    # Once for the _vapid_claims() gate, once for the send. Not once per row.
    assert key.call_count <= 2


# ── off the request path ─────────────────────────────────────────────────────


def test_notification_creation_queues_the_push_instead_of_sending_it_inline():
    from api.models import Notification

    recipient = User.objects.create_user(username='n_recip', password='x')
    with patch('api.tasks.push.send_web_push.delay') as delay:
        Notification.objects.create(
            recipient=recipient, notification_type='system', message='hello'
        )
    assert delay.called, 'the signal must queue web push, not call it synchronously'
    assert delay.call_args.args[0] == recipient.pk


def test_a_broker_failure_does_not_stop_the_notification_being_recorded():
    from api.models import Notification

    recipient = User.objects.create_user(username='n_broker', password='x')
    with patch('api.tasks.push.send_web_push.delay', side_effect=OSError('broker down')):
        notification = Notification.objects.create(
            recipient=recipient, notification_type='system', message='still saved'
        )
    assert Notification.objects.filter(pk=notification.pk).exists()


def test_the_task_carries_a_time_limit():
    """Audit H-06: a task with no limit can hold a worker forever."""
    from api.tasks.push import send_web_push

    assert send_web_push.soft_time_limit
    assert send_web_push.time_limit
    assert send_web_push.soft_time_limit < send_web_push.time_limit


def test_the_task_swallows_a_missing_user():
    from api.tasks.push import send_web_push

    assert send_web_push.run(9_999_999, {'title': 't'}) == 0
