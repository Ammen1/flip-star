"""Web Push (VAPID) sender.

Wraps `pywebpush` so callers can fire-and-forget notifications to all of a
user's PushSubscriptions. Subscriptions that the browser has revoked
(HTTP 404 / 410) are deleted automatically.

Configure VAPID keys via env vars (see `config/settings.py`).
"""

from __future__ import annotations

import json
import logging

import requests
from django.conf import settings
from django.contrib.auth.models import User

from api.integrations.push.endpoints import PushEndpointRejected, validate_push_endpoint

logger = logging.getLogger(__name__)

#: Seconds to wait for a push service. Audit finding H-07: pywebpush's own
#: default is ``timeout=10000`` -- ten thousand SECONDS, which requests reads as
#: nearly three hours -- and ``webpush(timeout=None)`` waits forever, because
#: ``send()`` pops the key and hands None straight to requests. Neither is a
#: timeout. This value is passed explicitly on every call.
PUSH_TIMEOUT_SECONDS = 10


class _NoRedirectSession(requests.Session):
    """A session that refuses to follow redirects.

    Validation happens on the URL that gets stored, so a 302 from an
    allow-listed host to an internal address would step around it. pywebpush's
    ``send()`` builds its own ``post()`` call and forwards no
    ``allow_redirects``, so the only place to force it is here.
    """

    def request(self, method, url, **kwargs):  # type: ignore[override]
        kwargs['allow_redirects'] = False
        return super().request(method, url, **kwargs)


def _vapid_claims() -> dict | None:
    if not _resolve_private_key():
        return None
    return {'sub': settings.VAPID_SUBJECT}


def _resolve_private_key() -> str:
    """Return a private key value accepted by pywebpush.

    Supports three input formats set in `VAPID_PRIVATE_KEY`:
      1. Inline PEM string (``-----BEGIN PRIVATE KEY-----\n...\n-----END...``)
      2. A filesystem path to a PEM file (e.g. ``/app/private_key.pem``)
      3. Raw URL-safe base64 of the 32-byte private scalar (what
         ``py_vapid --applicationServerKey`` does not print, but which is
         the easiest single-line value to stash in ``.env``). It's converted
         to PEM on the fly so pywebpush can use it.
    """
    raw = (settings.VAPID_PRIVATE_KEY or '').strip()
    if not raw:
        return ''
    if raw.startswith('-----BEGIN'):
        return raw
    # File path?
    try:
        import os

        if os.path.isfile(raw):
            with open(raw) as f:
                return f.read()
    except OSError:
        # Not readable as a file; fall through to the base64 interpretation
        # below. Logged at debug rather than swallowed: a VAPID_PRIVATE_KEY that
        # looks like a path but cannot be read is a deployment mistake worth
        # being able to see, and it is not otherwise distinguishable from a key
        # that was never a path.
        logger.debug('VAPID_PRIVATE_KEY is not a readable file path', exc_info=True)
    # Treat as URL-safe base64 of the 32-byte scalar → build a PEM.
    try:
        import base64

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        pad = '=' * (-len(raw) % 4)
        data = base64.urlsafe_b64decode(raw + pad)
        if len(data) != 32:
            return raw  # let pywebpush complain clearly
        secret_int = int.from_bytes(data, 'big')
        key = ec.derive_private_key(secret_int, ec.SECP256R1())
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return pem.decode('utf-8')
    except Exception:
        return raw


def send_web_push_to_user(user: User, payload: dict) -> int:
    """Send a Web Push payload to every active subscription a user has.

    Returns the number of subscriptions the push was successfully delivered to.
    Silently no-ops (returning 0) when VAPID isn't configured or pywebpush isn't
    installed, so callers can use this freely without breaking notification
    creation if push is disabled.
    """
    if not user or not user.is_authenticated:
        return 0
    claims = _vapid_claims()
    if not claims:
        return 0

    try:
        from pywebpush import WebPushException, webpush
    except Exception:  # pragma: no cover
        logger.warning('pywebpush not installed; skipping push send')
        return 0

    from api.models import PushSubscription

    subs = list(PushSubscription.objects.filter(user=user))
    if not subs:
        return 0

    body = json.dumps(payload)
    # Derived once, not once per subscription: _resolve_private_key() can run a
    # base64 decode and an EC key derivation, and it returns the same value
    # every time within a call.
    private_key = _resolve_private_key()
    delivered = 0
    with _NoRedirectSession() as session:
        for sub in subs:
            # Re-validated at send time, not just at subscribe time. Rows
            # predate this check, PUSH_ALLOWED_ENDPOINT_HOSTS can narrow, and a
            # row can be written by something other than push_subscribe. A
            # destination that is no longer acceptable is dropped rather than
            # contacted.
            try:
                endpoint = validate_push_endpoint(sub.endpoint)
            except PushEndpointRejected as exc:
                logger.warning(
                    'WebPush subscription %s not delivered: %s',
                    sub.pk,
                    exc.detail,
                    extra={'operation': 'web_push_send', 'result': exc.reason},
                )
                continue

            try:
                webpush(
                    subscription_info={
                        'endpoint': endpoint,
                        'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                    },
                    data=body,
                    vapid_private_key=private_key,
                    vapid_claims=dict(claims),
                    timeout=PUSH_TIMEOUT_SECONDS,
                    requests_session=session,
                )
                delivered += 1
            except WebPushException as exc:  # type: ignore[misc]
                status = getattr(exc.response, 'status_code', None) if exc.response else None
                if status in (404, 410):
                    # Subscription expired/unsubscribed — clean up.
                    try:
                        sub.delete()
                    except Exception:
                        # A row that cannot be deleted will be retried on the
                        # next notification and fail the same way, so this is
                        # worth seeing rather than discarding.
                        logger.warning(
                            'WebPush subscription %s reported %s but could not be deleted',
                            sub.pk,
                            status,
                            exc_info=True,
                            extra={'operation': 'web_push_send', 'result': 'cleanup_failed'},
                        )
                elif status is not None and 300 <= status < 400:
                    # _NoRedirectSession did not follow it, so pywebpush saw the
                    # 3xx as a failure (it raises on anything over 202). Logged
                    # distinctly because a redirect off an allow-listed host is
                    # how endpoint validation would be bypassed, not routine.
                    logger.warning(
                        'WebPush subscription %s answered %s; redirect not followed',
                        sub.pk,
                        status,
                        extra={'operation': 'web_push_send', 'result': 'redirect_refused'},
                    )
                else:
                    logger.warning('WebPush send failed (%s): %s', status, exc)
            except requests.Timeout:
                logger.warning(
                    'WebPush subscription %s timed out after %ss',
                    sub.pk,
                    PUSH_TIMEOUT_SECONDS,
                    extra={'operation': 'web_push_send', 'result': 'timeout'},
                )
            except Exception as exc:  # pragma: no cover
                logger.warning('WebPush send error: %s', exc)
    return delivered
