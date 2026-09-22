"""
Counting what an SMS costs to send.

`len()` is not the number a gateway bills. A message is GSM-7 if every
character fits that alphabet and UCS-2 if even one does not, and the capacities
differ by more than a factor of two -- so a single curly quote pasted into a
template can double the cost of every message sent from it.

These pin the arithmetic the subscription messages are held to.
"""

from api.services.sms.segments import (
    describe,
    encoding_of,
    is_gsm7,
    segments,
    septets,
    units,
)

# ── which alphabet ───────────────────────────────────────────────────────────


def test_ordinary_english_is_gsm7():
    assert is_gsm7('Your Daily Flipstar subscription is renewed for 3 ETB per day.') is True


def test_a_url_is_gsm7():
    """Every character the access link uses -- ? = & _ - . : / -- is in the
    basic alphabet, so the link does not force the expensive encoding."""
    link = 'https://uat.flipstar.et/register?subscription_tp=true&phone=251912345678'
    assert is_gsm7(link) is True


def test_one_foreign_character_changes_the_encoding():
    assert encoding_of('Flipstar') == 'GSM-7'
    assert encoding_of('Flipstar ሰላም') == 'UCS-2'
    assert encoding_of('It\u2019s renewed') == 'UCS-2', 'a curly apostrophe is not GSM-7'


# ── the two-septet characters ────────────────────────────────────────────────


def test_the_extension_characters_cost_two_septets():
    assert septets('abc') == 3
    assert septets('[') == 2
    assert septets('{}') == 4
    assert septets('€') == 2


def test_a_message_of_brackets_is_longer_than_it_looks():
    text = '[' * 100
    assert len(text) == 100
    assert units(text) == 200


# ── the boundaries ───────────────────────────────────────────────────────────


def test_a_single_gsm7_message_holds_160():
    assert segments('a' * 160) == 1
    assert segments('a' * 161) == 2, 'the 161st character starts a second part'


def test_concatenated_parts_hold_153_each():
    assert segments('a' * 306) == 2
    assert segments('a' * 307) == 3


def test_ucs2_holds_far_less():
    assert segments('ሰ' * 70) == 1
    assert segments('ሰ' * 71) == 2
    assert segments('ሰ' * 134) == 2, '67 per part once concatenated'


def test_nothing_costs_nothing():
    assert segments('') == 0
    assert segments(None) == 0


def test_the_description_says_what_and_why():
    assert describe('a' * 200) == '200 GSM-7 units, 2 segment(s)'
    assert describe('ሰ' * 80) == '80 UCS-2 units, 2 segment(s)'
