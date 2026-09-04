"""
The coin packages offered for Telebirr purchase.

One source of truth
-------------------
This list previously existed twice: once in
``api/management/commands/seed_coin_packages.py`` and again, hardcoded, as the
fallback in ``api/views/wallet.py:get_wallet_config`` for when the CoinPackage
table is empty. The seed command's own comment noted it was written to match
that fallback -- an arrangement that only holds while somebody remembers to
edit both. Changing one and not the other means the price a user is shown and
the price they are charged can disagree, which is the worst possible place for
a copy-paste to rot.

Both now import ``COIN_PACKAGES`` from here.

Not a security boundary
-----------------------
This is display and seeding data. It is deliberately NOT consulted when a
payment is priced: ``telebirr_initiate_payment`` and the USSD flow both take
only a ``package_id``, load the CoinPackage row, and read ``price_etb`` off
it. A client that posts a price or a coin amount is ignored, so the amount
charged always comes from the database rather than from this file or from the
request.

Prices are the five amounts Telebirr is configured for: 10, 50, 100, 250 and
500 ETB. Adding a sixth means agreeing it with Telebirr first -- an amount
they do not recognise is rejected at their gateway, after the user has already
confirmed the USSD prompt.
"""

#: Base rate, before any bonus. Every package grants ``price_etb * RATE`` coins.
COINS_PER_ETB = 10

#: name, price, coins, bonus, featured, order.
#:
#: The bonus climbs with the tier (0%, 15%, 20%, 25%, 30%) so larger purchases
#: carry a visible advantage. ``price_etb`` is the identity used by the seed's
#: update_or_create, so changing a price creates a new row rather than editing
#: one -- rename freely, but treat the price as the key.
COIN_PACKAGES = [
    {
        'name': 'Starter Pack',
        'price_etb': 10,
        'coin_amount': 100,
        'bonus_coins': 0,
        'is_featured': False,
        'sort_order': 1,
    },
    {
        'name': 'Most Popular',
        'price_etb': 50,
        'coin_amount': 500,
        'bonus_coins': 75,
        'is_featured': True,
        'sort_order': 2,
    },
    {
        'name': 'Best Deal',
        'price_etb': 100,
        'coin_amount': 1000,
        'bonus_coins': 200,
        'is_featured': False,
        'sort_order': 3,
    },
    {
        'name': 'Premium Package',
        'price_etb': 250,
        'coin_amount': 2500,
        'bonus_coins': 625,
        'is_featured': False,
        'sort_order': 4,
    },
    {
        'name': 'Ultimate Package',
        'price_etb': 500,
        'coin_amount': 5000,
        'bonus_coins': 1500,
        'is_featured': False,
        'sort_order': 5,
    },
]

#: The prices Telebirr accepts, for validation and for deactivating rows that
#: are no longer offered.
SUPPORTED_PRICES = frozenset(p['price_etb'] for p in COIN_PACKAGES)


def fallback_payload():
    """The package list shaped as ``get_wallet_config`` serves it.

    Used only when the CoinPackage table cannot be read -- a fresh database
    before the seed has run, or a migration in flight. ``id`` is the price
    rather than a row id, because no row exists to have one; the frontend uses
    it solely as a React key in that state, and any purchase attempt goes
    through the real table.
    """
    return [
        {
            'id': pkg['price_etb'],
            'name': pkg['name'],
            'price_etb': f'{pkg["price_etb"]}.0',
            'coin_amount': pkg['coin_amount'],
            'bonus_coins': pkg['bonus_coins'],
            'total_coins': pkg['coin_amount'] + pkg['bonus_coins'],
            'is_featured': pkg['is_featured'],
        }
        for pkg in COIN_PACKAGES
    ]


# ---------------------------------------------------------------------------
# Duplicate-purchase guard
# ---------------------------------------------------------------------------

#: How long after a USSD push a repeat tap counts as a double-tap rather than a
#: deliberate second purchase. Long enough to cover a confirmation that is
#: merely slow; short enough that a push the user ignored does not lock them
#: out of buying coins at all.
PENDING_PURCHASE_WINDOW_SECONDS = 10 * 60


def pending_coin_purchase(user, package=None, within_seconds=None):
    """A USSD coin purchase already awaiting confirmation, or None.

    Nothing stopped a second tap from firing a second USSD push: the view
    validated the package, called Telebirr, and created a pending row every
    time. Two pushes means two prompts on the handset and two debits if the
    user confirms both -- and because each carries its own
    OriginatorConversationID, both callbacks credit successfully. The user is
    charged twice and the records look entirely correct.

    Matches only rows that actually reached Telebirr. A failed initiation is
    recorded for audit with no payment_reference, and must not block the retry
    it exists to document.
    """
    from datetime import timedelta

    from django.utils import timezone

    from api.models.contest import CoinTransaction

    window = PENDING_PURCHASE_WINDOW_SECONDS if within_seconds is None else within_seconds

    qs = CoinTransaction.objects.filter(
        user=user,
        transaction_type='purchase',
        payment_method='telebirr_ussd',
        is_successful=False,
        payment_reference__isnull=False,
        created_at__gte=timezone.now() - timedelta(seconds=window),
    ).exclude(payment_reference='')

    if package is not None:
        qs = qs.filter(package=package)

    return qs.order_by('-created_at').first()


def purchase_pending_payload(existing):
    """The refusal returned when a push is already outstanding.

    Carries the original conversation id so the client can resume polling the
    first attempt rather than treating this as a dead end.
    """
    return {
        'success': False,
        'code': 'PURCHASE_PENDING',
        'error': (
            'A payment request is already waiting for confirmation. '
            'Please check your phone, or wait a moment before trying again.'
        ),
        'originator_conversation_id': existing.payment_reference,
    }
