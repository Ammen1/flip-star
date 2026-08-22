"""
Regression tests for the CRM (Ethio Telecom data-gift) and Telebirr B2C
winner-gift subsystems -- ported from the master branch, entirely missing
in the current project before this change.

The central deviation from master being tested: send_b2c_gift/send_b2c_bulk
(api/views/crm.py) must leave a WinnerGiftTransaction 'processing' after a
successful B2C *initiation*, never 'success' -- master marks it 'success'
immediately, which is exactly the "credited before payout confirmed" bug
this project's whole B2C payout effort (item 6) exists to avoid. Only
telebirr_b2c_webhook (api/views/direct_debit.py), extended in this same
change to also correlate WinnerGiftTransaction by originator_conversation_id,
may set 'success'/'failed'.

Also covers: HasAdminPermission scoping (not a blanket is_staff check, per
the item-3 admin-permission fix) and WinnerFrequencyRecord's eligibility
math, ported from master's CampaignScoringConfig-driven limits.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.campaign_extended import Campaign, CampaignScoringConfig, WinnerFrequencyRecord
from api.models.crm import CRMGiftPackage, CRMGiftTransaction
from api.models.gift import WinnerGiftPackage, WinnerGiftTransaction
from api.views.crm import CRMGiftAwardViewSet, CRMGiftTransactionViewSet
from api.views.direct_debit import telebirr_b2c_webhook

pytestmark = pytest.mark.integration

factory = APIRequestFactory()


@pytest.fixture
def user(db):
    u = User.objects.create_user(username='crm_user', password='x')
    u.profile.phone_number = '0911223344'
    u.profile.save()
    yield u
    u.delete()


@pytest.fixture
def admin_with_gift_permission(db):
    from api.models.subscription import AdminRole

    u = User.objects.create_user(username='crm_admin', password='x', is_staff=True)
    AdminRole.objects.create(user=u, role='finance_team', permission_level='full')
    yield u
    u.delete()


@pytest.fixture
def staff_without_admin_role(db):
    u = User.objects.create_user(username='crm_staff_no_role', password='x', is_staff=True)
    yield u
    u.delete()


def _soap_result(*, originator_conversation_id, result_code, transaction_id='', result_desc=''):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:res="http://cps.huawei.com/cpsinterface/response">
  <soapenv:Body>
    <api:Result xmlns:api="http://cps.huawei.com/cpsinterface/response">
      <res:ResultType>0</res:ResultType>
      <res:ResultCode>{result_code}</res:ResultCode>
      <res:ResultDesc>{result_desc}</res:ResultDesc>
      <res:OriginatorConversationID>{originator_conversation_id}</res:OriginatorConversationID>
      <res:TransactionID>{transaction_id}</res:TransactionID>
    </api:Result>
  </soapenv:Body>
</soapenv:Envelope>'''.encode()


# ---------------------------------------------------------------------------
# HasAdminPermission scoping -- award_gifts is per-role, not is_staff
# ---------------------------------------------------------------------------

def test_staff_without_admin_role_cannot_award_crm_gift(staff_without_admin_role, user):
    package = CRMGiftPackage.objects.create(name='1GB', offering_id='OFF1', charge_amount=10)

    request = factory.post('/admin/crm/award/', {'user_id': user.id, 'package_id': package.id}, format='json')
    force_authenticate(request, user=staff_without_admin_role)

    response = CRMGiftAwardViewSet.as_view({'post': 'award'})(request)

    assert response.status_code == 403
    assert not CRMGiftTransaction.objects.filter(user=user).exists()


def test_finance_team_admin_can_award_crm_gift(admin_with_gift_permission, user):
    package = CRMGiftPackage.objects.create(name='1GB', offering_id='OFF2', charge_amount=10)

    with patch(
        'api.views.crm.CRMService.send_gift',
        return_value=(True, 'OK', {'ret_code': '0'}),
    ):
        request = factory.post('/admin/crm/award/', {'user_id': user.id, 'package_id': package.id}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        response = CRMGiftAwardViewSet.as_view({'post': 'award'})(request)

    assert response.status_code == 201, response.data
    txn = CRMGiftTransaction.objects.get(user=user)
    assert txn.status == 'success'


def test_crm_transaction_viewset_hides_other_users_transactions_from_plain_staff(staff_without_admin_role, user):
    """is_staff=True with no AdminRole must see only their own transactions
    -- the exact regression class fixed for api/views/admin.py in item 3,
    now also checked here since this viewset scopes visibility the same way."""
    package = CRMGiftPackage.objects.create(name='1GB', offering_id='OFF3', charge_amount=10)
    CRMGiftTransaction.objects.create(
        user=user, phone_number='0911223344', package=package, offering_id='OFF3',
        transaction_id='TXN_OTHER_1', charge_amount=10, status='success',
    )

    request = factory.get('/admin/crm/transactions/')
    force_authenticate(request, user=staff_without_admin_role)
    response = CRMGiftTransactionViewSet.as_view({'get': 'list'})(request)

    assert response.status_code == 200
    assert len(response.data) == 0


def test_crm_transaction_viewset_shows_all_to_admin_with_view_gifts(admin_with_gift_permission, user):
    package = CRMGiftPackage.objects.create(name='1GB', offering_id='OFF4', charge_amount=10)
    CRMGiftTransaction.objects.create(
        user=user, phone_number='0911223344', package=package, offering_id='OFF4',
        transaction_id='TXN_OTHER_2', charge_amount=10, status='success',
    )

    request = factory.get('/admin/crm/transactions/')
    force_authenticate(request, user=admin_with_gift_permission)
    response = CRMGiftTransactionViewSet.as_view({'get': 'list'})(request)

    assert response.status_code == 200
    assert len(response.data) == 1


# ---------------------------------------------------------------------------
# CRM award: max_awards_per_user, package eligibility
# ---------------------------------------------------------------------------

def test_award_rejects_when_max_awards_per_user_reached(admin_with_gift_permission, user):
    package = CRMGiftPackage.objects.create(name='1GB', offering_id='OFF5', charge_amount=10, max_awards_per_user=1)
    CRMGiftTransaction.objects.create(
        user=user, phone_number='0911223344', package=package, offering_id='OFF5',
        transaction_id='TXN_PRIOR', charge_amount=10, status='success',
    )

    request = factory.post('/admin/crm/award/', {'user_id': user.id, 'package_id': package.id}, format='json')
    force_authenticate(request, user=admin_with_gift_permission)
    response = CRMGiftAwardViewSet.as_view({'post': 'award'})(request)

    assert response.status_code == 400
    assert CRMGiftTransaction.objects.filter(user=user).count() == 1


# ---------------------------------------------------------------------------
# send_b2c_gift: must never mark 'success' before the webhook confirms
# ---------------------------------------------------------------------------

def test_send_b2c_gift_leaves_transaction_processing_not_success(admin_with_gift_permission, user):
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        'api.views.crm.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value={
            'success': True,
            'originator_conversation_id': 'S_X20260820WINGIFT1',
            'conversation_id': 'AG_20260820WINGIFT1',
        },
    ):
        request = factory.post('/admin/crm/send-b2c-gift/', {'user_id': user.id, 'amount': 500, 'winner_type': 'weekly'}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_gift'})(request)

    assert response.status_code == 200, response.data
    txn = WinnerGiftTransaction.objects.get(winner=user)
    assert txn.status == 'processing'
    assert txn.status != 'success'
    assert txn.originator_conversation_id == 'S_X20260820WINGIFT1'


def test_send_b2c_gift_rejects_non_telebirr_user(admin_with_gift_permission, user):
    request = factory.post('/admin/crm/send-b2c-gift/', {'user_id': user.id, 'amount': 500}, format='json')
    force_authenticate(request, user=admin_with_gift_permission)

    response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_gift'})(request)

    assert response.status_code == 400
    assert not WinnerGiftTransaction.objects.filter(winner=user).exists()


def test_send_b2c_gift_marks_failed_on_initiation_failure(admin_with_gift_permission, user):
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        'api.views.crm.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value={'success': False, 'error': 'upstream error'},
    ):
        request = factory.post('/admin/crm/send-b2c-gift/', {'user_id': user.id, 'amount': 500}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_gift'})(request)

    assert response.status_code == 400
    txn = WinnerGiftTransaction.objects.get(winner=user)
    assert txn.status == 'failed'


# ---------------------------------------------------------------------------
# telebirr_b2c_webhook: WinnerGiftTransaction correlation (extended path)
# ---------------------------------------------------------------------------

@pytest.fixture
def processing_winner_gift(db):
    u = User.objects.create_user(username='winner_gift_user', password='x')
    package = WinnerGiftPackage.objects.create(
        winner_type='weekly', gift_type='cash', payment_method='telebirr_b2c', amount=500,
    )
    txn = WinnerGiftTransaction.objects.create(
        winner=u, winner_type='weekly', gift_package=package, amount=500, payment_method='telebirr_b2c',
        receiver_msisdn='251911223344', status='processing', originator_conversation_id='S_X20260820WGWEBHOOK1',
    )
    yield txn
    txn.delete()
    u.delete()


def test_webhook_marks_winner_gift_success(processing_winner_gift):
    body = _soap_result(originator_conversation_id='S_X20260820WGWEBHOOK1', result_code='0', transaction_id='TXNWG1')
    request = factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml')

    response = telebirr_b2c_webhook(request)

    assert response.status_code == 200
    processing_winner_gift.refresh_from_db()
    assert processing_winner_gift.status == 'success'
    assert processing_winner_gift.telebirr_transaction_id == 'TXNWG1'


def test_webhook_marks_winner_gift_failed(processing_winner_gift):
    body = _soap_result(originator_conversation_id='S_X20260820WGWEBHOOK1', result_code='1', result_desc='declined')
    request = factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml')

    response = telebirr_b2c_webhook(request)

    assert response.status_code == 200
    processing_winner_gift.refresh_from_db()
    assert processing_winner_gift.status == 'failed'
    assert 'declined' in processing_winner_gift.error_message


def test_webhook_winner_gift_duplicate_delivery_does_not_double_process(processing_winner_gift):
    body = _soap_result(originator_conversation_id='S_X20260820WGWEBHOOK1', result_code='0', transaction_id='TXNWG2')

    telebirr_b2c_webhook(factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml'))
    telebirr_b2c_webhook(factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml'))

    processing_winner_gift.refresh_from_db()
    assert processing_winner_gift.status == 'success'


# ---------------------------------------------------------------------------
# WinnerFrequencyRecord: eligibility math ported from master
# ---------------------------------------------------------------------------

@pytest.fixture
def campaign_with_scoring_config(db):
    campaign = Campaign.objects.create(title='Test Campaign', campaign_type='daily')
    config = CampaignScoringConfig.objects.create(campaign=campaign, daily_win_limit_per_month=2)
    yield campaign, config
    config.delete()
    campaign.delete()


def test_frequency_eligibility_true_when_under_limit(user, campaign_with_scoring_config):
    campaign, _config = campaign_with_scoring_config

    is_eligible, current_wins, limit = WinnerFrequencyRecord.check_frequency_eligibility(user, 'daily', campaign)

    assert is_eligible is True
    assert current_wins == 0
    assert limit == 2


def test_frequency_eligibility_false_when_limit_reached(user, campaign_with_scoring_config):
    campaign, _config = campaign_with_scoring_config

    now = timezone.now()
    for i in range(2):
        WinnerFrequencyRecord.objects.create(
            user=user, campaign=campaign, winner_type='daily',
            period_start=now.replace(hour=0, minute=0, second=0, microsecond=0) - timezone.timedelta(days=i),
            period_end=now,
        )

    is_eligible, current_wins, limit = WinnerFrequencyRecord.check_frequency_eligibility(user, 'daily', campaign)

    assert is_eligible is False
    assert current_wins == 2
    assert limit == 2


def test_record_win_is_idempotent_for_the_same_period(user):
    # No period_start given -- record_win auto-computes it (today's daily
    # window), identically on both calls.
    record1, created1 = WinnerFrequencyRecord.record_win(user=user, winner_type='daily')
    record2, created2 = WinnerFrequencyRecord.record_win(user=user, winner_type='daily')

    assert created1 is True
    assert created2 is False
    assert record1.pk == record2.pk
    assert WinnerFrequencyRecord.objects.filter(user=user, winner_type='daily').count() == 1
