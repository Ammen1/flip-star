"""
Ethiopian mobile number validation.

The rule is nine digits beginning with 9 (Ethio Telecom) or 7 (Safaricom
Ethiopia). The previous implementation checked only the length and the first
character, so ``9abcdefgh`` and ``251abcdefghi`` were accepted and stored as
phone numbers -- these tests pin that shut.

``normalize_ethiopian_phone`` returns ``251XXXXXXXXX`` (no ``+``) because that
is the form already stored in ``UserProfile.phone_number`` and used for
lookups; ``to_e164`` is the separate E.164 helper for the API surface.
"""

import pytest

from common.validators import (
    is_valid_ethiopian_mobile,
    normalize_ethiopian_phone,
    to_e164,
    to_local,
)


# ─── accepted forms, all the same subscriber ──────────────────────────────────

@pytest.mark.parametrize('raw', [
    '944365493',
    '0944365493',
    '251944365493',
    '+251944365493',
    '+251 94 436 5493',
    '+251-944-365-493',
    ' 944365493 ',
])
def test_every_accepted_form_normalises_to_one_value(raw):
    assert normalize_ethiopian_phone(raw) == '251944365493'
    assert to_e164(raw) == '+251944365493'
    assert to_local(raw) == '0944365493'


@pytest.mark.parametrize('raw,expected', [
    ('944365493', '251944365493'),
    ('912345678', '251912345678'),
    ('987654321', '251987654321'),
    ('744365493', '251744365493'),   # Safaricom Ethiopia
])
def test_valid_numbers_from_the_spec(raw, expected):
    assert normalize_ethiopian_phone(raw) == expected


# ─── rejected ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw', [
    '844365493',        # wrong leading digit
    '644365493',
    '044365493',        # 0 is a trunk prefix, not a subscriber digit
    '94436549',         # too short
    '9443654930',       # too long
    '94436549a',        # letters
    'abc944365493',
    '9abcdefgh',        # accepted by the previous implementation
    '251abcdefghi',     # accepted by the previous implementation
    '+251+251944365493',  # doubled country code
    '251251944365493',
    '00944365493',
    '',
    '   ',
    None,
    '+',
    '251',
])
def test_invalid_numbers_are_rejected(raw):
    assert normalize_ethiopian_phone(raw) is None
    assert to_e164(raw) is None
    assert to_local(raw) is None
    assert is_valid_ethiopian_mobile(raw) is False


# ─── properties ───────────────────────────────────────────────────────────────

def test_normalisation_is_idempotent():
    """Re-normalising must never stack another country code."""
    once = normalize_ethiopian_phone('944365493')
    assert normalize_ethiopian_phone(once) == once
    e164 = to_e164('944365493')
    assert to_e164(e164) == e164
    assert '+251+251' not in str(to_e164(e164))
    assert not str(normalize_ethiopian_phone(once)).startswith('251251')


def test_storage_form_has_no_plus():
    """`UserProfile.phone_number` lookups depend on this; a `+` breaks them."""
    assert normalize_ethiopian_phone('+251944365493') == '251944365493'


def test_non_string_input_does_not_raise():
    for value in (None, 12345, [], {}, object()):
        assert normalize_ethiopian_phone(value) is None


# ─── the view's helper delegates to the same rule ─────────────────────────────

def test_core_view_helper_uses_the_shared_rule():
    from api.views.core import _normalize_ethiopian_phone

    assert _normalize_ethiopian_phone('944365493') == '251944365493'
    assert _normalize_ethiopian_phone('+251944365493') == '251944365493'
    assert _normalize_ethiopian_phone('9abcdefgh') is None
    assert _normalize_ethiopian_phone('251abcdefghi') is None
    assert _normalize_ethiopian_phone('844365493') is None
    assert _normalize_ethiopian_phone('9443654930') is None
