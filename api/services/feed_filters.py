"""
Category and time-window filters for the trending feeds.

/explorer/trending/ (the web Explore page, and the mobile Explore screen) and
/reels/trending/ both take ?category= and used to read it differently: one
rejected an unknown slug, the other silently served every post -- so a
category whose slug did not match looked exactly like a filter that "does
nothing". Both now resolve through here.

``category`` accepts:
  - nothing, ``all`` or ``trending``  -> no category filter. ``trending`` is
                                         what the mobile Explore screen sends
                                         for its only tab.
  - a category id (``5``)             -> preferred; ids survive renames.
  - a category slug (``dance``)       -> still accepted for existing clients.
An unknown or inactive category raises InvalidCategory: the view answers 400
rather than pretending the filter ran.
"""

from datetime import timedelta

from rest_framework import status
from rest_framework.response import Response

NO_CATEGORY_VALUES = frozenset({'', 'all', 'trending'})
MAX_PK = 2**31 - 1

# The windows the clients offer. Anything else keeps the explorer's historical
# fallback of a year, so an unexpected value still returns a sensible feed.
TIME_WINDOWS = {
    '24h': timedelta(hours=24),
    '7d': timedelta(days=7),
    '30d': timedelta(days=30),
}
FALLBACK_WINDOW = timedelta(days=365)


class InvalidCategory(Exception):
    def __init__(self, value):
        super().__init__(value)
        self.value = value


def resolve_category(raw):
    """The active Category that ``raw`` names, or None for "all categories"."""
    from api.models import Category

    value = (raw or '').strip()
    if value.lower() in NO_CATEGORY_VALUES:
        return None
    active = Category.objects.filter(is_active=True)
    if value.isascii() and value.isdigit():
        # Beyond the integer column the database would raise, not miss.
        pk = int(value)
        category = active.filter(pk=pk).first() if pk <= MAX_PK else None
    else:
        category = active.filter(slug=value).first()
    if category is None:
        raise InvalidCategory(value)
    return category


def invalid_category_response(value):
    return Response(
        {
            'error': 'Unknown or inactive category.',
            'code': 'invalid_category',
            'category': value,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def window_start(raw, now):
    """Earliest created_at the ``time_range`` value lets through."""
    return now - TIME_WINDOWS.get((raw or '').strip(), FALLBACK_WINDOW)


def bounded_int(raw, default, low, high):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(value, high))
