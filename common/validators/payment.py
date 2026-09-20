"""
Which payment methods a coin purchase may use.

The rule, and the only place it is defined on the server:

    0 < price <= 10 ETB  ->  telebirr or airtime
        price >  10 ETB  ->  telebirr only

Airtime used to be permitted at *exactly* 10 ETB, which offered it for the one
10 ETB package and for nothing else -- a custom 5 ETB purchase, which costs the
buyer less, could not use it. The limit is a ceiling, not a price.

The client mirrors this in ``Flipstar-web/pages/wallet/BuyCoinsPage.jsx``, but
the client is a convenience, not the authority -- a request that names
``airtime`` for a 50 ETB package must be refused here regardless of what the UI
allowed.

Note on the current state of airtime
------------------------------------
``purchase_coins_on_demand`` (POST /charging/coin-purchase/) returns 403 for
every request: airtime coin purchase was deliberately switched off so that
Ethio Telecom SIM cards are used solely for SMS OTP verification. This module
does not change that. It defines the price rule so that the constraint is
explicit and enforced *before* that block, and so re-enabling airtime is a
one-line decision that cannot accidentally ship without the price limit.
"""

from decimal import Decimal, InvalidOperation

from common.exceptions import ValidationError

TELEBIRR = 'telebirr'
AIRTIME = 'airtime'

#: The most a purchase may cost and still be payable from airtime.
AIRTIME_MAX_ETB = Decimal('10')

#: The old name, from when the rule was an exact price rather than a ceiling.
#: Kept so an importer of it does not break; both refer to the same 10 ETB.
AIRTIME_PRICE_ETB = AIRTIME_MAX_ETB

SUPPORTED_METHODS = (TELEBIRR, AIRTIME)


def _as_decimal(price):
    try:
        return Decimal(str(price))
    except (InvalidOperation, TypeError, ValueError):
        return None


def allowed_pay_methods(price_etb):
    """The methods permitted at `price_etb`.

    Airtime is allowed up to and including the ceiling. Zero and negative
    amounts are not purchases and are excluded explicitly -- without that, a
    price of -1 would satisfy "at most 10" and widen what is allowed.

    An unparseable price yields telebirr only -- the restrictive answer, so a
    malformed amount can never widen what is allowed either.
    """
    amount = _as_decimal(price_etb)
    if amount is not None and Decimal('0') < amount <= AIRTIME_MAX_ETB:
        return [TELEBIRR, AIRTIME]
    return [TELEBIRR]


def validate_pay_method(method, price_etb):
    """Raise ``ValidationError`` unless `method` is permitted at `price_etb`."""
    normalised = str(method or '').strip().lower()

    if normalised not in SUPPORTED_METHODS:
        raise ValidationError('Unsupported payment method. Choose telebirr or airtime.')

    if normalised not in allowed_pay_methods(price_etb):
        # Formatted with :g rather than Decimal.normalize(), which renders 10
        # as '1E+1' and would put that in front of a user.
        raise ValidationError(
            f'Airtime can only be used for purchases of {AIRTIME_MAX_ETB:g} ETB or less. '
            'Please pay with telebirr.'
        )

    return normalised
