"""
Regression tests for the Telebirr mandate management commands -- ported
from the master branch, entirely missing in the current project before this
change. Only the 3 self-contained ones (depending only on
TelebirrDirectDebitService, already ported earlier this session) are
ported; sync_mandate_status/sync_telebirr_mandate_status/
process_telebirr_mandate_deductions all depend on
api/services/telebirr_mandate_service.py (a third, separate Fabric/RSA-signed
Telebirr integration, ~700 lines), which master's own Celery Beat schedule
marks as superseded ("replaced by USSD Push") and which nothing in this
codebase's user-facing surface calls -- not ported.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from api.models.direct_debit import DirectDebitMandate

pytestmark = pytest.mark.integration


@pytest.fixture
def user(db):
    u = User.objects.create_user(username='mandate_cmd_user', password='x')
    yield u
    u.delete()


@pytest.fixture
def active_mandate(db, user):
    mandate = DirectDebitMandate.objects.create(
        user=user, payer_msisdn='251911223344', payer_reference_number='REF1',
        payee_identifier_value='9286', mandate_id='M123456789', status='active',
        frequency='05', first_payment_date=date.today(), expiry_date=date.today() + timedelta(days=365),
    )
    yield mandate
    mandate.delete()


def test_cancel_mandate_by_phone_cancels_via_telebirr(active_mandate):
    out = StringIO()
    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.cancel_mandate',
        return_value={'success': True},
    ), patch('builtins.input', return_value='yes'):
        call_command('cancel_mandate_by_phone', '0911223344', stdout=out)

    active_mandate.refresh_from_db()
    assert active_mandate.status == 'cancelled'
    assert active_mandate.cancelled_at is not None


def test_cancel_mandate_by_phone_cancels_locally_when_telebirr_call_fails(active_mandate):
    """A failed Telebirr call must not leave the mandate active locally --
    otherwise it stays eligible for the next scheduled debit."""
    out = StringIO()
    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.cancel_mandate',
        return_value={'success': False, 'error': 'timeout'},
    ), patch('builtins.input', return_value='yes'):
        call_command('cancel_mandate_by_phone', '0911223344', stdout=out)

    active_mandate.refresh_from_db()
    assert active_mandate.status == 'cancelled'


def test_cancel_mandate_by_phone_declines_without_confirmation(active_mandate):
    out = StringIO()
    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.cancel_mandate',
    ) as mock_cancel, patch('builtins.input', return_value='no'):
        call_command('cancel_mandate_by_phone', '0911223344', stdout=out)

    mock_cancel.assert_not_called()
    active_mandate.refresh_from_db()
    assert active_mandate.status == 'active'


def test_cancel_mandate_by_phone_no_match_does_not_error(db):
    out = StringIO()
    call_command('cancel_mandate_by_phone', '0999999999', stdout=out)
    assert 'No Direct Debit mandates found' in out.getvalue()


@pytest.fixture
def subscription_with_mandate_contract(db, user):
    from api.models.subscription import SubscriptionPlan, SubscriptionTier

    tier = SubscriptionTier.objects.create(
        name='Mandate Cmd Test Tier', slug='mandate-cmd-test-tier', duration_type='monthly', duration_days=30,
        price_etb=100, onevas_code='MC1', spid='sp', service_id='svc', product_id='prod',
    )
    plan = SubscriptionPlan.objects.create(
        user=user, tier=tier, status='active', payment_method='telebirr',
        telebirr_phone_number='251922334455', mandate_contract_id='CONTRACT123', mandate_status='active',
    )
    yield plan
    plan.delete()
    tier.delete()


def test_cancel_mandate_by_contract_id_updates_all_matching_subscriptions(subscription_with_mandate_contract):
    out = StringIO()
    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.cancel_mandate',
        return_value={'success': True},
    ):
        call_command('cancel_mandate_by_contract_id', 'CONTRACT123', '--force', stdout=out)

    subscription_with_mandate_contract.refresh_from_db()
    assert subscription_with_mandate_contract.mandate_status == 'cancelled'


def test_cancel_mandate_by_contract_id_leaves_status_unchanged_on_telebirr_failure(subscription_with_mandate_contract):
    out = StringIO()
    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.cancel_mandate',
        return_value={'success': False, 'error': 'not found'},
    ):
        call_command('cancel_mandate_by_contract_id', 'CONTRACT123', '--force', stdout=out)

    subscription_with_mandate_contract.refresh_from_db()
    assert subscription_with_mandate_contract.mandate_status == 'active'


def test_cancel_all_mandates_by_phone_updates_matching_subscription(subscription_with_mandate_contract):
    out = StringIO()
    with patch(
        'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.cancel_mandate',
        return_value={'success': True},
    ), patch('builtins.input', return_value='yes'):
        call_command('cancel_all_mandates_by_phone', '0922334455', stdout=out)

    subscription_with_mandate_contract.refresh_from_db()
    assert subscription_with_mandate_contract.mandate_status == 'cancelled'
