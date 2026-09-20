"""
Ethiopian mobile number validation and normalisation.

One rule, one place. The subscriber part is nine digits beginning with 9
(Ethio Telecom) or 7 (Safaricom Ethiopia):

    ^[79]\\d{8}$

Accepted input, all meaning the same subscriber:

    944365493            bare national number
    0944365493           with the trunk prefix
    251944365493         with the country code
    +251944365493        E.164
    +251 94 436 5493     spaces and dashes are ignored

Rejected: anything else -- wrong length, a leading 8, letters anywhere, or a
doubled country code such as ``+251+251944365493`` / ``251251944365493``.

Storage format
--------------
``normalize_ethiopian_phone`` returns ``251XXXXXXXXX`` -- no ``+``. That is the
form already stored in ``UserProfile.phone_number`` and used for lookups, and
the form Onevas expects. Returning E.164 here would silently stop every
existing record matching, so ``to_e164`` is a separate helper for the API
surface and display, and switching storage to it would need a data migration.
"""

import re

# The subscriber part: nine digits, leading 9 (Ethio Telecom) or 7 (Safaricom).
ETHIOPIAN_MOBILE_RE = re.compile(r'^[79]\d{8}$')

COUNTRY_CODE = '251'

INVALID_PHONE_MESSAGE = (
    'Please enter a valid Ethiopian phone number starting with 9 '
    '(e.g. 944365493).'
)

# Only these are stripped before matching. Anything else -- a letter, a stray
# symbol -- must survive so the regex can reject it, rather than being quietly
# scrubbed into a number the user never typed.
_SEPARATORS = re.compile(r'[\s\-()]')


def _subscriber_part(raw):
    """The nine-digit subscriber number, or None if `raw` is not one.

    Handles the trunk prefix and country code in either order of appearance,
    and refuses a country code repeated more than once.
    """
    if raw is None:
        return None

    s = _SEPARATORS.sub('', str(raw))
    if not s:
        return None

    # A single leading '+' is allowed; '+251+251...' is not.
    if s.startswith('+'):
        s = s[1:]
    if '+' in s:
        return None

    # Strip at most one country code, then at most one trunk prefix. Doing it
    # once each is what rejects '251251944365493' and '00944365493'.
    if s.startswith(COUNTRY_CODE):
        s = s[len(COUNTRY_CODE):]
    elif s.startswith('0'):
        s = s[1:]

    return s if ETHIOPIAN_MOBILE_RE.match(s) else None


def is_valid_ethiopian_mobile(raw):
    """True when `raw` is an Ethiopian mobile number in any accepted form."""
    return _subscriber_part(raw) is not None


def normalize_ethiopian_phone(raw):
    """``251XXXXXXXXX`` for storage and lookups, or None when invalid."""
    part = _subscriber_part(raw)
    return COUNTRY_CODE + part if part else None


def lookup_variants(raw):
    """Accepted storage variants for a phone lookup.

    New writes should use ``normalize_ethiopian_phone``. This exists for
    reads against older rows that may still carry E.164 or local trunk forms.
    """
    part = _subscriber_part(raw)
    if not part:
        return []

    variants = [
        COUNTRY_CODE + part,
        '+' + COUNTRY_CODE + part,
        '0' + part,
        part,
    ]
    return list(dict.fromkeys(variants))


def to_e164(raw):
    """``+251XXXXXXXXX`` for API responses and display, or None when invalid."""
    part = _subscriber_part(raw)
    return '+' + COUNTRY_CODE + part if part else None


def to_local(raw):
    """``0XXXXXXXXX`` -- the form CRM and telebirr B2C expect, or None."""
    part = _subscriber_part(raw)
    return '0' + part if part else None
