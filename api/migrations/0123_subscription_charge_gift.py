"""The daily login bonus becomes a gift for paying.

Adds the per-charge gift amount to each tier, the ledger type its grants are
written under, and the constraint that makes one charge worth exactly one
gift. See api/services/subscription_gift.py.
"""

from django.db import migrations, models

#: What the login bonus paid per day. Seeded so the reward keeps its value
#: per charge on the daily plan, which is the one it replaces most directly.
#: Weekly and monthly tiers are charged less often and so are gifted less
#: often -- set them higher in the admin if they should be worth more.
FORMER_DAILY_LOGIN_BONUS = 3


def seed_gift_amounts(apps, schema_editor):
    """Give every existing tier the amount the login bonus used to pay.

    Without this the field defaults to 0 and the reward silently stops
    existing the moment the login bonus is removed.
    """
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')
    SubscriptionTier.objects.filter(charge_gift_coins=0).update(
        charge_gift_coins=FORMER_DAILY_LOGIN_BONUS
    )


def clear_gift_amounts(apps, schema_editor):
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')
    SubscriptionTier.objects.filter(charge_gift_coins=FORMER_DAILY_LOGIN_BONUS).update(
        charge_gift_coins=0
    )


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0122_timwe_renewal_retries'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptiontier',
            name='charge_gift_coins',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Gift coins granted every time a charge on this tier completes -- daily for a daily plan, weekly for a weekly one. Spendable and giftable, unlike bonus_coins. This replaced the daily login bonus: see api/services/subscription_gift.py.',
            ),
        ),
        migrations.AlterField(
            model_name='cointransaction',
            name='transaction_type',
            field=models.CharField(
                choices=[
                    ('purchase', 'Coin Purchase'),
                    ('welcome_bonus', 'Welcome Bonus'),
                    ('daily_login', 'Daily Login Bonus'),
                    ('subscription_gift', 'Subscription Charge Gift'),
                    ('spin_reward', 'Daily Spin Reward'),
                    ('post_bonus', 'Daily Post Bonus'),
                    ('campaign_join', 'Campaign Join Reward'),
                    ('campaign_winner', 'Campaign Winner Reward'),
                    ('like_received', 'Like Received'),
                    ('comment_reward', 'Quality Comment Reward'),
                    ('referral', 'Referral Bonus'),
                    ('profile_complete', 'Profile Completion'),
                    ('gift_sent', 'Gift Sent'),
                    ('gift_received', 'Gift Received'),
                    ('boost', 'Post Boost'),
                    ('extra_entry', 'Extra Entry'),
                    ('campaign_like', 'Campaign Like Cost'),
                    ('campaign_comment', 'Campaign Comment Cost'),
                    ('campaign_share', 'Campaign Share Cost'),
                    ('campaign_gift_fee', 'Campaign Gift Fee'),
                    ('reward', 'Generic Reward'),
                    ('refund', 'Refund'),
                    ('withdrawal', 'Withdrawal to Birr'),
                    ('admin_adjustment', 'Admin Adjustment'),
                ],
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name='cointransaction',
            constraint=models.UniqueConstraint(
                condition=models.Q(('transaction_type', 'subscription_gift')),
                fields=('transaction_type', 'payment_reference'),
                name='one_subscription_gift_per_payment',
            ),
        ),
        migrations.RunPython(seed_gift_amounts, clear_gift_amounts),
    ]
