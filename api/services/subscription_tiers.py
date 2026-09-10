"""
Resolving which subscription tier an aggregator notification refers to.

Why a keyword fallback exists at all
------------------------------------
The obvious answer is the product id, and it is tried first. But the MA does
not always send a product id we hold: TIMWE and OneVAS front the same
products, and the ids they quote have not always matched what is stored on the
tiers. Real syncOrderRelation traffic has arrived with ``productID``
``1000030022`` and ``10000302850`` for the same catalogue.

The subscriber's own keyword is the more reliable signal in that case. A
subscriber texting ``1`` to the short code has said which plan they want, in
the only vocabulary the SMS channel has, and that intent does not depend on
whether two systems agree about an id.

This is the order the removed OneVAS webhook used -- product id, then SMS code
-- and with it gone this module is the only copy of the mapping.
"""

import re

from api.models import SubscriptionTier

#: SMS code to duration type, as the OneVAS webhook defined it.
#:
#: These are the digits a subscriber texts to the short code, not an internal
#: identifier -- ``1`` is "the daily plan" to the person sending it.
SMS_CODE_TO_DURATION = {
    '1': 'daily',
    '2': 'weekly',
    '3': 'monthly',
    '4': 'ondemand',
}


def duration_for_keyword(keyword: str) -> str | None:
    """The duration type a subscriber's SMS keyword asks for, or None.

    Accepts both shapes seen in real traffic: the bare digit (``1``), which is
    what the MA forwards in ``extensionInfo``, and the ``Ok1`` form the OneVAS
    code documents. A keyword carrying no digit at all -- ``Ok``, ``sub`` --
    expresses no choice of plan and resolves to None rather than guessing one.
    """
    if not keyword:
        return None
    digits = re.sub(r'\D', '', keyword)
    if not digits:
        return None
    return SMS_CODE_TO_DURATION.get(digits)


def resolve_tier(product_id: str = '', keyword: str = '') -> SubscriptionTier | None:
    """The tier a notification refers to, or None if nothing matches.

    Product id first, because it is exact when it is right. The keyword is
    consulted only when the id matched nothing, so a correct id is never
    overridden by a keyword that disagrees with it.
    """
    if product_id:
        tier = SubscriptionTier.objects.filter(product_id=product_id).first()
        if tier is not None:
            return tier

    duration = duration_for_keyword(keyword)
    if duration:
        # is_active matters here in a way it does not above: an id is a
        # specific tier, while a duration selects whichever tier currently
        # serves that plan, and a retired one must not be sold.
        return SubscriptionTier.objects.filter(duration_type=duration, is_active=True).first()

    return None
