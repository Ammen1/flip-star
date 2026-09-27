"""Validation for browser-supplied Web Push endpoints.

Audit finding H-07. ``POST /api/v1/push/subscribe/`` stores whatever
``endpoint`` URL the caller sends, and the server later POSTs to it. Two things
followed from that:

* **SSRF.** The destination was user-controlled and the egress NetworkPolicy is
  deliberately unrestricted (``k8s/base/networkpolicy.yaml``), so in-cluster
  addresses -- Vault on 8200, PostgreSQL, Redis -- were reachable. Blind, since
  the body is encrypted to the subscription's keys and no response is returned
  to the caller, but reachable.
* **Denial of service.** ``pywebpush`` was called with no timeout, so a host
  that accepts a connection and never answers held the calling thread forever.

The timeout lives in ``webpush.py``; this module is the destination control.

Why a host allow-list is the primary control
--------------------------------------------
Web Push endpoints are not arbitrary: the browser chooses them, and each
browser has one push service. Chrome and the Chromium family get
``fcm.googleapis.com``, Firefox gets ``updates.push.services.mozilla.com``,
Safari gets ``web.push.apple.com``, older Edge gets a ``*.notify.windows.com``
shard. A subscription naming anything else did not come from a browser.

This also settles DNS rebinding, which an IP-based check cannot. Validating a
resolved address at subscribe time proves nothing about what the name resolves
to at send time -- that is the rebinding attack, and it is why "resolve, then
check the IP" is not a control. Pinning the name instead means an attacker has
to make ``fcm.googleapis.com`` itself resolve somewhere internal, which needs
control of the resolver, and an attacker with that has better options than this
endpoint. So: no DNS lookup happens here, deliberately, and none is needed.

The IP-literal and private-range checks below are therefore defence in depth,
not the load-bearing control. They exist for the deployment that widens
``PUSH_ALLOWED_ENDPOINT_HOSTS`` -- a self-hosted autopush, say -- and would
otherwise have no protection at all.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from django.conf import settings

#: Push services real browsers use. An entry starting with '.' matches any
#: subdomain of that suffix; anything else must match the host exactly.
#:
#: Deliberately not a wildcard and deliberately not empty-means-everything --
#: audit finding M-11 is what an "empty list allows all" default looks like in
#: production.
DEFAULT_ALLOWED_PUSH_HOSTS: tuple[str, ...] = (
    # Chrome, Edge (current), Brave, Opera, Samsung Internet
    'fcm.googleapis.com',
    # Firefox
    'updates.push.services.mozilla.com',
    # Mozilla autopush shards
    '.push.services.mozilla.com',
    # Safari / iOS 16.4+ web push
    'web.push.apple.com',
    # Edge (legacy WNS)
    '.notify.windows.com',
)

#: The model column is URLField(max_length=600); reject before the database does.
MAX_ENDPOINT_LENGTH = 600


class PushEndpointRejected(ValueError):
    """A subscription endpoint failed validation.

    ``reason`` is a short machine code for the API response; ``str(exc)`` is the
    human-readable detail for logs. Neither echoes the rejected URL back to the
    caller.
    """

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def allowed_hosts() -> tuple[str, ...]:
    """The configured allow-list, falling back to the known browser services.

    An explicitly empty setting falls back to the defaults rather than allowing
    everything: a misconfiguration should not silently reopen H-07.
    """
    configured = getattr(settings, 'PUSH_ALLOWED_ENDPOINT_HOSTS', None) or ()
    cleaned = tuple(h.strip().lower() for h in configured if h and h.strip())
    return cleaned or DEFAULT_ALLOWED_PUSH_HOSTS


def host_is_allowed(host: str, allowlist: tuple[str, ...] | None = None) -> bool:
    """True when ``host`` matches the allow-list exactly or by dotted suffix.

    The suffix form requires a leading dot so that an entry of
    ``.notify.windows.com`` matches ``abc.notify.windows.com`` but never
    ``evilnotify.windows.com``.
    """
    host = (host or '').strip().lower().rstrip('.')
    if not host:
        return False
    for entry in allowlist if allowlist is not None else allowed_hosts():
        if entry.startswith('.'):
            if host.endswith(entry) and len(host) > len(entry):
                return True
        elif host == entry:
            return True
    return False


def _reject_if_blocked_ip(host: str) -> None:
    """Reject a host written as an IP literal in a range that must not be reached.

    Only reachable when the allow-list has been widened to permit an IP, since
    no browser push service is an IP literal.
    """
    try:
        ip = ipaddress.ip_address(host.strip('[]'))
    except ValueError:
        return  # not an IP literal; the allow-list is what governs names

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise PushEndpointRejected(
            'endpoint_host_not_routable',
            f'endpoint host {ip} is in a non-routable range',
        )
    # 169.254.169.254 is link-local and already caught above; this covers the
    # IPv6 spelling of the same idea.
    if isinstance(ip, ipaddress.IPv6Address) and (ip.ipv4_mapped or ip.sixtofour):
        raise PushEndpointRejected(
            'endpoint_host_not_routable',
            f'endpoint host {ip} wraps an IPv4 address',
        )


def validate_push_endpoint(raw: object) -> str:
    """Return ``raw`` as a trusted endpoint URL, or raise ``PushEndpointRejected``.

    Checks, in order, so the error names the first real problem:

    1. present, a string, and within the column width
    2. parses, with a scheme and a host
    3. scheme is exactly https -- no http, no file, no gopher
    4. no embedded credentials, which is how ``https://fcm.googleapis.com@evil``
       reads as one host to a human and another to a URL parser
    5. no port other than 443
    6. not an IP literal in a non-routable range
    7. host is on the allow-list
    """
    if raw is None or not isinstance(raw, str) or not raw.strip():
        raise PushEndpointRejected('endpoint_required', 'endpoint is required')

    endpoint = raw.strip()
    if len(endpoint) > MAX_ENDPOINT_LENGTH:
        raise PushEndpointRejected(
            'endpoint_too_long',
            f'endpoint exceeds {MAX_ENDPOINT_LENGTH} characters',
        )

    try:
        parts = urlsplit(endpoint)
    except ValueError as exc:
        raise PushEndpointRejected('endpoint_malformed', 'endpoint is not a URL') from exc

    if not parts.scheme or not parts.netloc:
        raise PushEndpointRejected('endpoint_malformed', 'endpoint is not an absolute URL')

    if parts.scheme.lower() != 'https':
        raise PushEndpointRejected(
            'endpoint_scheme_not_https',
            f'endpoint scheme {parts.scheme!r} is not https',
        )

    if parts.username or parts.password or '@' in parts.netloc:
        raise PushEndpointRejected(
            'endpoint_has_credentials',
            'endpoint must not embed credentials',
        )

    try:
        port = parts.port
    except ValueError as exc:
        raise PushEndpointRejected('endpoint_malformed', 'endpoint port is not a number') from exc
    if port is not None and port != 443:
        raise PushEndpointRejected(
            'endpoint_port_not_allowed',
            f'endpoint port {port} is not 443',
        )

    host = (parts.hostname or '').lower()
    if not host:
        raise PushEndpointRejected('endpoint_malformed', 'endpoint has no host')

    _reject_if_blocked_ip(host)

    if not host_is_allowed(host):
        raise PushEndpointRejected(
            'endpoint_host_not_allowed',
            f'endpoint host {host} is not a known push service',
        )

    return endpoint
