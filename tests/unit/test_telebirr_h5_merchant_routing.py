"""
Coin purchases and subscription payments settle to different H5 merchant
accounts.

Both go through the same Fabric ``preOrder`` call and both carry a
``merch_code`` -- the field that decides which merchant account the money
lands in. One shared setting cannot separate them, so the caller declares
intent with ``flow=``. These tests pin that each caller declares it correctly
and that neither account's code leaks into the other's request.

Ethio Telecom confirmed only ``merch_code`` differs between accounts: the
Fabric app id, app secret, merchant app id and RSA keypair are shared. So the
signing path is deliberately untouched here, and one key signs for both
accounts -- that is asserted rather than assumed.

No network call is made: requests.post is mocked. No payment is initiated.
Every credential below is a fabricated test value.
"""

from __future__ import annotations

import inspect
import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from api.integrations.telebirr.checkout import TelebirrService

pytestmark = pytest.mark.unit

_POST = 'api.integrations.telebirr.checkout.requests.post'

# A throwaway RSA key so signing works without touching real material.
_TEST_KEY = None


def _test_private_key_pem():
    global _TEST_KEY
    if _TEST_KEY is None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _TEST_KEY = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
    return _TEST_KEY


BASE = {
    'TELEBIRR_H5_BASE_URL': 'https://example.invalid/fabric',
    'TELEBIRR_FABRIC_APP_ID': 'FABRIC-APP',
    'TELEBIRR_APP_SECRET': 'app-secret',
    'TELEBIRR_MERCHANT_APP_ID': 'MERCHANT-APP',
    'TELEBIRR_MERCHANT_CODE': 'SHARED-CODE',
    'TELEBIRR_NOTIFY_URL': 'https://example.invalid/notify',
    'TELEBIRR_REDIRECT_URL': 'https://example.invalid/redirect',
}

SPLIT = {
    'TELEBIRR_H5_COIN_MERCHANT_CODE': 'COIN-CODE',
    'TELEBIRR_H5_SUBSCRIPTION_MERCHANT_CODE': 'SUB-CODE',
}


def _settings(**extra):
    return override_settings(**{**BASE, 'TELEBIRR_PRIVATE_KEY': _test_private_key_pem(), **extra})


def _token_and_preorder():
    """Two sequential responses: applyFabricToken, then preOrder."""
    token = MagicMock(status_code=200)
    token.json.return_value = {'token': 'fabric-token'}
    token.raise_for_status.return_value = None

    pre = MagicMock(status_code=200)
    pre.json.return_value = {
        'result': 'SUCCESS',
        'biz_content': {'prepay_id': 'PREPAY123', 'merch_order_id': 'ORDER123'},
    }
    pre.raise_for_status.return_value = None
    return [token, pre]


def _order(flow=None, **kwargs):
    """Create an order and return (preOrder biz_content, result dict)."""
    with patch(_POST, side_effect=_token_and_preorder()) as mock_post:
        service = TelebirrService()
        result = service.create_order_ondemand(title='test', amount='10.00', flow=flow, **kwargs)
    preorder_call = mock_post.call_args_list[1]
    return preorder_call.kwargs['json'], result


# ---------------------------------------------------------------------------
# Off by default
# ---------------------------------------------------------------------------


def test_both_flows_share_the_merchant_code_until_it_is_split():
    """Shipping this code changes nothing until the settings are configured."""
    with _settings():
        coin, _ = _order(flow='coin')
        sub, _ = _order(flow='subscription')
        plain, _ = _order()

    assert coin['biz_content']['merch_code'] == 'SHARED-CODE'
    assert sub['biz_content']['merch_code'] == 'SHARED-CODE'
    assert plain['biz_content']['merch_code'] == 'SHARED-CODE'


def test_an_unknown_flow_falls_back_to_the_shared_code():
    with _settings(**SPLIT):
        service = TelebirrService()
        assert service.merchant_code_for(None) == 'SHARED-CODE'


# ---------------------------------------------------------------------------
# Split: each flow gets its own account
# ---------------------------------------------------------------------------


def test_coins_use_the_coin_merchant_code():
    with _settings(**SPLIT):
        body, result = _order(flow='coin')

    assert body['biz_content']['merch_code'] == 'COIN-CODE'
    assert 'SUB-CODE' not in json.dumps(body)
    assert result['merch_code'] == 'COIN-CODE'


def test_subscriptions_use_the_subscription_merchant_code():
    with _settings(**SPLIT):
        body, result = _order(flow='subscription')

    assert body['biz_content']['merch_code'] == 'SUB-CODE'
    assert 'COIN-CODE' not in json.dumps(body)
    assert result['merch_code'] == 'SUB-CODE'


def test_the_raw_request_carries_the_same_code_as_the_preorder():
    """The SuperApp SDK checks the two agree.

    A rawRequest signed with a different merch_code than the preOrder that
    produced its prepay_id is rejected by the SDK, not the gateway -- so it
    fails on the handset with no server-side trace.
    """
    with _settings(**SPLIT):
        _, coin = _order(flow='coin')
        _, sub = _order(flow='subscription')

    assert 'merch_code=COIN-CODE' in coin['raw_request']
    assert 'SUB-CODE' not in coin['raw_request']
    assert 'merch_code=SUB-CODE' in sub['raw_request']
    assert 'COIN-CODE' not in sub['raw_request']


def test_only_the_merchant_code_differs_between_the_two_accounts():
    """Everything else is shared, as Ethio Telecom confirmed.

    If a later change starts varying the app id or the Fabric key per flow,
    this test fails and the assumption gets revisited deliberately.
    """
    with _settings(**SPLIT):
        coin, _ = _order(flow='coin')
        sub, _ = _order(flow='subscription')

    cb, sb = coin['biz_content'], sub['biz_content']
    assert cb['appid'] == sb['appid'] == 'MERCHANT-APP'
    assert coin['method'] == sub['method'] == 'payment.preorder'
    assert coin['sign_type'] == sub['sign_type'] == 'SHA256WithRSA'
    differing = {k for k in cb if cb[k] != sb.get(k)}
    assert differing <= {'merch_code', 'merch_order_id'}


def test_one_keypair_signs_for_both_accounts():
    """The signature is present and well-formed for each flow.

    Only merch_code changes, so the shared private key must produce a valid
    signature for both -- there is no per-account key to select.
    """
    with _settings(**SPLIT):
        coin, _ = _order(flow='coin')
        sub, _ = _order(flow='subscription')

    for body in (coin, sub):
        assert body['sign']
        assert body['sign_type'] == 'SHA256WithRSA'
    assert coin['sign'] != sub['sign']  # different payloads, different signatures


# ---------------------------------------------------------------------------
# queryOrder follows the order's own account
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'flow, expected',
    [('coin', 'COIN-CODE'), ('subscription', 'SUB-CODE'), (None, 'SHARED-CODE')],
)
def test_query_order_asks_the_right_merchant(flow, expected):
    """An order queried on the wrong merchant answers not-found.

    That reads as "never paid" and would strand a completed purchase.
    """
    token = MagicMock(status_code=200)
    token.json.return_value = {'token': 'fabric-token'}
    token.raise_for_status.return_value = None
    query = MagicMock(status_code=200)
    query.json.return_value = {'result': 'SUCCESS', 'biz_content': {}}
    query.raise_for_status.return_value = None

    with _settings(**SPLIT), patch(_POST, side_effect=[token, query]) as mock_post:
        TelebirrService().query_order('ORDER123', flow=flow)

    body = mock_post.call_args_list[1].kwargs['json']
    assert body['biz_content']['merch_code'] == expected


# ---------------------------------------------------------------------------
# Call sites declare their intent
# ---------------------------------------------------------------------------


def _code_only(module):
    """Source with comment lines removed.

    The call sites carry comments naming the *other* flow, on purpose -- each
    one explains that the same method serves both. Counting raw text would
    match those, so comments are stripped before asserting.
    """
    lines = inspect.getsource(module).split('\n')
    return '\n'.join(line for line in lines if not line.lstrip().startswith('#'))


def test_the_coin_call_sites_declare_coin():
    from api.views import wallet as wallet_views

    code = _code_only(wallet_views)
    assert code.count("flow='coin'") == 2  # create_order_ondemand + query_order
    assert "flow='subscription'" not in code


def test_the_subscription_call_sites_declare_subscription():
    from api.views import subscription as sub_views

    code = _code_only(sub_views)
    assert code.count("flow='subscription'") == 2  # create_order_ondemand + query_order
    assert "flow='coin'" not in code


def test_notify_verification_needs_no_flow():
    """Callbacks are verified with the shared public key, not a merchant code.

    There is no account to choose, so no opportunity to choose the wrong one.
    """
    signature = inspect.signature(TelebirrService.verify_notify)
    assert 'flow' not in signature.parameters
