"""
Subscriptions bill to a different telebirr merchant account than the rest of
the application.

Coin purchases (C2B), withdrawal payouts (B2C) and airtime (TIMWE -- a
different provider entirely) stay on the current account. Only subscription
charges move. The two accounts settle to different places, so a charge landing
on the wrong one is not a degraded outcome: it is money arriving somewhere
nobody is reconciling, and nothing downstream notices.

That makes ISOLATION the property under test, not routing. Most tests here
assert what did NOT change. Two methods -- ``create_one_off_payment`` and
``initiate_ussd_push_payment`` -- serve both subscriptions and coin purchases,
so the split cannot be inferred from the method being called; the caller has
to declare intent, and these tests pin that each caller declares it correctly.

The two credential blocks in the Huawei CPS envelope are treated differently,
and several tests exist only to hold that line:

  <req:Initiator>  the merchant account -- never falls back.
  <req:Caller>     the integrator calling the API -- falls back to the
                   current account's values, because the same partner
                   integrates both.

No live network call is made: requests.post is mocked and its call arguments
inspected. No real transaction is initiated. Every credential below is a
fabricated test value.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from api.integrations.telebirr.direct_debit import (
    TelebirrDirectDebitService,
    TelebirrSubscriptionRoutingError,
)

pytestmark = pytest.mark.unit

_POST = 'api.integrations.telebirr.direct_debit.requests.post'
_OK = MagicMock(
    status_code=200,
    text='<res:ResponseCode>0</res:ResponseCode><res:ResponseDesc>OK</res:ResponseDesc>',
)

# The account everything EXCEPT subscriptions uses. Deliberately distinct
# strings so "the old account's value is absent" is a meaningful assertion
# rather than two settings that happen to share a value.
CURRENT = {
    'TELEBIRR_SHORTCODE': 'CUR-SHORTCODE',
    'TELEBIRR_B2C_SHORTCODE': 'CUR-B2C-SHORTCODE',
    'TELEBIRR_USSD_MERCHANT_SHORTCODE': 'CUR-USSD-SHORTCODE',
    'TELEBIRR_THIRD_PARTY_ID': 'CUR-THIRDPARTY',
    'TELEBIRR_THIRD_PARTY_PASSWORD': 'cur-thirdparty-password',
    'TELEBIRR_USSD_THIRD_PARTY_ID': 'CUR-USSD-THIRDPARTY',
    'TELEBIRR_USSD_THIRD_PARTY_PASSWORD': 'cur-ussd-thirdparty-password',
    'TELEBIRR_SP_OPERATOR_ID': 'CUR-SP-OP',
    'TELEBIRR_SP_OPERATOR_CREDENTIAL': 'cur-sp-credential',
    'TELEBIRR_ORG_OPERATOR_ID': 'CUR-ORG-OP',
    'TELEBIRR_ORG_OPERATOR_CREDENTIAL': 'cur-org-credential',
    'TELEBIRR_USSD_ORG_OPERATOR_ID': 'CUR-USSD-OP',
    'TELEBIRR_USSD_ORG_OPERATOR_CREDENTIAL': 'cur-ussd-credential',
    'TELEBIRR_B2C_ORG_OPERATOR_ID': 'CUR-B2C-OP',
    'TELEBIRR_B2C_ORG_OPERATOR_CREDENTIAL': 'cur-b2c-credential',
    'TELEBIRR_SOAP_URL': 'https://example.invalid/current',
    'TELEBIRR_USSD_SOAP_URL': 'https://example.invalid/current-ussd',
}

# The subscription account, fully provisioned. Fabricated identities.
SUBSCRIPTION = {
    'TELEBIRR_SUBSCRIPTION_SHORTCODE': 'OLD-SHORTCODE',
    'TELEBIRR_SUBSCRIPTION_SOAP_URL': 'https://example.invalid/old',
    'TELEBIRR_SUBSCRIPTION_THIRD_PARTY_ID': 'SUB-THIRDPARTY',
    'TELEBIRR_SUBSCRIPTION_THIRD_PARTY_PASSWORD': 'sub-thirdparty-password',
    'TELEBIRR_SUBSCRIPTION_SP_OPERATOR_ID': 'SUB-SP-OP',
    'TELEBIRR_SUBSCRIPTION_SP_OPERATOR_CREDENTIAL': 'sub-sp-credential',
    'TELEBIRR_SUBSCRIPTION_ORG_OPERATOR_ID': 'SUB-ORG-OP',
    'TELEBIRR_SUBSCRIPTION_ORG_OPERATOR_CREDENTIAL': 'sub-org-credential',
    'TELEBIRR_SUBSCRIPTION_USSD_SOAP_URL': 'https://example.invalid/old-ussd',
    'TELEBIRR_SUBSCRIPTION_USSD_THIRD_PARTY_ID': 'SUB-USSD-THIRDPARTY',
    'TELEBIRR_SUBSCRIPTION_USSD_THIRD_PARTY_PASSWORD': 'sub-ussd-thirdparty-password',
    'TELEBIRR_SUBSCRIPTION_USSD_ORG_OPERATOR_ID': 'SUB-USSD-OP',
    'TELEBIRR_SUBSCRIPTION_USSD_ORG_OPERATOR_CREDENTIAL': 'sub-ussd-credential',
}

# What Ethio Telecom actually issued for the old account: the USSD identity
# only, and no third-party password of its own. This is the configuration
# that will really be deployed, so it gets its own tests rather than only the
# fully-provisioned ideal above.
USSD_ONLY = {
    'TELEBIRR_SUBSCRIPTION_SHORTCODE': 'OLD-SHORTCODE',
    'TELEBIRR_SUBSCRIPTION_USSD_SOAP_URL': 'https://example.invalid/old-ussd',
    'TELEBIRR_SUBSCRIPTION_USSD_THIRD_PARTY_ID': 'SUB-USSD-THIRDPARTY',
    'TELEBIRR_SUBSCRIPTION_USSD_ORG_OPERATOR_ID': 'SUB-USSD-OP',
    'TELEBIRR_SUBSCRIPTION_USSD_ORG_OPERATOR_CREDENTIAL': 'sub-ussd-credential',
}

# Every identity string belonging to the current account. A subscription
# request must carry none of them: mixing the old short code with the current
# operator's credential is refused by the gateway with a ResponseDesc that
# names neither, which is the failure these guard.
CURRENT_OPERATOR_VALUES = (
    'CUR-SHORTCODE',
    'CUR-USSD-SHORTCODE',
    'CUR-SP-OP',
    'cur-sp-credential',
    'CUR-ORG-OP',
    'cur-org-credential',
    'CUR-USSD-OP',
    'cur-ussd-credential',
)

MANDATE_ARGS = {
    'payer_msisdn': '2519XXXXXXX',
    'payer_reference_number': 'SUB_1_20260930120000',
    'frequency': '03',
    'first_payment_date': '20260930',
    'expiry_date': '20270930',
}
ONE_OFF_ARGS = {
    'payer_msisdn': '2519XXXXXXX',
    'payer_reference_number': 'SUB_1_20260930120000',
}
DEBIT_ARGS = {'payer_reference_number': 'SUB_1_20260930120000', 'amount': '20.00'}
USSD_ARGS = {'amount': '20.00', 'phone_number': '2519XXXXXXX', 'coins': 0}

ALL_FLOWS = [
    ('create_mandate', MANDATE_ARGS),
    ('create_one_off_payment', ONE_OFF_ARGS),
    ('initiate_debit', DEBIT_ARGS),
    ('initiate_ussd_push_payment', USSD_ARGS),
]


def _routed():
    """Settings with the subscription account fully provisioned."""
    return override_settings(**{**CURRENT, **SUBSCRIPTION})


def _ussd_only():
    """Settings as Ethio Telecom actually issued them: USSD identity only."""
    return override_settings(**{**CURRENT, **USSD_ONLY})


def _unrouted():
    """Settings with routing switched OFF (short code unset)."""
    return override_settings(**{**CURRENT, 'TELEBIRR_SUBSCRIPTION_SHORTCODE': ''})


def _call(method_name, **kwargs):
    """Call one service method and return the SOAP body it sent.

    The service reads settings in __init__, so it is constructed inside the
    override block rather than imported as the module singleton.
    """
    with patch(_POST, return_value=_OK) as mock_post:
        service = TelebirrDirectDebitService()
        getattr(service, method_name)(**kwargs)
    return mock_post.call_args.kwargs['data']


def _call_url(method_name, **kwargs):
    """As _call, but returns the gateway URL the request was posted to."""
    with patch(_POST, return_value=_OK) as mock_post:
        service = TelebirrDirectDebitService()
        getattr(service, method_name)(**kwargs)
    return mock_post.call_args.args[0]


# ---------------------------------------------------------------------------
# The switch: an unset short code means nothing changes at all
# ---------------------------------------------------------------------------


def test_routing_is_off_when_the_subscription_shortcode_is_unset():
    with _unrouted():
        assert TelebirrDirectDebitService().subscription_routing_enabled is False


def test_routing_is_on_when_the_subscription_shortcode_is_set():
    with _routed():
        assert TelebirrDirectDebitService().subscription_routing_enabled is True


@pytest.mark.parametrize('method, kwargs', ALL_FLOWS)
def test_asking_for_subscription_routing_changes_nothing_while_it_is_off(method, kwargs):
    """Deploying this code is a no-op until the account is configured.

    This is what makes the change safe to ship ahead of the configuration:
    every subscription call site already passes for_subscription=True, and
    until the short code is set that flag must have no effect whatsoever.
    """
    with _unrouted():
        routed = _call(method, for_subscription=True, **kwargs)
        plain = _call(method, **kwargs)

    # Conversation ids and timestamps differ per call, so the identity fields
    # are compared rather than the whole envelope.
    for value in CURRENT_OPERATOR_VALUES:
        assert (value in routed) == (value in plain)
    assert 'OLD-SHORTCODE' not in routed


# ---------------------------------------------------------------------------
# Routing on: subscription flows move to the subscription account
# ---------------------------------------------------------------------------


def test_subscription_mandate_uses_the_subscription_account():
    with _routed():
        body = _call('create_mandate', for_subscription=True, **MANDATE_ARGS)

    assert '<com:IdentifierValue>OLD-SHORTCODE</com:IdentifierValue>' in body
    assert '<req:Identifier>SUB-SP-OP</req:Identifier>' in body
    assert '<req:SecurityCredential>sub-sp-credential</req:SecurityCredential>' in body


def test_subscription_one_off_uses_the_subscription_account():
    with _routed():
        body = _call('create_one_off_payment', for_subscription=True, **ONE_OFF_ARGS)

    assert '<com:IdentifierValue>OLD-SHORTCODE</com:IdentifierValue>' in body
    assert '<req:Identifier>SUB-SP-OP</req:Identifier>' in body


def test_subscription_debit_uses_the_org_operator_not_the_sp_operator():
    """Each telebirr command authenticates as a different operator TYPE.

    Mandate creation is IdentifierType 14 (SP), the debit is 11 (ORG). One
    shared pair would authenticate for one command and be rejected for the
    other, which is why the account carries three pairs rather than one.
    """
    with _routed():
        body = _call('initiate_debit', for_subscription=True, **DEBIT_ARGS)

    assert '<req:ShortCode>OLD-SHORTCODE</req:ShortCode>' in body
    assert '<req:Identifier>SUB-ORG-OP</req:Identifier>' in body
    assert '<req:SecurityCredential>sub-org-credential</req:SecurityCredential>' in body
    assert 'SUB-SP-OP' not in body


def test_subscription_ussd_push_uses_the_ussd_operator():
    with _routed():
        body = _call('initiate_ussd_push_payment', for_subscription=True, **USSD_ARGS)

    assert '<req:ShortCode>OLD-SHORTCODE</req:ShortCode>' in body
    assert '<req:Identifier>SUB-USSD-OP</req:Identifier>' in body
    assert '<req:SecurityCredential>sub-ussd-credential</req:SecurityCredential>' in body


def test_subscription_requests_go_to_the_subscription_gateway():
    with _routed():
        assert _call_url('create_mandate', for_subscription=True, **MANDATE_ARGS) == (
            'https://example.invalid/old'
        )
        assert _call_url('initiate_ussd_push_payment', for_subscription=True, **USSD_ARGS) == (
            'https://example.invalid/old-ussd'
        )


@pytest.mark.parametrize('method, kwargs', ALL_FLOWS)
def test_a_subscription_request_carries_no_current_account_operator(method, kwargs):
    """No mixing of Initiator identities. That is the routing decision."""
    with _routed():
        body = _call(method, for_subscription=True, **kwargs)

    for value in CURRENT_OPERATOR_VALUES:
        assert value not in body, f'{method} leaked {value!r} into a subscription request'


# ---------------------------------------------------------------------------
# Caller falls back; Initiator never does
# ---------------------------------------------------------------------------


def test_the_caller_block_falls_back_to_the_current_integrator():
    """<req:Caller> names who is calling the API, not whose money moves.

    Ethio Telecom issued the old account no third-party password of its own,
    so the current one is reused. Reusing the OPERATOR the same way would be
    a charge against the wrong merchant, which is why only this half falls
    back.
    """
    with _ussd_only():
        body = _call('initiate_ussd_push_payment', for_subscription=True, **USSD_ARGS)

    # Caller: the subscription account's own id, the current password.
    assert '<req:ThirdPartyID>SUB-USSD-THIRDPARTY</req:ThirdPartyID>' in body
    assert '<req:Password>cur-ussd-thirdparty-password</req:Password>' in body
    # Initiator: entirely the subscription account.
    assert '<req:Identifier>SUB-USSD-OP</req:Identifier>' in body
    assert '<req:ShortCode>OLD-SHORTCODE</req:ShortCode>' in body
    assert 'CUR-USSD-OP' not in body
    assert 'cur-ussd-credential' not in body


def test_ussd_only_provisioning_routes_the_live_subscription_path():
    """The configuration that will actually be deployed.

    The web app's only subscription payment call is
    /subscription/telebirr/ussd/initiate/, so the USSD identity alone is
    enough to move subscription revenue.
    """
    with _ussd_only():
        body = _call('initiate_ussd_push_payment', for_subscription=True, **USSD_ARGS)
        url = _call_url('initiate_ussd_push_payment', for_subscription=True, **USSD_ARGS)

    assert '<req:ShortCode>OLD-SHORTCODE</req:ShortCode>' in body
    assert url == 'https://example.invalid/old-ussd'


def test_ussd_only_provisioning_leaves_coin_purchases_alone():
    with _ussd_only():
        body = _call(
            'initiate_ussd_push_payment',
            amount='10.00',
            phone_number='2519XXXXXXX',
            coins=100,
        )
        url = _call_url(
            'initiate_ussd_push_payment',
            amount='10.00',
            phone_number='2519XXXXXXX',
            coins=100,
        )

    assert '<req:ShortCode>CUR-USSD-SHORTCODE</req:ShortCode>' in body
    assert '<req:Identifier>CUR-USSD-OP</req:Identifier>' in body
    assert 'OLD-SHORTCODE' not in body
    assert url == 'https://example.invalid/current-ussd'


@pytest.mark.parametrize(
    'method, kwargs, expected_key',
    [
        ('create_mandate', MANDATE_ARGS, 'TELEBIRR_SUBSCRIPTION_SP_OPERATOR_ID'),
        ('create_one_off_payment', ONE_OFF_ARGS, 'TELEBIRR_SUBSCRIPTION_SP_OPERATOR_ID'),
        ('initiate_debit', DEBIT_ARGS, 'TELEBIRR_SUBSCRIPTION_ORG_OPERATOR_ID'),
    ],
)
def test_ussd_only_provisioning_refuses_the_c2b_subscription_flows(method, kwargs, expected_key):
    """The C2B subscription paths have no old-account identity, so they stop.

    They do NOT quietly stay on the current account: that would put
    subscription money where nobody is reconciling it. The failure names the
    setting Ethio Telecom has not issued yet.
    """
    with _ussd_only(), patch(_POST, return_value=_OK) as mock_post:
        service = TelebirrDirectDebitService()
        result = getattr(service, method)(for_subscription=True, **kwargs)

    assert result['success'] is False
    assert expected_key in result['error']
    mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Routing on: everything else stays exactly where it was
# ---------------------------------------------------------------------------


def test_coin_one_off_stays_on_the_current_account_while_routing_is_on():
    """Buy Coins and subscriptions share create_one_off_payment.

    This is the test that catches a global TELEBIRR_SHORTCODE change: the
    short code is the same attribute for both purchase types, so moving it
    globally moves coin purchases with it.
    """
    with _routed():
        body = _call('create_one_off_payment', **ONE_OFF_ARGS)

    assert '<com:IdentifierValue>CUR-SHORTCODE</com:IdentifierValue>' in body
    assert '<req:Identifier>CUR-SP-OP</req:Identifier>' in body
    assert 'OLD-SHORTCODE' not in body
    assert 'SUB-SP-OP' not in body


def test_coin_ussd_push_stays_on_the_current_account_while_routing_is_on():
    """Buy Coins and subscriptions share initiate_ussd_push_payment too."""
    with _routed():
        body = _call(
            'initiate_ussd_push_payment',
            amount='10.00',
            phone_number='2519XXXXXXX',
            coins=100,
        )

    assert '<req:ShortCode>CUR-USSD-SHORTCODE</req:ShortCode>' in body
    assert '<req:Identifier>CUR-USSD-OP</req:Identifier>' in body
    assert 'OLD-SHORTCODE' not in body
    assert 'SUB-USSD-OP' not in body


def test_b2c_cashout_stays_on_the_current_account_while_routing_is_on():
    with _routed(), patch(_POST, return_value=_OK) as mock_post:
        service = TelebirrDirectDebitService()
        service.initiate_b2c_payment(receiver_msisdn='2519XXXXXXX', amount='50.00')

    body = mock_post.call_args.kwargs['data']
    assert 'CUR-B2C-SHORTCODE' in body
    assert 'CUR-B2C-OP' in body
    assert 'OLD-SHORTCODE' not in body
    for value in ('SUB-SP-OP', 'SUB-ORG-OP', 'SUB-USSD-OP'):
        assert value not in body


def test_b2c_has_no_subscription_switch_at_all():
    """A payout cannot be routed to the subscription account by accident.

    There is no for_subscription parameter to pass, which is a stronger
    guarantee than a test asserting a default value.
    """
    signature = inspect.signature(TelebirrDirectDebitService.initiate_b2c_payment)
    assert 'for_subscription' not in signature.parameters


def test_airtime_does_not_read_any_telebirr_setting():
    """Airtime is TIMWE, a different provider. Nothing here can reach it."""
    from api.integrations.timwe import charge

    assert 'TELEBIRR' not in inspect.getsource(charge)


# ---------------------------------------------------------------------------
# An existing mandate keeps its own account
# ---------------------------------------------------------------------------


def test_a_mandate_created_on_the_current_account_is_not_moved():
    """Routing a debit follows the mandate, not today's configuration.

    A subscription mandate created before this feature existed lives on the
    current account. purchase_type would call it a subscription and send the
    debit to the old account, where the mandate does not exist.
    """
    with _routed():
        service = TelebirrDirectDebitService()
        legacy = SimpleNamespace(payee_identifier_value='CUR-SHORTCODE')
        assert service.mandate_is_on_subscription_account(legacy) is False


def test_a_mandate_created_on_the_subscription_account_is_recognised():
    with _routed():
        service = TelebirrDirectDebitService()
        current = SimpleNamespace(payee_identifier_value='OLD-SHORTCODE')
        assert service.mandate_is_on_subscription_account(current) is True


def test_no_mandate_is_on_the_subscription_account_while_routing_is_off():
    with _unrouted():
        service = TelebirrDirectDebitService()
        for value in ('OLD-SHORTCODE', 'CUR-SHORTCODE', '', None):
            assert (
                service.mandate_is_on_subscription_account(
                    SimpleNamespace(payee_identifier_value=value)
                )
                is False
            )


def test_the_account_actually_used_is_reported_back_for_storage():
    """The caller records this on the mandate row.

    Without it the mandate stores today's configured short code, which is a
    different thing from the one the request carried the moment configuration
    changes underneath a long-lived mandate.
    """
    with _routed(), patch(_POST, return_value=_OK):
        service = TelebirrDirectDebitService()
        routed = service.create_mandate(for_subscription=True, **MANDATE_ARGS)
        plain = service.create_one_off_payment(**ONE_OFF_ARGS)

    assert routed['payee_shortcode'] == 'OLD-SHORTCODE'
    assert plain['payee_shortcode'] == 'CUR-SHORTCODE'


# ---------------------------------------------------------------------------
# Incomplete operator identity fails loudly rather than borrowing an account
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'missing_key, method, kwargs',
    [
        ('TELEBIRR_SUBSCRIPTION_SP_OPERATOR_ID', 'create_mandate', MANDATE_ARGS),
        (
            'TELEBIRR_SUBSCRIPTION_SP_OPERATOR_CREDENTIAL',
            'create_one_off_payment',
            ONE_OFF_ARGS,
        ),
        ('TELEBIRR_SUBSCRIPTION_ORG_OPERATOR_ID', 'initiate_debit', DEBIT_ARGS),
        ('TELEBIRR_SUBSCRIPTION_ORG_OPERATOR_CREDENTIAL', 'initiate_debit', DEBIT_ARGS),
        (
            'TELEBIRR_SUBSCRIPTION_USSD_ORG_OPERATOR_ID',
            'initiate_ussd_push_payment',
            USSD_ARGS,
        ),
        (
            'TELEBIRR_SUBSCRIPTION_USSD_ORG_OPERATOR_CREDENTIAL',
            'initiate_ussd_push_payment',
            USSD_ARGS,
        ),
    ],
)
def test_a_missing_operator_identity_never_falls_back(missing_key, method, kwargs):
    """Half an Initiator is a hard failure, not a silent fallback.

    The fallback would be the account holding coin revenue and funding
    withdrawals, so no request is sent at all.
    """
    with override_settings(**{**CURRENT, **SUBSCRIPTION, missing_key: ''}):
        with patch(_POST, return_value=_OK) as mock_post:
            service = TelebirrDirectDebitService()
            result = getattr(service, method)(for_subscription=True, **kwargs)

    assert result['success'] is False
    assert missing_key in result['error']
    mock_post.assert_not_called()


def test_the_raised_error_names_settings_and_not_values():
    """The message reaches logs and API responses.

    It must name the missing SETTING and must never contain a credential --
    including the ones that are correctly configured.
    """
    with override_settings(
        **{**CURRENT, **SUBSCRIPTION, 'TELEBIRR_SUBSCRIPTION_ORG_OPERATOR_ID': ''}
    ):
        service = TelebirrDirectDebitService()
        with pytest.raises(TelebirrSubscriptionRoutingError) as raised:
            service._subscription_identity('org')

    message = str(raised.value)
    assert 'TELEBIRR_SUBSCRIPTION_ORG_OPERATOR_ID' in message
    for secret in (
        'sub-sp-credential',
        'sub-org-credential',
        'sub-ussd-credential',
        'sub-thirdparty-password',
        'sub-ussd-thirdparty-password',
        'cur-org-credential',
        'cur-thirdparty-password',
        'cur-ussd-thirdparty-password',
    ):
        assert secret not in message


def test_identity_is_none_rather_than_an_error_when_routing_is_off():
    """Off is not a misconfiguration, so it must not raise."""
    with _unrouted():
        service = TelebirrDirectDebitService()
        for role in ('sp', 'org', 'ussd'):
            assert service._subscription_identity(role) is None


# ---------------------------------------------------------------------------
# Call sites declare their intent
# ---------------------------------------------------------------------------


def test_every_subscription_call_site_asks_for_subscription_routing():
    """Pins the call sites that must opt in.

    A new subscription payment path that forgets the flag bills the wrong
    account and still looks correct in review, so the call sites are asserted
    directly and not only the service.
    """
    from api.views import direct_debit as dd_views
    from api.views import subscription as sub_views

    dd_source = inspect.getsource(dd_views)
    sub_source = inspect.getsource(sub_views)

    # The recurring subscription mandate and the subscription one-off.
    assert dd_source.count('for_subscription=True') == 2
    # Both debits that follow a mandate route by the mandate's own account.
    assert dd_source.count('mandate_is_on_subscription_account(') == 2
    # The USSD push that charges a subscription -- the live path.
    assert sub_source.count('for_subscription=True') == 1


def test_the_coin_purchase_call_sites_do_not_ask_for_it():
    """Buy Coins must not carry the flag, in either of its two paths."""
    from api.views import wallet as wallet_views

    assert 'for_subscription' not in inspect.getsource(wallet_views)
