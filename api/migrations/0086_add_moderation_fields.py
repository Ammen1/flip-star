# Generated migration for moderation system enhancements

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0085_boostcampaign_boostconfig_boostengagement_and_more'),
    ]

    operations = [
        # Add moderation fields to UserProfile
        migrations.AddField(
            model_name='userprofile',
            name='is_shadowbanned',
            field=models.BooleanField(default=False, help_text='User is shadow banned - content hidden from others but visible to self'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='ban_expires_at',
            field=models.DateTimeField(null=True, blank=True, help_text='When temporary ban expires (null if not temp banned)'),
        ),
        
        # Add is_hidden field to Reel for soft-delete
        migrations.AddField(
            model_name='reel',
            name='is_hidden',
            field=models.BooleanField(default=False, help_text='Content is hidden/removed by moderation (soft-delete)'),
        ),
        
        # Add moderation notification type to Notification model
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                choices=[
                    ('like', 'Like'),
                    ('comment', 'Comment'),
                    ('follow', 'Follow'),
                    ('mention', 'Mention'),
                    ('gift', 'Gift'),
                    ('moderation', 'Moderation Action'),
                ],
                max_length=20
            ),
        ),
    ]
