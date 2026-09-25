"""IP allow-listing for the unsigned Telebirr SOAP webhooks.

The problem
-----------
Three Telebirr callbacks -- B2C payout results, direct-debit results and USSD
purchase results -- arrive as SOAP envelopes carrying no signature of any
kind. The coin callback is different: it is signed, and that signature is
verified. These three have nothing to verify.

What protects them today is that each handler takes the row lock, checks the
transaction is still in the state a callback may advance, and refuses
otherwise -- so a replay settles nothing twice. What that does *not* stop is
a first, forged callback: anyone who can guess an ``OriginatorConversationID``
can mark a payout succeeded that Telebirr never made.

Why this is here and not only at the ingress
--------------------------------------------
The real fix is an allow-list at the ingress, and that remains the
recommendation -- a request refused by nginx never reaches Python. But the
ingress is operated separately from this code, an allow-list that exists only
in an nginx config is invisible to everybody reading the handler, and a
misconfigured ingress fails open silently. This is defence in depth: the same
rule, stated where the handler can be read, verifiable by a test.

Failing open by default, deliberately
-------------------------------------
``TELEBIRR_WEBHOOK_ALLOWED_IPS`` is empty by default and an empty list allows
everything -- exactly what happens today. This has to be opt-in: shipping a
populated default would mean guessing Telebirr's egress addresses, and a
wrong guess silently drops real payout confirmations, which is a worse
failure than the one being fixed. Set it once the addresses are confirmed
with Telebirr.

Addresses go in settings, never in code: they are deployment configuration
and they change without a release.
"""

from __future__ import annotations

import ipaddress
import logging

from django.conf import settings

from common.security.client_ip import get_client_ip

logger = logging.getLogger(__name__)

SETTING_NAME = 'TELEBIRR_WEBHOOK_ALLOWED_IPS'


def _configured_networks():
    """Parsed allow-list, or an empty list when unconfigured.

    Accepts a list or a comma-separated string, because environment-driven
    settings arrive as strings and a list is easier to read in Python
    settings. An unparseable entry is dropped with a warning rather than
    taking the process down -- but it is logged loudly, because a typo in an
    allow-list is a hole in it.
    """
    raw = getattr(settings, SETTING_NAME, None) or []
    if isinstance(raw, str):
        raw = raw.split(',')

    networks = []
    for entry in raw:
        entry = (entry or '').strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning(
                'WEBHOOK_ALLOWLIST_BAD_ENTRY setting=%s entry=%r ignored', SETTING_NAME, entry
            )
    return networks


def is_configured():
    """Whether an allow-list has been set at all."""
    return bool(_configured_networks())


def ip_allowed(ip_str):
    """Whether ``ip_str`` may deliver a webhook.

    True when no allow-list is configured -- see the module docstring on why
    the default is open.
    """
    networks = _configured_networks()
    if not networks:
        return True

    try:
        ip = ipaddress.ip_address((ip_str or '').strip())
    except ValueError:
        # An allow-list is configured and we cannot tell who this is. With a
        # list in force the safe answer is no.
        return False

    return any(ip in network for network in networks)


def request_allowed(request):
    """Whether this request may deliver a webhook.

    Resolves the caller through ``common.security.client_ip``, which honours
    ``X-Forwarded-For`` only from a configured trusted proxy -- without that,
    an allow-list is bypassed by setting a header.
    """
    return ip_allowed(get_client_ip(request))


def refuse(request, *, webhook):
    """The refusal to return, or ``None`` when the caller is allowed.

    Returns a DRF ``Response`` so a view can ``return`` it directly::

        denied = refuse(request, webhook='telebirrB2C')
        if denied is not None:
            return denied

    Kept as a helper rather than a decorator because these views are already
    wrapped in ``@api_view`` and ``@permission_classes``, and another layer
    between them and the function obscures which one answered.
    """
    if request_allowed(request):
        return None

    from rest_framework import status
    from rest_framework.response import Response

    logger.warning(
        'WEBHOOK_IP_REFUSED webhook=%s ip=%s -- not in %s',
        webhook,
        get_client_ip(request),
        SETTING_NAME,
    )
    return Response({'success': False, 'error': 'Not permitted'}, status=status.HTTP_403_FORBIDDEN)
