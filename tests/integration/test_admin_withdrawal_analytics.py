"""
Regression tests for admin_withdrawal_analytics (api/views/wallet.py) --
ported from the master branch, missing entirely in the current project
before this change.

Master's WithdrawalRequest has a 'failed' status and platform_fee_birr
field; current's model has neither (STATUS_CHOICES uses 'rejected'/
'cancelled' instead, and the fee field is named fee_birr) -- the port
adapts the aggregation to the real schema rather than filtering on a
status value that can never match.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.wallet import WithdrawalRequest
from api.views.wallet import admin_withdrawal_analytics

pytestmark = pytest.mark.integration

factory = APIRequestFactory()


@pytest.fixture
def staff_user(db):
    u = User.objects.create_user(username='wd_analytics_staff', password='x', is_staff=True)
    yield u
    u.delete()


@pytest.fixture
def plain_user(db):
    u = User.objects.create_user(username='wd_analytics_plain', password='x')
    yield u
    u.delete()


@pytest.fixture
def withdrawals(db, staff_user):
    rows = [
        WithdrawalRequest.objects.create(
            user=staff_user, point_amount=1000, gross_birr=100, fee_birr=20, net_birr=80,
            conversion_rate=10, payout_method='telebirr', payout_account='251911000111', status='completed',
        ),
        WithdrawalRequest.objects.create(
            user=staff_user, point_amount=2000, gross_birr=200, fee_birr=40, net_birr=160,
            conversion_rate=10, payout_method='telebirr', payout_account='251911000111', status='pending',
        ),
        WithdrawalRequest.objects.create(
            user=staff_user, point_amount=500, gross_birr=50, fee_birr=10, net_birr=40,
            conversion_rate=10, payout_method='telebirr', payout_account='251911000111', status='rejected',
        ),
    ]
    yield rows
    for r in rows:
        r.delete()


def test_admin_withdrawal_analytics_aggregates_totals(staff_user, withdrawals):
    request = factory.get('/admin/withdrawal-analytics/')
    force_authenticate(request, user=staff_user)

    response = admin_withdrawal_analytics(request)

    assert response.status_code == 200, response.data
    assert response.data['total_withdrawals'] == 3
    assert response.data['total_gross_birr'] == 350.0
    assert response.data['total_platform_fee_birr'] == 70.0
    assert response.data['total_net_birr'] == 280.0
    assert response.data['completed_count'] == 1
    assert response.data['pending_count'] == 1
    assert response.data['rejected_count'] == 1
    assert response.data['avg_withdrawal_birr'] == 80.0


def test_admin_withdrawal_analytics_handles_no_withdrawals(staff_user, db):
    request = factory.get('/admin/withdrawal-analytics/')
    force_authenticate(request, user=staff_user)

    response = admin_withdrawal_analytics(request)

    assert response.status_code == 200
    assert response.data['total_withdrawals'] == 0
    assert response.data['total_gross_birr'] == 0.0
    assert response.data['avg_withdrawal_birr'] == 0.0


def test_admin_withdrawal_analytics_rejects_non_staff(plain_user, db):
    request = factory.get('/admin/withdrawal-analytics/')
    force_authenticate(request, user=plain_user)

    response = admin_withdrawal_analytics(request)

    assert response.status_code == 403
