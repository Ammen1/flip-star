"""
Which payment methods a coin purchase may use.

    0 < price <= 10 ETB  ->  telebirr or airtime
        price >  10 ETB  ->  telebirr only

The client mirrors this, but the client is a convenience. A request naming
``airtime`` for a 50 ETB package must be refused server-side whatever the UI
allowed, which is what these tests pin.

The limit used to be an exact price, so airtime was offered for the one 10 ETB
package and for nothing cheaper -- a 5 ETB custom purchase could not use it.
It is a ceiling now, which is why the "below ten" cases below assert the
opposite of what they used to.
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


@pytest.mark.parametrize('price', [5, '9.99', Decimal('1'), 0.01, '10.00'])
def test_below_ten_etb_offers_both_methods(price):
    """A cheaper purchase is not a dearer one: the limit is a ceiling."""
    assert allowed_pay_methods(price) == [TELEBIRR, AIRTIME]


@pytest.mark.parametrize('price', [0, '0', Decimal('0'), -1, '-5', Decimal('-0.01')])
def test_nothing_and_less_than_nothing_are_not_purchases(price):
    """Without the explicit floor, -1 satisfies "at most 10" and would widen
    what is allowed -- the one way a ceiling can be got round."""
    assert allowed_pay_methods(price) == [TELEBIRR]


@pytest.mark.parametrize('price', [None, '', 'abc', [], {}])
def test_an_unparseable_price_never_widens_what_is_allowed(price):
    """A malformed amount must fall to the restrictive answer, not the open one."""
    assert allowed_pay_methods(price) == [TELEBIRR]


# ─── enforcement ──────────────────────────────────────────────────────────────


def test_airtime_is_accepted_at_ten_etb():
    assert validate_pay_method('airtime', 10) == AIRTIME, 'the limit itself is included'


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
    assert 'or less' in str(exc.value.message), 'the message still describes an exact price'
    # Never render the amount in scientific notation to a user.
    assert '1E+1' not in str(exc.value.message)


@pytest.mark.parametrize('price', [1, 5, '9.99', 10, Decimal('2.50')])
def test_airtime_is_accepted_at_or_below_the_limit(price):
    assert validate_pay_method('airtime', price) == AIRTIME


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
