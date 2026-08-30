"""
Which payment methods a coin purchase may use.

    price == 10 ETB  ->  telebirr or airtime
    price >  10 ETB  ->  telebirr only

The client mirrors this, but the client is a convenience. A request naming
``airtime`` for a 50 ETB package must be refused server-side whatever the UI
allowed, which is what these tests pin.
"""

from decimal import Decimal

import pytest

from common.exceptions import ValidationError
from common.validators import AIRTIME, TELEBIRR, allowed_pay_methods, validate_pay_method


# ─── which methods are offered ────────────────────────────────────────────────

@pytest.mark.parametrize('price', [10, '10', '10.0', 10.0, Decimal('10'), Decimal('10.00')])
def test_ten_etb_offers_both_methods(price):
    assert allowed_pay_methods(price) == [TELEBIRR, AIRTIME]


@pytest.mark.parametrize('price', [10.01, 11, 20, 25, 30, 50, 100, 250, '20', Decimal('50')])
def test_above_ten_etb_is_telebirr_only(price):
    assert allowed_pay_methods(price) == [TELEBIRR]


@pytest.mark.parametrize('price', [0, 5, '9.99', Decimal('1')])
def test_below_ten_etb_is_telebirr_only(price):
    """The rule is *exactly* 10, not 'up to 10'."""
    assert allowed_pay_methods(price) == [TELEBIRR]


@pytest.mark.parametrize('price', [None, '', 'abc', [], {}])
def test_an_unparseable_price_never_widens_what_is_allowed(price):
    """A malformed amount must fall to the restrictive answer, not the open one."""
    assert allowed_pay_methods(price) == [TELEBIRR]


# ─── enforcement ──────────────────────────────────────────────────────────────

def test_airtime_is_accepted_at_ten_etb():
    assert validate_pay_method('airtime', 10) == AIRTIME


def test_telebirr_is_accepted_at_ten_etb():
    assert validate_pay_method('telebirr', 10) == TELEBIRR


@pytest.mark.parametrize('price', [20, 50, 100, '30'])
def test_telebirr_is_accepted_above_ten_etb(price):
    assert validate_pay_method('telebirr', price) == TELEBIRR


@pytest.mark.parametrize('price', [10.01, 11, 20, 50, 100, 250])
def test_airtime_is_rejected_above_ten_etb(price):
    with pytest.raises(ValidationError) as exc:
        validate_pay_method('airtime', price)
    assert '10 ETB' in str(exc.value.message)
    # Never render the amount in scientific notation to a user.
    assert '1E+1' not in str(exc.value.message)


@pytest.mark.parametrize('method', ['paypal', 'card', 'cash', '', None, 'AIRTIME_', 'tele birr'])
def test_unsupported_methods_are_rejected(method):
    with pytest.raises(ValidationError):
        validate_pay_method(method, 10)


@pytest.mark.parametrize('method', ['Telebirr', 'TELEBIRR', ' telebirr ', 'AirTime'])
def test_method_matching_is_case_and_space_insensitive(method):
    assert validate_pay_method(method, 10) in (TELEBIRR, AIRTIME)


def test_a_bypass_attempt_is_refused():
    """The scenario the rule exists for: airtime named for an expensive package."""
    with pytest.raises(ValidationError):
        validate_pay_method('airtime', 250)
