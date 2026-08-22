# Generated migration for extended campaign system

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0017_coinpackage_contesttimeline_usersubscription_and_more'),
    ]

    operations = [
        # Create CampaignScoringConfig model
        migrations.CreateModel(
            name='CampaignScoringConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('max_creativity_points', models.DecimalField(decimal_places=2, default=30, help_text='Max points for creativity', max_digits=5)),
                ('max_engagement_points', models.DecimalField(decimal_places=2, default=25, help_text='Max points for engagement', max_digits=5)),
                ('max_consistency_points', models.DecimalField(decimal_places=2, default=20, help_text='Max points for consistency', max_digits=5)),
                ('max_quality_points', models.DecimalField(decimal_places=2, default=15, help_text='Max points for quality', max_digits=5)),
                ('max_theme_relevance_points', models.DecimalField(decimal_places=2, default=10, help_text='Max points for theme relevance', max_digits=5)),
                ('likes_weight', models.DecimalField(decimal_places=2, default=0.6, help_text='Weight for likes in engagement score', max_digits=5)),
                ('comments_weight', models.DecimalField(decimal_places=2, default=1.5, help_text='Weight for comments in engagement score', max_digits=5)),
                ('shares_weight', models.DecimalField(decimal_places=2, default=2.0, help_text='Weight for shares in engagement score', max_digits=5)),
                ('streak_points_per_day', models.DecimalField(decimal_places=2, default=1.0, help_text='Points per day of streak', max_digits=5)),
                ('participation_points_per_day', models.DecimalField(decimal_places=2, default=0.5, help_text='Points per day participated', max_digits=5)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('campaign', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='scoring_config', to='api.campaign')),
            ],
            options={
                'verbose_name': 'Campaign Scoring Configuration',
                'verbose_name_plural': 'Campaign Scoring Configurations',
            },
        ),
        
        # Add campaign fields to Reel
        migrations.AddField(
            model_name='reel',
            name='campaign',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='campaign_posts', to='api.campaign'),
        ),
        migrations.AddField(
            model_name='reel',
            name='is_campaign_post',
            field=models.BooleanField(default=False),
        ),
        
        # Create CampaignTheme model
        migrations.CreateModel(
            name='CampaignTheme',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField()),
                ('week_number', models.IntegerField(help_text='Week 1, 2, 3, etc.')),
                ('start_date', models.DateTimeField()),
                ('end_date', models.DateTimeField()),
                ('is_active', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='themes', to='api.campaign')),
            ],
            options={
                'ordering': ['campaign', 'week_number'],
                'unique_together': {('campaign', 'week_number')},
            },
        ),
        
        # Add theme field to Reel
        migrations.AddField(
            model_name='reel',
            name='theme',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='theme_posts', to='api.campaigntheme'),
        ),
        
        # Create PostScore model
        migrations.CreateModel(
            name='PostScore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('moderation_status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20)),
                ('rejection_reason', models.TextField(blank=True)),
                ('moderated_at', models.DateTimeField(blank=True, null=True)),
                ('creativity_score', models.DecimalField(decimal_places=2, default=0, help_text='Max 30 points', max_digits=5)),
                ('engagement_score', models.DecimalField(decimal_places=2, default=0, help_text='Max 25 points', max_digits=5)),
                ('consistency_score', models.DecimalField(decimal_places=2, default=0, help_text='Max 20 points', max_digits=5)),
                ('quality_score', models.DecimalField(decimal_places=2, default=0, help_text='Max 15 points', max_digits=5)),
                ('theme_relevance_score', models.DecimalField(decimal_places=2, default=0, help_text='Max 10 points', max_digits=5)),
                ('total_score', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='post_scores', to='api.campaign')),
                ('moderated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='moderated_posts', to=settings.AUTH_USER_MODEL)),
                ('reel', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='campaign_score', to='api.reel')),
                ('theme', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='post_scores', to='api.campaigntheme')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='campaign_scores', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-total_score', '-created_at'],
            },
        ),
        
        # Create UserCampaignStats model
        migrations.CreateModel(
            name='UserCampaignStats',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_posts', models.IntegerField(default=0)),
                ('approved_posts', models.IntegerField(default=0)),
                ('rejected_posts', models.IntegerField(default=0)),
                ('total_score', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('average_score', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('days_participated', models.IntegerField(default=0)),
                ('current_streak', models.IntegerField(default=0)),
                ('longest_streak', models.IntegerField(default=0)),
                ('last_post_date', models.DateField(blank=True, null=True)),
                ('daily_rank', models.IntegerField(blank=True, null=True)),
                ('weekly_rank', models.IntegerField(blank=True, null=True)),
                ('monthly_rank', models.IntegerField(blank=True, null=True)),
                ('overall_rank', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_stats', to='api.campaign')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='campaign_stats', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-total_score'],
                'unique_together': {('user', 'campaign')},
            },
        ),
        
        # Create Leaderboard model
        migrations.CreateModel(
            name='Leaderboard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_type', models.CharField(choices=[('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly'), ('overall', 'Overall')], max_length=20)),
                ('period_start', models.DateTimeField()),
                ('period_end', models.DateTimeField()),
                ('is_current', models.BooleanField(default=True)),
                ('is_finalized', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='leaderboards', to='api.campaign')),
            ],
            options={
                'ordering': ['-period_start'],
            },
        ),
        
        # Create LeaderboardEntry model
        migrations.CreateModel(
            name='LeaderboardEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rank', models.IntegerField()),
                ('score', models.DecimalField(decimal_places=2, max_digits=10)),
                ('posts_count', models.IntegerField(default=0)),
                ('bonus_points', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('leaderboard', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='entries', to='api.leaderboard')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='leaderboard_entries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['rank'],
                'unique_together': {('leaderboard', 'user')},
            },
        ),
        
        # Create WinnerSelection model
        migrations.CreateModel(
            name='WinnerSelection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('selection_type', models.CharField(choices=[('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly'), ('grand', 'Grand Finale')], max_length=20)),
                ('top_scorers_percentage', models.IntegerField(default=70, help_text='Percentage from top scorers')),
                ('random_participants_percentage', models.IntegerField(default=30, help_text='Percentage from random active users')),
                ('is_finalized', models.BooleanField(default=False)),
                ('finalized_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='winner_selections', to='api.campaign')),
                ('finalized_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='finalized_selections', to=settings.AUTH_USER_MODEL)),
                ('leaderboard', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='winner_selections', to='api.leaderboard')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        # Create SelectedWinner model
        migrations.CreateModel(
            name='SelectedWinner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rank', models.IntegerField()),
                ('final_score', models.DecimalField(decimal_places=2, max_digits=10)),
                ('selection_method', models.CharField(choices=[('top_scorer', 'Top Scorer'), ('random', 'Random Selection')], max_length=20)),
                ('prize_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('prize_claimed', models.BooleanField(default=False)),
                ('prize_claimed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('selection', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='winners', to='api.winnerselection')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='campaign_winner_selections', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['rank'],
                'unique_together': {('selection', 'rank')},
            },
        ),
        
        # Create CampaignBadge model
        migrations.CreateModel(
            name='CampaignBadge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('badge_type', models.CharField(choices=[('participation', 'Participation'), ('consistency', 'Consistency'), ('top_scorer', 'Top Scorer'), ('winner', 'Winner'), ('engagement_king', 'Engagement King')], max_length=50)),
                ('title', models.CharField(max_length=100)),
                ('description', models.TextField()),
                ('icon', models.CharField(blank=True, help_text='Emoji or icon identifier', max_length=50)),
                ('earned_at', models.DateTimeField(auto_now_add=True)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='badges', to='api.campaign')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='campaign_badges', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-earned_at'],
            },
        ),
        
        # Add indexes
        migrations.AddIndex(
            model_name='reel',
            index=models.Index(fields=['campaign', '-created_at'], name='api_reel_campaig_idx'),
        ),
        migrations.AddIndex(
            model_name='reel',
            index=models.Index(fields=['is_campaign_post', '-created_at'], name='api_reel_is_camp_idx'),
        ),
        migrations.AddIndex(
            model_name='postscore',
            index=models.Index(fields=['campaign', '-total_score'], name='api_postscor_campaig_idx'),
        ),
        migrations.AddIndex(
            model_name='postscore',
            index=models.Index(fields=['user', 'campaign'], name='api_postscor_user_ca_idx'),
        ),
        migrations.AddIndex(
            model_name='usercampaignstats',
            index=models.Index(fields=['campaign', '-total_score'], name='api_usercam_campaig_idx'),
        ),
        migrations.AddIndex(
            model_name='leaderboard',
            index=models.Index(fields=['campaign', 'period_type', '-period_start'], name='api_leaderb_campaig_idx'),
        ),
        migrations.AddIndex(
            model_name='leaderboardentry',
            index=models.Index(fields=['leaderboard', 'rank'], name='api_leaderb_leaderb_idx'),
        ),
    ]
