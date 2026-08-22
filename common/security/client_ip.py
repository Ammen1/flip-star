"""
Secure client-IP resolution.

``X-Forwarded-For`` is trivially spoofable by any direct caller -- trusting
it unconditionally lets an attacker set any IP they like and bypass IP-based
rate limiting or IP-based audit logging entirely. It can only be trusted
when the *immediate* TCP peer (``REMOTE_ADDR``) is a proxy this deployment
actually controls (nginx, a load balancer); anything else -- including a
value forwarded by an untrusted upstream -- must be ignored.

Configure ``settings.TRUSTED_PROXY_IPS`` with the IP(s)/CIDR range(s) of your
own reverse proxy. Defaults to loopback only (``127.0.0.1``, ``::1``), which
is correct when nginx runs on the same host or Docker network as this
process -- the common case for this project's deployment. An empty list
means "trust nothing": :func:`get_client_ip` then always returns
``REMOTE_ADDR``, same as ignoring the header entirely.
"""

from __future__ import annotations

import ipaddress

from django.conf import settings


def _parse_networks(raw) -> list:
    networks = []
    for entry in raw:
        entry = (entry or '').strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return networks


def _is_trusted(ip_str: str, networks: list) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def get_client_ip(request) -> str:
    """
    The caller's real IP address, honoring ``X-Forwarded-For`` only when the
    direct connection came from a configured trusted proxy.
    """
    remote_addr = request.META.get('REMOTE_ADDR', '') or ''
    trusted_networks = _parse_networks(getattr(settings, 'TRUSTED_PROXY_IPS', []))

    if not trusted_networks or not _is_trusted(remote_addr, trusted_networks):
        return remote_addr

    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if not forwarded_for:
        return remote_addr

    # Each proxy hop prepends the address it saw its client connect from, so
    # reading right-to-left: the first entry that is NOT itself one of our
    # trusted proxies is the real client. Anything further left could have
    # been supplied by that untrusted client and is not trustworthy.
    hops = [h.strip() for h in forwarded_for.split(',') if h.strip()]
    for hop in reversed(hops):
        if not _is_trusted(hop, trusted_networks):
            return hop

    # Every hop claimed to be a trusted proxy, or the header was malformed --
    # nothing left we can trust as the client.
    return remote_addr
