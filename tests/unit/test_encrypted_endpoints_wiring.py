"""
Regression tests proving the Tier-1 sensitive endpoints actually enforce
encrypted transport, not just that the decorator is importable.

No database is available in this suite (see tests/conftest.py), so
IsAuthenticated-gated views are exercised with DRF's force_authenticate --
which attaches a user to the request without a real auth lookup -- rather
than a real User/Token. That's enough to get past the permission check and
prove what's actually under test here: that encrypted_endpoint's rejection
fires (DecryptionError, 400) before any view body -- and therefore before
any DB access, wallet mutation, or payment call -- runs.

This does not re-prove the parser/renderer mechanism itself (round-tripped
generically in test_encrypted_transport.py) or each view's business logic on
decrypted data (blocked by the same pre-existing DB gap as the rest of the
suite). It proves the one thing specific to this wiring pass: every listed
endpoint really is gated now, not just decorated.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views.charging import initiate_on_demand_charging, purchase_coins_on_demand
from api.views.contest import purchase_coins
from api.views.core import (
    change_password,
    delete_account,
    forgot_password_confirm,
    forgot_password_phone_verify,
    login_with_subscription_otp,
    register,
    register_with_phone,
    reset_password,
)
from api.views.direct_debit import (
    activate_direct_debit_mandate,
    cancel_direct_debit_mandate,
    create_direct_debit_mandate,
    create_one_off_coin_purchase,
    initiate_direct_debit,
)
from api.views.wallet import (
    cancel_withdrawal,
    reinvest_points,
    request_withdrawal,
    telebirr_initiate_payment,
)
from common.security.encrypted_transport import (
    CLIENT_PUBLIC_KEY_HEADER_NAME,
    EncryptedJSONParser,
    EncryptedJSONRenderer,
)

pytestmark = pytest.mark.unit

factory = APIRequestFactory()

#: (view, requires_authentication, extra view args)
TIER_1_ENDPOINTS = [
    (register, False, ()),
    (register_with_phone, False, ()),
    (reset_password, False, ()),
    (forgot_password_confirm, False, ()),
    (forgot_password_phone_verify, False, ()),
    (login_with_subscription_otp, False, ()),
    (change_password, True, ()),
    (delete_account, True, ()),
    (request_withdrawal, True, ()),
    (cancel_withdrawal, True, (1,)),
    (reinvest_points, True, ()),
    (telebirr_initiate_payment, True, ()),
    (create_direct_debit_mandate, True, ()),
    (activate_direct_debit_mandate, True, ()),
    (cancel_direct_debit_mandate, True, ()),
    (initiate_direct_debit, True, ()),
    (create_one_off_coin_purchase, True, ()),
    (initiate_on_demand_charging, True, ()),
    (purchase_coins_on_demand, True, ()),
    (purchase_coins, True, ()),
]


def _view_name(view):
    return getattr(view, '__name__', repr(view))


@pytest.mark.parametrize('view,requires_auth,extra_args', TIER_1_ENDPOINTS, ids=_view_name)
def test_wired_correctly(view, requires_auth, extra_args):
    assert list(view.cls.parser_classes) == [EncryptedJSONParser], (
        f'{_view_name(view)} is not using EncryptedJSONParser'
    )
    assert list(view.cls.renderer_classes) == [EncryptedJSONRenderer], (
        f'{_view_name(view)} is not using EncryptedJSONRenderer'
    )


@pytest.mark.parametrize('view,requires_auth,extra_args', TIER_1_ENDPOINTS, ids=_view_name)
def test_rejects_request_without_client_public_key_header(view, requires_auth, extra_args):
    # Envelope-shaped (even with garbage values) so the rejection reliably
    # comes from the missing header, regardless of whether request.data
    # happens to get touched earlier than usual -- e.g. common/throttling.py's
    # identity-based throttles read request.data during initial(), before
    # encrypted_endpoint's own check ever runs, for endpoints that throttle
    # by an identifier out of the request body (reset/forgot-password).
    body = {'encrypted': 'x', 'nonce': 'y', 'checksum': 'z'}
    request = factory.post('/x/', data=body, format='json')
    if requires_auth:
        force_authenticate(request, user=MagicMock(is_authenticated=True, is_staff=False))

    response = view(request, *extra_args)

    assert response.status_code == 400, (
        f'{_view_name(view)} did not reject a request with no '
        f'{CLIENT_PUBLIC_KEY_HEADER_NAME} header (got {response.status_code})'
    )
    body = response.data if hasattr(response, 'data') else {}
    assert CLIENT_PUBLIC_KEY_HEADER_NAME in str(body), (
        f'{_view_name(view)} rejected the request but not for the expected reason: {body}'
    )
