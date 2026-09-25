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

from decimal import Decimal
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

#
# The payout itself now lives in api/services/prize_delivery.py, so the
# Telebirr call is patched where it actually happens rather than on this
# module. The amount is no longer sent in the request either: it comes from
# the published prize structure, and a request naming a different figure is
# refused rather than honoured.

B2C_PAYMENT = (
    'api.integrations.telebirr.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment'
)


def test_send_b2c_gift_leaves_transaction_processing_not_success(admin_with_gift_permission, user):
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        B2C_PAYMENT,
        return_value={
            'success': True,
            'originator_conversation_id': 'S_X20260820WINGIFT1',
            'conversation_id': 'AG_20260820WINGIFT1',
        },
    ):
        request = factory.post('/admin/crm/send-b2c-gift/', {'user_id': user.id, 'winner_type': 'weekly'}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_gift'})(request)

    assert response.status_code == 200, response.data
    txn = WinnerGiftTransaction.objects.get(winner=user)
    assert txn.status == 'processing'
    assert txn.status != 'success'
    assert txn.originator_conversation_id == 'S_X20260820WINGIFT1'


def test_send_b2c_gift_pays_the_documented_amount(admin_with_gift_permission, user):
    """Not whatever the caller asked for -- a weekly prize is 1,000 ETB."""
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        B2C_PAYMENT,
        return_value={'success': True, 'originator_conversation_id': 'O1', 'conversation_id': 'C1'},
    ) as initiate:
        request = factory.post('/admin/crm/send-b2c-gift/', {'user_id': user.id, 'winner_type': 'weekly'}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        CRMGiftAwardViewSet.as_view({'post': 'send_b2c_gift'})(request)

    assert initiate.call_args.kwargs['amount'] == Decimal('1000.00')
    assert WinnerGiftTransaction.objects.get(winner=user).amount == Decimal('1000.00')


def test_b2c_gift_refuses_a_caller_supplied_amount(admin_with_gift_permission, user):
    """The vulnerability this closed.

    The payout amount used to be read straight from the request body, so a
    winner was paid whatever was asked for. A mismatch is now refused loudly
    rather than silently overridden, so nobody is left believing they paid a
    figure they did not.
    """
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        B2C_PAYMENT
    ) as initiate:
        request = factory.post('/admin/crm/send-b2c-gift/', {'user_id': user.id, 'amount': 500, 'winner_type': 'weekly'}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_gift'})(request)

    assert response.status_code == 400
    assert response.data['prize_amount'] == '1000.00'
    assert not initiate.called
    assert not WinnerGiftTransaction.objects.filter(winner=user).exists()


def test_b2c_gift_accepts_a_request_naming_the_correct_amount(admin_with_gift_permission, user):
    """Existing callers send the right figure; they keep working."""
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        B2C_PAYMENT,
        return_value={'success': True, 'originator_conversation_id': 'O2', 'conversation_id': 'C2'},
    ):
        request = factory.post('/admin/crm/send-b2c-gift/', {'user_id': user.id, 'amount': 1000, 'winner_type': 'weekly'}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_gift'})(request)

    assert response.status_code == 200, response.data


def test_send_b2c_gift_is_idempotent(admin_with_gift_permission, user):
    """Pressing send twice must not pay twice."""
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        B2C_PAYMENT,
        return_value={'success': True, 'originator_conversation_id': 'O3', 'conversation_id': 'C3'},
    ) as initiate:
        for _ in range(2):
            request = factory.post('/admin/crm/send-b2c-gift/', {'user_id': user.id, 'winner_type': 'weekly'}, format='json')
            force_authenticate(request, user=admin_with_gift_permission)
            CRMGiftAwardViewSet.as_view({'post': 'send_b2c_gift'})(request)

    assert WinnerGiftTransaction.objects.filter(winner=user).count() == 1
    assert initiate.call_count == 1, 'the second request sent a second payout'


def test_send_b2c_gift_rejects_non_telebirr_user(admin_with_gift_permission, user):
    request = factory.post('/admin/crm/send-b2c-gift/', {'user_id': user.id}, format='json')
    force_authenticate(request, user=admin_with_gift_permission)

    response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_gift'})(request)

    assert response.status_code == 400
    assert 'Telebirr' in response.data['error'], 'refused for the wrong reason'
    assert not WinnerGiftTransaction.objects.filter(winner=user).exists()


def test_send_b2c_gift_marks_failed_on_initiation_failure(admin_with_gift_permission, user):
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        B2C_PAYMENT,
        return_value={'success': False, 'error': 'upstream error'},
    ):
        request = factory.post('/admin/crm/send-b2c-gift/', {'user_id': user.id}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_gift'})(request)

    assert response.status_code == 400
    txn = WinnerGiftTransaction.objects.get(winner=user)
    assert txn.status == 'failed'
    assert txn.attempt_count == 1


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


# ---------------------------------------------------------------------------
# send_b2c_bulk: the path that could pay a whole cohort twice
# ---------------------------------------------------------------------------


@pytest.fixture
def selected_weekly_winners(db):
    """A finalised weekly selection with three winners."""
    from datetime import timedelta

    from api.models.campaign_extended import Leaderboard, SelectedWinner, WinnerSelection

    start = timezone.now() - timedelta(days=7)
    campaign = Campaign.objects.create(
        title='Weekly Battle',
        campaign_type='weekly',
        status='active',
        start_date=start,
        entry_deadline=timezone.now(),
    )
    leaderboard = Leaderboard.objects.create(
        campaign=campaign,
        period_type='weekly',
        period_start=start,
        period_end=timezone.now(),
    )
    selection = WinnerSelection.objects.create(
        campaign=campaign,
        selection_type='weekly',
        leaderboard=leaderboard,
        is_finalized=True,
    )

    winners = []
    for index in range(3):
        winner = User.objects.create_user(username=f'bulk_winner_{index}', password='x')
        winner.profile.phone_number = f'09115{index:05d}'
        winner.profile.save()
        SelectedWinner.objects.create(
            selection=selection, user=winner, rank=index + 1, final_score=100 - index
        )
        winners.append(winner)

    return campaign, winners


def test_bulk_payout_pays_each_winner_once(admin_with_gift_permission, selected_weekly_winners):
    _campaign, winners = selected_weekly_winners

    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        B2C_PAYMENT,
        return_value={'success': True, 'originator_conversation_id': 'OB', 'conversation_id': 'CB'},
    ) as initiate:
        request = factory.post('/admin/crm/send-b2c-bulk/', {'winner_type': 'weekly'}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_bulk'})(request)

    assert response.status_code == 200, response.data
    assert response.data['initiated'] == 3
    assert initiate.call_count == 3
    assert WinnerGiftTransaction.objects.filter(winner__in=winners).count() == 3


def test_rerunning_the_bulk_payout_does_not_pay_twice(
    admin_with_gift_permission, selected_weekly_winners
):
    """The reason this endpoint was worth migrating.

    It used to create a fresh transaction per call, so re-running it after a
    partial failure paid everybody who had already been paid a second time.
    """
    _campaign, winners = selected_weekly_winners

    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        B2C_PAYMENT,
        return_value={'success': True, 'originator_conversation_id': 'OB', 'conversation_id': 'CB'},
    ) as initiate:
        for _ in range(2):
            request = factory.post('/admin/crm/send-b2c-bulk/', {'winner_type': 'weekly'}, format='json')
            force_authenticate(request, user=admin_with_gift_permission)
            response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_bulk'})(request)

    assert WinnerGiftTransaction.objects.filter(winner__in=winners).count() == 3
    assert initiate.call_count == 3, 'the second run sent a second round of payouts'
    assert response.data['already_paid'] == 3
    assert response.data['initiated'] == 0


def test_bulk_payout_reports_the_prize_amount(admin_with_gift_permission, selected_weekly_winners):
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        B2C_PAYMENT,
        return_value={'success': True, 'originator_conversation_id': 'OB', 'conversation_id': 'CB'},
    ):
        request = factory.post('/admin/crm/send-b2c-bulk/', {'winner_type': 'weekly'}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_bulk'})(request)

    assert response.data['prize_amount'] == '1000.00'


def test_bulk_payout_refuses_a_caller_supplied_amount(
    admin_with_gift_permission, selected_weekly_winners
):
    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        B2C_PAYMENT
    ) as initiate:
        request = factory.post('/admin/crm/send-b2c-bulk/', {'winner_type': 'weekly', 'amount': 5}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_bulk'})(request)

    assert response.status_code == 400
    assert not initiate.called


def test_bulk_payout_records_the_campaign_and_deadline(
    admin_with_gift_permission, selected_weekly_winners
):
    """A bulk payout still gets its delivery deadline, so the 10-day promise
    is trackable for winners paid this way."""
    campaign, winners = selected_weekly_winners

    with patch('api.models.core.UserProfile.is_telebirr_user', return_value=True), patch(
        B2C_PAYMENT,
        return_value={'success': True, 'originator_conversation_id': 'OB', 'conversation_id': 'CB'},
    ):
        request = factory.post('/admin/crm/send-b2c-bulk/', {'winner_type': 'weekly'}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        CRMGiftAwardViewSet.as_view({'post': 'send_b2c_bulk'})(request)

    prize = WinnerGiftTransaction.objects.filter(winner=winners[0]).first()
    assert prize.campaign == campaign
    assert prize.deadline_at is not None


def test_bulk_payout_skips_non_telebirr_winners(
    admin_with_gift_permission, selected_weekly_winners
):
    _campaign, winners = selected_weekly_winners

    def only_first_is_telebirr(self):
        return self.user_id == winners[0].id

    with patch('api.models.core.UserProfile.is_telebirr_user', only_first_is_telebirr), patch(
        B2C_PAYMENT,
        return_value={'success': True, 'originator_conversation_id': 'OB', 'conversation_id': 'CB'},
    ) as initiate:
        request = factory.post('/admin/crm/send-b2c-bulk/', {'winner_type': 'weekly'}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        response = CRMGiftAwardViewSet.as_view({'post': 'send_b2c_bulk'})(request)

    assert response.data['initiated'] == 1
    assert response.data['skipped'] == 2
    assert initiate.call_count == 1


def test_a_skipped_winner_still_gets_a_prize_row(
    admin_with_gift_permission, selected_weekly_winners
):
    """The gap this closed.

    Winners without Telebirr used to be filtered out before any prize was
    awarded, so nothing recorded that they were owed 1,000 ETB. Now each one
    has a row marked skipped, with the reason, still counted as owed.
    """
    from api.services import prize_delivery

    _campaign, winners = selected_weekly_winners

    def only_first_is_telebirr(self):
        return self.user_id == winners[0].id

    with patch('api.models.core.UserProfile.is_telebirr_user', only_first_is_telebirr), patch(
        B2C_PAYMENT,
        return_value={'success': True, 'originator_conversation_id': 'OB', 'conversation_id': 'CB'},
    ):
        request = factory.post('/admin/crm/send-b2c-bulk/', {'winner_type': 'weekly'}, format='json')
        force_authenticate(request, user=admin_with_gift_permission)
        CRMGiftAwardViewSet.as_view({'post': 'send_b2c_bulk'})(request)

    # All three won; none is missing from the books.
    assert WinnerGiftTransaction.objects.filter(winner__in=winners).count() == 3

    unpaid = WinnerGiftTransaction.objects.filter(winner__in=winners[1:])
    assert {prize.status for prize in unpaid} == {'skipped'}
    for prize in unpaid:
        assert prize.amount == Decimal('1000.00')
        assert 'Telebirr' in prize.error_message
        assert prize.is_owed

    assert prize_delivery.owed_deliveries().filter(winner__in=winners[1:]).count() == 2
