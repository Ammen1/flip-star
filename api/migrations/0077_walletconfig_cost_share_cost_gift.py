from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0076_directdebitmandate_tier'),
    ]

    operations = [
        migrations.AddField(
            model_name='walletconfig',
            name='cost_share',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Coins charged to the user when they share a campaign post (0 = free)',
            ),
        ),
        migrations.AddField(
            model_name='walletconfig',
            name='cost_gift',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Extra coins charged on top of the gift value when sending a gift on a campaign post (0 = free)',
            ),
        ),
        migrations.AlterField(
            model_name='cointransaction',
            name='transaction_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('purchase', 'Coin Purchase'),
                    ('welcome_bonus', 'Welcome Bonus'),
                    ('daily_login', 'Daily Login Bonus'),
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
            ),
        ),
    ]
