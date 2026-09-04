"""
Classifying "no telebirr account" apart from every other payment failure.

The stakes are asymmetric, which is why the default is to classify nothing.

  false positive   a gateway timeout labelled "you need to register" sends a
                   paying customer to sign up for an account they already
                   have, and hides a real outage behind a friendly message
  false negative   an unregistered customer sees a generic error -- unhelpful,
                   but honest, and exactly what happens today

So UNREGISTERED_RESPONSE_CODES ships empty and is populated from configuration
once Telebirr confirms the codes. These tests pin that default, the matching
rules once codes are supplied, and the boundary that matters most: that no
provider text ever reaches the client.
"""

import pytest

from api.services import telebirr_registration as reg

# ---------------------------------------------------------------------------
# The safe default
# ---------------------------------------------------------------------------


def test_no_codes_are_classified_by_default():
    """
    Nothing is guessed.

    Until Telebirr tells us which code means "not registered", an unknown
    failure must take the ordinary error path.
    """
    assert reg.UNREGISTERED_RESPONSE_CODES == frozenset()


@pytest.mark.parametrize('code', ['1', '999', '2001', '4001', '1002', '1211'])
def test_an_unconfigured_code_is_not_a_registration_problem(code):
    result = {'success': False, 'response_code': code, 'error': 'Service failure'}

    assert reg.is_unregistered_failure(result) is False


def test_a_successful_result_is_never_classified():
    """Registration is only ever inferred from a refusal."""
    assert reg.is_unregistered_failure({'success': True, 'response_code': '0'}) is False


def test_an_empty_result_is_not_classified():
    assert reg.is_unregistered_failure({}) is False
    assert reg.is_unregistered_failure(None) is False


# ---------------------------------------------------------------------------
# Matching, once codes are configured
# ---------------------------------------------------------------------------


def test_a_configured_code_is_recognised(monkeypatch):
    monkeypatch.setattr(reg, 'UNREGISTERED_RESPONSE_CODES', frozenset({'2001'}))

    assert reg.is_unregistered_failure(
        {'success': False, 'response_code': '2001', 'error': 'Service failure'}
    )
    assert not reg.is_unregistered_failure(
        {'success': False, 'response_code': '2002', 'error': 'Service failure'}
    )


@pytest.mark.parametrize(
    'desc',
    [
        'Customer is not registered',
        'UNREGISTERED SUBSCRIBER',
        'No such customer',
        'no such subscriber',
        'Customer not found',
        'Subscriber does not exist',
    ],
)
def test_description_matching_catches_a_generic_code(desc):
    """Some gateways return a generic code with the detail in the text."""
    assert reg.is_unregistered_failure({'success': False, 'response_code': '1', 'error': desc})


@pytest.mark.parametrize(
    'desc',
    [
        'Parameter is incorrect',
        'Invalid amount',
        'Insufficient balance',
        'Service temporarily unavailable',
        'Request timed out',
        'Invalid security credential',
        'Duplicate OriginatorConversationID',
    ],
)
def test_unrelated_failures_are_not_mistaken_for_registration(desc):
    """
    The false-positive guard.

    'Insufficient balance' in particular: that customer IS registered, and
    telling them to register would be both wrong and insulting.
    """
    assert not reg.is_unregistered_failure({'success': False, 'response_code': '1', 'error': desc})


# ---------------------------------------------------------------------------
# What the user is told
# ---------------------------------------------------------------------------


def test_the_prompt_explains_action_and_can_be_dismissed():
    """The four things FS-10 requires the prompt to carry."""
    payload = reg.registration_required_payload()

    assert payload['code'] == reg.NOT_REGISTERED_CODE
    assert payload['explanation']
    assert payload['benefit']
    assert payload['action']['value'] == reg.REGISTRATION_SHORTCODE
    assert payload['dismissible'] is True, 'user must be able to cancel'


def test_no_provider_text_reaches_the_client():
    """
    ResponseDesc echoes request fields and internal identifiers, so it is
    logged and never returned.
    """
    result = {
        'success': False,
        'response_code': '2001',
        'error': 'ShortCode 90124 rejected for Initiator apiop_flipstar: not registered',
    }
    payload, log_reason = reg.classify_initiation_failure(result)

    serialised = str(payload)
    for secret in ('90124', 'apiop_flipstar', 'ShortCode'):
        assert secret not in serialised, f'{secret!r} leaked to the client'

    # The detail is not lost -- it goes to the log instead.
    assert '2001' in log_reason


def test_an_ordinary_failure_gets_a_generic_message():
    payload, reason = reg.classify_initiation_failure(
        {'success': False, 'response_code': '1', 'error': 'Internal error at node 4'}
    )

    assert payload['code'] == 'PAYMENT_FAILED'
    assert 'node 4' not in str(payload)
    assert 'node 4' in reason


# ---------------------------------------------------------------------------
# Preserving the user's selection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_selected_package_survives_the_prompt():
    """
    After registering, the user returns to the purchase they started -- not to
    an empty list having forgotten what they were buying.
    """
    from api.models.contest import CoinPackage

    pkg = CoinPackage.objects.create(
        name='Most Popular', price_etb=50, coin_amount=500, bonus_coins=75
    )
    pkg.refresh_from_db()  # price_etb is a Decimal only once the DB has cast it
    payload = reg.registration_required_payload(pkg)

    pending = payload['pending_package']
    assert pending['id'] == pkg.id
    assert pending['name'] == 'Most Popular'
    assert pending['total_coins'] == 575
    # Compared numerically: the string form depends on the field's
    # decimal_places, which is a schema detail this test should not pin.
    assert float(pending['price_etb']) == 50.0


def test_no_package_key_when_none_was_selected():
    assert 'pending_package' not in reg.registration_required_payload()
