"""
Pins the database contract.

The restructure moved every model module into ``api/models/``. Django derives
table names from the *app label*, not the module path, so the move is only safe
while every model stays registered under the ``api`` label with its original
table name.

These tests fail loudly if a future change splits the app or renames a table.
"""

import pytest
from django.apps import apps

pytestmark = pytest.mark.integration

#: Every model must belong to this app label. Changing it renames ~82 tables.
EXPECTED_APP_LABEL = 'api'

#: Models that intentionally override the default table name. Everything else
#: must resolve to ``api_<modelname>``.
EXPLICIT_TABLE_NAMES = {
    'UserSubscription': 'user_subscriptions',
    'CoinPackage': 'coin_packages',
    'CoinTransaction': 'coin_transactions',
    'UserCoinBalance': 'user_coin_balances',
    'PostBoost': 'post_boosts',
    'GiftToCreator': 'gifts_to_creators',
    'ContestPostScore': 'contest_post_scores',
    'ContestLeaderboard': 'contest_leaderboards',
    'ContestTimeline': 'contest_timelines',
    'AntiCheatLog': 'anti_cheat_logs',
    'EligibilityVerification': 'eligibility_verifications',
    'GrandFinaleEntry': 'grand_finale_entries',
    'ExtraEntryPurchase': 'extra_entry_purchases',
    'SupportRequest': 'support_requests',
}


def _api_models():
    return apps.get_app_config(EXPECTED_APP_LABEL).get_models()


def test_all_models_registered_under_api_label():
    """Splitting the app would change every default table name."""
    for model in _api_models():
        assert model._meta.app_label == EXPECTED_APP_LABEL, (
            f'{model.__name__} is registered under '
            f'{model._meta.app_label!r}, expected {EXPECTED_APP_LABEL!r}'
        )


def test_table_names_unchanged():
    """Table names must match what the 86 existing migrations created."""
    for model in _api_models():
        name = model.__name__
        expected = EXPLICIT_TABLE_NAMES.get(name, f'api_{name.lower()}')
        assert model._meta.db_table == expected, (
            f'{name} maps to table {model._meta.db_table!r}, expected {expected!r}. '
            'A table rename requires a data migration, not a code move.'
        )


def test_model_count_is_stable():
    """Guards against a model being accidentally registered or dropped.

    Note: PhoneOTP and PasswordResetToken are deliberately *not* registered --
    migrations 0051 and 0054 dropped their tables. See the restructure report.

    106 is the count as of porting, from the master branch: UserConsent/
    ConsentHistory (consent tracking, api/models/legal.py);
    PendingTelebirrMandate/B2CPaymentTransaction (Telebirr B2C payout,
    api/models/subscription.py and direct_debit.py); CRMGiftPackage/
    CRMGiftTransaction/CRMGiftAuditLog/WinnerGiftPackage/
    WinnerGiftTransaction/WinnerFrequencyRecord (CRM data gifts + Telebirr
    B2C winner gifts, api/models/crm.py, gift.py, campaign_extended.py);
    SecurityEvent (security event logging, api/models/admin.py); Draft
    (unpublished reel drafts, api/models/core.py); and PrivilegeAuditLog
    (admin grant/revoke audit trail, api/models/admin.py -- master declares
    this model but never writes to it; admin_grant_admin now does).

    110 adds Organization (api/models/organization.py), which owns campaigns
    and scopes what an ORGANIZATION-realm user may see. Realm and role are
    fields on the existing UserProfile rather than models of their own --
    this project uses Django's built-in auth.User, so there is no separate
    user table to add and none was created.

    113 adds the organization coin economy (api/models/coin_config.py):
    CoinConfiguration (per-organization rates with optional per-campaign
    overrides), CoinConfigurationAudit (who changed a coin value, from what,
    to what) and CampaignRewardGrant (the idempotency record that makes a
    retried reward a no-op).

    114 adds SmsMessage (api/models/sms.py), which tracks an outbound SMS from
    queueing to delivery. SMPP is asynchronous in both directions: submit_sm
    returns a gateway message id and the delivery receipt for it arrives
    later, so there has to be somewhere to write the id down. It is also what
    the idempotency key hangs off, and so what stops a retry sending a second
    OTP. Deliberately not a field on the subscription models -- SMS delivery
    is not payment state.

    These do not duplicate the three coin concepts that already existed:
    CampaignScoringConfig holds LEADERBOARD weights, WalletConfig.cost_* holds
    what an engagement costs the actor, and WalletConfig.*_reward held what it
    should pay -- globally, and credited to nobody. The new models add the
    missing per-organization axis and leave all three alone.

    Update it deliberately when the model set genuinely changes.
    """
    assert len(list(_api_models())) == 114


@pytest.mark.parametrize(
    'name',
    [
        'UserProfile',
        'Reel',
        'Comment',
        'Vote',
        'Follow',
        'Block',
        'WalletConfig',
        'WithdrawalRequest',
        'UserCoinBalance',
        'CoinTransaction',
        'SubscriptionPlan',
        'SubscriptionTier',
        'DirectDebitMandate',
        'Campaign',
        'PostScore',
        'BoostCampaign',
        'Gift',
        'Conversation',
    ],
)
def test_key_models_importable_from_package_root(name):
    """``from api.models import X`` must keep working for every model."""
    import api.models as models_pkg

    assert hasattr(models_pkg, name), f'api.models no longer exports {name}'


def test_unregistered_auth_models_stay_unregistered():
    """
    PhoneOTP and PasswordResetToken have no tables.

    Importing them into ``api/models/__init__`` would register them and make
    ``makemigrations`` want to recreate the dropped tables. This test guards
    that regression.
    """
    import api.models as models_pkg

    assert not hasattr(models_pkg, 'PhoneOTP')
    assert not hasattr(models_pkg, 'PasswordResetToken')
