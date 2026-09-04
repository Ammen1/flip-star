"""
Telling "this customer has no Telebirr account" apart from every other payment
failure.

How registration is actually determined
---------------------------------------
It is not looked up. There is no endpoint that answers "is this MSISDN
registered", and nothing in our data records it -- a user's registration state
lives entirely on Telebirr's side and changes without telling us.

The only signal is the ``<res:ResponseCode>`` on an attempted payment:
``0`` means the push was accepted, anything else is a failure carrying a
``<res:ResponseDesc>``. So the flow is necessarily "try, then interpret",
and this module is the interpreter.

That is also why the check is inherently server-side. A client cannot be
asked whether its user is registered, because the client cannot know -- and a
client that *claimed* to know would be asserting something only the provider
can answer. ``UNREGISTERED_RESPONSE_CODES`` is never read from a request.

Why the codes are configuration, not constants
----------------------------------------------
We do not have Telebirr's authoritative code list. Hardcoding a guess would be
worse than useless: mislabelling a gateway timeout as "you need to register"
sends a paying customer to sign up for an account they already have, and hides
a real outage behind a friendly message.

So the list is empty by default -- unknown codes fall through to the ordinary
error path, exactly as they do today -- and is populated by configuration once
Telebirr confirms the codes. Set TELEBIRR_UNREGISTERED_CODES to a comma
separated list, e.g. "2001,4001". Description matching is available as a
fallback for the same reason: some gateways return a generic code and put the
detail in the text.

Nothing here changes what is charged or credited. It only classifies a failure
that has already happened, so a wrong entry in the list produces a wrong
message, never a wrong debit.
"""

from __future__ import annotations

import logging
import re

# Vault first, .env only as a fallback -- reading decouple directly here would
# bypass the secrets layer, which tests/unit/test_no_hardcoded_secrets.py
# enforces. Same import style as infrastructure/storage/config.py.
from infrastructure.secrets import secret as config

logger = logging.getLogger(__name__)

#: Response codes that mean the customer has no Telebirr account.
#:
#: Empty until Telebirr confirms them. An unrecognised failure is reported as
#: an ordinary payment error rather than being guessed at.
UNREGISTERED_RESPONSE_CODES = frozenset(
    code.strip()
    for code in config('TELEBIRR_UNREGISTERED_CODES', default='').split(',')
    if code.strip()
)

#: Case-insensitive phrases in ResponseDesc that indicate the same thing.
#:
#: A fallback for gateways that return a generic code with the detail in the
#: text. Deliberately narrow: broad matching on words like "invalid" would
#: catch malformed-request failures, which have nothing to do with
#: registration.
UNREGISTERED_DESC_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r'\bnot\s+regist',
        r'\bunregistered\b',
        r'\bno\s+such\s+(customer|subscriber|user)\b',
        r'\bcustomer\s+(does\s+not\s+exist|not\s+found)\b',
        r'\bsubscriber\s+(does\s+not\s+exist|not\s+found)\b',
    )
]

#: The code the client switches on to show the registration prompt.
NOT_REGISTERED_CODE = 'TELEBIRR_NOT_REGISTERED'

#: What the user is told to do. A short code rather than a URL: registration
#: happens on the handset, and a link would send them somewhere that cannot
#: complete it.
REGISTRATION_SHORTCODE = config('TELEBIRR_REGISTRATION_SHORTCODE', default='*127#')


def is_unregistered_failure(result: dict) -> bool:
    """True when a failed initiation was refused for want of an account.

    ``result`` is what ``initiate_ussd_push_payment`` returns. A successful
    result is never classified -- registration is only ever inferred from a
    refusal.
    """
    if not result or result.get('success'):
        return False

    code = str(result.get('response_code') or '').strip()
    if code and code in UNREGISTERED_RESPONSE_CODES:
        return True

    desc = str(result.get('error') or '')
    return any(pattern.search(desc) for pattern in UNREGISTERED_DESC_PATTERNS)


def registration_required_payload(package=None) -> dict:
    """The response that drives the registration prompt.

    Carries the package so the client can restore the user's selection after
    they register, rather than dropping them back on an empty list having
    forgotten what they were buying.

    Contains no provider text. ``ResponseDesc`` echoes request fields and
    internal identifiers, so it goes to the log and never to the client.
    """
    payload = {
        'success': False,
        'code': NOT_REGISTERED_CODE,
        'error': 'This phone number is not registered with telebirr.',
        'title': 'Register with telebirr to continue',
        'explanation': (
            'Your payment could not be started because this phone number does '
            'not have a telebirr account yet.'
        ),
        'benefit': (
            'Registering takes about a minute and lets you buy coins and '
            'subscribe directly from your phone balance, with no card needed.'
        ),
        'action': {
            'label': f'Dial {REGISTRATION_SHORTCODE}',
            'type': 'ussd',
            'value': REGISTRATION_SHORTCODE,
        },
        'dismissible': True,
    }

    if package is not None:
        # Echoed back so the client can resume this exact purchase. Read from
        # the CoinPackage row, not from the request that started it.
        payload['pending_package'] = {
            'id': package.id,
            'name': package.name,
            'price_etb': str(package.price_etb),
            'total_coins': package.get_total_coins(),
        }

    return payload


def classify_initiation_failure(result: dict, package=None) -> tuple[dict, str]:
    """Turn a failed initiation into (client payload, log message).

    One place decides what the user sees, so the registration prompt and the
    ordinary error path cannot drift into disagreeing about the same failure.
    """
    provider_code = str(result.get('response_code') or 'none')
    provider_desc = str(result.get('error') or 'no description')

    if is_unregistered_failure(result):
        return (
            registration_required_payload(package),
            f'unregistered customer (code={provider_code})',
        )

    return (
        {
            'success': False,
            'code': 'PAYMENT_FAILED',
            'error': 'We could not start your payment. Please try again in a moment.',
        },
        f'provider refused (code={provider_code}, desc={provider_desc})',
    )
