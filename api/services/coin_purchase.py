"""
The contract the coin-purchase popup depends on.

Two failures look identical to a client that only reads HTTP status and prose:
"you are not signed in" and "you do not have enough coins". The popup has to
tell them apart -- one asks the user to sign in, the other offers packages --
so both carry a stable machine-readable ``code`` here rather than leaving the
client to pattern-match error text that changes.

``required_coins`` is authoritative and always computed server-side from
WalletConfig; the client never supplies the amount it is short by, and never
supplies the amount it is credited.
"""

INSUFFICIENT_COINS_CODE = 'INSUFFICIENT_COINS'
AUTH_REQUIRED_CODE = 'AUTH_REQUIRED'


def insufficient_coins_payload(required, balance, message=None, **extra):
    """The body every endpoint returns when it refuses for want of coins.

    `required` and `balance` are ints the server worked out; the popup renders
    the shortfall from them, so they must never be echoed from the request.
    """
    required = int(required or 0)
    balance = int(balance or 0)
    payload = {
        'success': False,
        'code': INSUFFICIENT_COINS_CODE,
        'error': message or (
            f'You need {required} coins for this and have {balance}.'
        ),
        'required_coins': required,
        'current_coins': balance,
        'shortfall': max(required - balance, 0),
        # Kept for older clients that branch on this flag.
        'needs_recharge': True,
    }
    payload.update(extra)
    return payload


def auth_required_payload(message=None):
    """Returned when an action needs a signed-in user.

    Distinct from INSUFFICIENT_COINS on purpose: the popup must not offer coin
    packages to someone whose real problem is an expired session.
    """
    return {
        'success': False,
        'code': AUTH_REQUIRED_CODE,
        'error': message or 'Please sign in to continue.',
    }
