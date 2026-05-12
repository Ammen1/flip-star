"""Web Push (VAPID) sender.

Wraps `pywebpush` so callers can fire-and-forget notifications to all of a
user's PushSubscriptions. Subscriptions that the browser has revoked
(HTTP 404 / 410) are deleted automatically.

Configure VAPID keys via env vars (see `config/settings.py`).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


def _vapid_claims() -> Optional[dict]:
    if not _resolve_private_key():
        return None
    return {"sub": settings.VAPID_SUBJECT}


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
            with open(raw, 'r') as f:
                return f.read()
    except Exception:
        pass
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
        logger.warning("pywebpush not installed; skipping push send")
        return 0

    from .models import PushSubscription

    subs = list(PushSubscription.objects.filter(user=user))
    if not subs:
        return 0

    body = json.dumps(payload)
    delivered = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=body,
                vapid_private_key=_resolve_private_key(),
                vapid_claims=dict(claims),
            )
            delivered += 1
        except WebPushException as exc:  # type: ignore[misc]
            status = getattr(exc.response, "status_code", None) if exc.response else None
            if status in (404, 410):
                # Subscription expired/unsubscribed — clean up.
                try:
                    sub.delete()
                except Exception:
                    pass
            else:
                logger.warning("WebPush send failed (%s): %s", status, exc)
        except Exception as exc:  # pragma: no cover
            logger.warning("WebPush send error: %s", exc)
    return delivered
