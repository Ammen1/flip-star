"""
Model registry for the ``api`` application.

The models are split across sibling modules by business domain, but they all
belong to the single Django app label ``api``. That is deliberate: 86 existing
migrations, every ``api_*`` table name, and all ContentType rows depend on it.
Splitting these into separate Django apps requires a pinned ``db_table`` on each
model plus paired ``SeparateDatabaseAndState`` migrations, and is not something
a restructure can do safely.

Every model is re-exported here, so ``from api.models import X`` resolves for
any model regardless of which module defines it -- exactly as it did when this
package was a single ``models.py``.
"""

# Django's auth model was implicitly re-exported by the previous single-module
# ``models.py``, and several modules import it from here. Kept for compatibility.
from django.contrib.auth.models import User

# --- Core social ------------------------------------------------------------
from .core import (
    Block,
    Category,
    Comment,
    CommentLike,
    CommentReply,
    Competition,
    Draft,
    Follow,
    Mention,
    ModerationAction,
    NotInterested,
    Notification,
    NotificationPreference,
    PushSubscription,
    Quest,
    Reel,
    Report,
    SavedPost,
    Subscription,
    UserProfile,
    UserQuest,
    Vote,
    Winner,
)

# --- Campaigns --------------------------------------------------------------
from .campaign import (
    Campaign,
    CampaignEntry,
    CampaignNotification,
    CampaignVote,
    CampaignWinner,
)
from .campaign_extended import (
    CampaignBadge,
    CampaignScoringConfig,
    CampaignTheme,
    GamificationActivity,
    GrandFinalist,
    JudgeScore,
    Leaderboard,
    LeaderboardEntry,
    PostScore,
    PublicVote,
    SelectedWinner,
    UserCampaignStats,
    WinnerFrequencyRecord,
    WinnerSelection,
)
from .master_campaign import MasterCampaign, MasterCampaignParticipant

# --- Organizations ----------------------------------------------------------
from .organization import Organization, UserRealm, UserRole

# --- Contest (legacy 90-day system) -----------------------------------------
from .contest import (
    AntiCheatLog,
    CoinPackage,
    CoinTransaction,
    ContestLeaderboard,
    ContestPostScore,
    ContestTimeline,
    EligibilityVerification,
    ExtraEntryPurchase,
    GiftToCreator,
    GrandFinaleEntry,
    PostBoost,
    UserCoinBalance,
    UserSubscription,
    UserTier,
)

# --- Wallet -----------------------------------------------------------------
from .wallet import WalletConfig, WithdrawalRequest

# --- Subscriptions ----------------------------------------------------------
from .subscription import (
    AdminRole,
    ExpiredSubscriptionAction,
    OnevasChargingTransaction,
    OnevasWebhookLog,
    PendingTelebirrMandate,
    PromoCode,
    SubscriptionCoinTransaction,
    SubscriptionFeatureUsage,
    SubscriptionHistory,
    SubscriptionPayment,
    SubscriptionPlan,
    SubscriptionReport,
    SubscriptionTier,
    TrialPopupLog,
    UserPromoUsage,
)

# --- TIMWE Master Aggregator ------------------------------------------------
from .timwe import (
    TimweChargeTransaction,
    TimweSyncOrderLog,
)

# --- Payments ---------------------------------------------------------------
from .direct_debit import B2CPaymentTransaction, DirectDebitMandate, DirectDebitTransaction

# --- Advertising ------------------------------------------------------------
from .boost import (
    BoostCampaign,
    BoostConfig,
    BoostEngagement,
    BoostImpression,
    BoostStats,
)

# --- Gifts ------------------------------------------------------------------
from .gift import (
    Gift,
    GiftCombo,
    GiftTransaction,
    UserGiftStats,
    WinnerGiftPackage,
    WinnerGiftTransaction,
)

# --- CRM (Ethio Telecom data-gift integration) -------------------------------
from .crm import CRMGiftAuditLog, CRMGiftPackage, CRMGiftTransaction

# --- Messaging --------------------------------------------------------------
from .messaging import Conversation, Message, MessageRead

# --- Legal ------------------------------------------------------------------
from .legal import (
    ConsentHistory,
    LegalDocument,
    LegalDocumentVersion,
    UserConsent,
    UserLegalAcceptance,
)

# --- Support --------------------------------------------------------------
from .support import SupportRequest

# --- Auth -------------------------------------------------------------------
# NOT re-exported. ``api/models/auth.py`` declares PhoneOTP and
# PasswordResetToken, but neither has a live table:
#
#   0043 creates both -> 0051 drops PhoneOTP and PasswordResetToken.user
#   -> 0053 recreates PhoneOTP -> 0054 drops PhoneOTP again
#
# Importing them here would register them with the app registry and make
# ``makemigrations`` want to recreate the tables, which is a schema change this
# module must not cause. The modules that use them import lazily inside the
# function body, exactly as before. See the restructure report: those code paths
# raise a database error at runtime and need a separate fix.

# --- Platform administration ------------------------------------------------
from .admin import (
    APIKey,
    AdminNotification,
    PlatformMetrics,
    PlatformSettings,
    SecurityEvent,
    SystemLog,
)

__all__ = [
    'Organization',
    'UserRealm',
    'UserRole',
    # re-exported for backward compatibility
    'User',
    # core
    'Block',
    'Category',
    'Comment',
    'CommentLike',
    'CommentReply',
    'Competition',
    'Draft',
    'Follow',
    'Mention',
    'ModerationAction',
    'NotInterested',
    'Notification',
    'NotificationPreference',
    'PushSubscription',
    'Quest',
    'Reel',
    'Report',
    'SavedPost',
    'Subscription',
    'UserProfile',
    'UserQuest',
    'Vote',
    'Winner',
    # campaigns
    'Campaign',
    'CampaignEntry',
    'CampaignNotification',
    'CampaignVote',
    'CampaignWinner',
    'CampaignBadge',
    'CampaignScoringConfig',
    'CampaignTheme',
    'GamificationActivity',
    'GrandFinalist',
    'JudgeScore',
    'Leaderboard',
    'LeaderboardEntry',
    'PostScore',
    'PublicVote',
    'SelectedWinner',
    'UserCampaignStats',
    'WinnerFrequencyRecord',
    'WinnerSelection',
    'MasterCampaign',
    'MasterCampaignParticipant',
    # contest
    'AntiCheatLog',
    'CoinPackage',
    'CoinTransaction',
    'ContestLeaderboard',
    'ContestPostScore',
    'ContestTimeline',
    'EligibilityVerification',
    'ExtraEntryPurchase',
    'GiftToCreator',
    'GrandFinaleEntry',
    'PostBoost',
    'UserCoinBalance',
    'UserSubscription',
    'UserTier',
    # wallet
    'WalletConfig',
    'WithdrawalRequest',
    # subscriptions
    'AdminRole',
    'ExpiredSubscriptionAction',
    'OnevasChargingTransaction',
    'OnevasWebhookLog',
    'PendingTelebirrMandate',
    'PromoCode',
    'SubscriptionCoinTransaction',
    'SubscriptionFeatureUsage',
    'SubscriptionHistory',
    'SubscriptionPayment',
    'SubscriptionPlan',
    'SubscriptionReport',
    'SubscriptionTier',
    'TrialPopupLog',
    'UserPromoUsage',
    # payments
    'B2CPaymentTransaction',
    'DirectDebitMandate',
    'DirectDebitTransaction',
    # advertising
    'BoostCampaign',
    'BoostConfig',
    'BoostEngagement',
    'BoostImpression',
    'BoostStats',
    # gifts
    'Gift',
    'GiftCombo',
    'GiftTransaction',
    'UserGiftStats',
    'WinnerGiftPackage',
    'WinnerGiftTransaction',
    # crm
    'CRMGiftAuditLog',
    'CRMGiftPackage',
    'CRMGiftTransaction',
    # messaging
    'Conversation',
    'Message',
    'MessageRead',
    # legal
    'ConsentHistory',
    'LegalDocument',
    'LegalDocumentVersion',
    'UserConsent',
    'UserLegalAcceptance',
    # support
    'SupportRequest',
    # platform administration
    'APIKey',
    'AdminNotification',
    'PlatformMetrics',
    'PlatformSettings',
    'SecurityEvent',
    'SystemLog',
]
