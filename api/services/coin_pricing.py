"""
What a given amount of birr buys in coins.

Packages answered this until now: each `CoinPackage` row names a price and the
coins that come with it, so there was never a rate to state -- only five fixed
offers. A buyer who wants to spend 5 birr, or 37, has no package to pick, and
this is the rule that serves them.

## The rate is derived, never written down

Every active package prices its base coins identically -- 10 coins per birr at
the time of writing -- and differs only in the *bonus* on top, which grows with
the size of the purchase. So the base rate is already stated, five times over,
by the packages themselves. `base_coins_per_birr()` reads it back off them
rather than introducing a sixth place where it could be set and then disagree.

Two consequences worth being explicit about:

* **`WalletConfig.coins_per_birr` is not this rate.** It is the *withdrawal*
  rate -- 100 coins to 1 ETB -- and it sits in the withdrawal section of the
  config for that reason. Buying at the withdrawal rate would let anybody turn
  10 birr into 10 birr's worth of withdrawable coins and back again. Using it
  here would be a money bug, not a rounding difference.

* **A custom amount earns no bonus.** The bonus is what a package is *for*: it
  is the reward for committing to a bigger tier. If custom amounts carried it,
  the packages would be strictly worse than typing their own price in, and the
  tiers would stop meaning anything.

Which leaves one edge worth handling kindly: somebody typing exactly 50 when a
50-birr package exists should not quietly get 500 coins instead of the 575 the
package offers. `quote()` spots that and hands back the package, so they get
the better deal and the purchase runs down the ordinary package path.

## The server is the authority

`quote()` is called twice for every custom purchase: once so the page can show
a figure while the buyer types, and again inside the purchase endpoint, which
ignores whatever the client believed. The client is told the rate rather than
having it compiled in, so the two agree -- but only one of them decides.
"""

from decimal import ROUND_DOWN, Decimal, InvalidOperation

#: Amounts are money: two decimal places, and never rounded up in the buyer's
#: favour when converting to whole coins.
TWO_PLACES = Decimal('0.01')


class CoinPricingError(ValueError):
    """A quote that cannot be honoured, with a message fit to show a buyer."""

    def __init__(self, message, *, code):
        super().__init__(message)
        self.code = code


def _active_packages():
    from api.models.contest import CoinPackage

    return list(CoinPackage.objects.filter(is_active=True).exclude(price_etb__lte=0))


def base_coins_per_birr(packages=None):
    """Coins per birr before any bonus, read off the packages.

    Every package should agree. If they ever disagree -- someone reprices one
    tier and not the others -- the *lowest* rate wins, because the alternative
    is selling custom amounts more cheaply than the packages and letting people
    arbitrage the difference.

    Returns None when there is nothing to derive a rate from, which is the
    honest answer: with no packages there is no established price, and
    `quote()` refuses rather than inventing one.
    """
    rows = _active_packages() if packages is None else list(packages)
    rates = []
    for p in rows:
        price = Decimal(str(p.price_etb))
        if price <= 0 or not p.coin_amount:
            continue
        rates.append(Decimal(p.coin_amount) / price)
    if not rates:
        return None
    return min(rates)


def limits(config=None):
    """The smallest and largest custom purchase allowed, as Decimals."""
    if config is None:
        from api.models.wallet import WalletConfig

        config = WalletConfig.get_config()
    return (
        Decimal(str(config.custom_purchase_min_etb)),
        Decimal(str(config.custom_purchase_max_etb)),
    )


def parse_amount(raw):
    """Read a buyer's input as money, or refuse it.

    Accepts what a number field produces -- '5', '5.5', 5, Decimal('5.00') --
    and rejects everything else by name, so the caller can say which rule was
    broken rather than 'invalid'.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise CoinPricingError('Enter an amount in Birr.', code='amount_required')
    try:
        amount = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CoinPricingError('Enter a valid amount in Birr.', code='amount_invalid') from exc
    if not amount.is_finite():
        raise CoinPricingError('Enter a valid amount in Birr.', code='amount_invalid')
    if amount <= 0:
        raise CoinPricingError('Enter an amount greater than 0.', code='amount_not_positive')
    if amount.as_tuple().exponent < -2:
        raise CoinPricingError(
            'Amounts can have at most 2 decimal places.', code='amount_too_precise'
        )
    return amount.quantize(TWO_PLACES)


def quote(raw_amount, *, config=None, packages=None):
    """What `raw_amount` buys. Raises CoinPricingError if it buys nothing.

    Returns a dict:
        amount_etb  Decimal, normalised to 2 places -- what will be charged
        coins       int, what will be credited
        package     the CoinPackage whose price this matches, or None
        bonus_coins int, 0 unless a package matched

    Coins are rounded **down**. 5.55 birr at 10 coins/birr is 55 coins, not 56:
    the buyer is never credited a fraction of a coin they did not pay for.
    """
    amount = parse_amount(raw_amount)

    low, high = limits(config)
    if amount < low:
        raise CoinPricingError(
            f'The smallest purchase is {_money(low)} Birr.', code='below_minimum'
        )
    if amount > high:
        raise CoinPricingError(
            f'The largest purchase is {_money(high)} Birr.', code='above_maximum'
        )

    rows = _active_packages() if packages is None else list(packages)

    # Exactly a package price: give them the package, bonus and all.
    for p in rows:
        if Decimal(str(p.price_etb)).quantize(TWO_PLACES) == amount:
            return {
                'amount_etb': amount,
                'coins': p.get_total_coins(),
                'package': p,
                'bonus_coins': p.bonus_coins,
            }

    rate = base_coins_per_birr(rows)
    if not rate:
        raise CoinPricingError(
            'Coin pricing is unavailable right now. Please try again later.',
            code='pricing_unavailable',
        )

    coins = int((amount * rate).to_integral_value(rounding=ROUND_DOWN))
    if coins <= 0:
        raise CoinPricingError(
            f'{_money(amount)} Birr is too small to buy a coin.', code='below_minimum'
        )

    return {'amount_etb': amount, 'coins': coins, 'package': None, 'bonus_coins': 0}


def public_pricing(config=None):
    """The rate and limits, for a client to show a figure while somebody types.

    The client is handed the rate instead of compiling one in, so its
    arithmetic matches this module's by construction. It is still only a
    display: `quote()` decides what is actually sold.
    """
    low, high = limits(config)
    rate = base_coins_per_birr()
    return {
        'enabled': rate is not None,
        'coins_per_birr': str(rate) if rate is not None else None,
        'min_etb': _money(low),
        'max_etb': _money(high),
        'decimal_places': 2,
    }


def _money(value):
    return str(Decimal(value).quantize(TWO_PLACES))
