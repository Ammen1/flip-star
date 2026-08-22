# Generated migration for messaging delivery lifecycle

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0054_adminrole_expiredsubscriptionaction_onevaswebhooklog_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name='message',
            name='delivery_status',
            field=models.CharField(
                choices=[
                    ('sending', 'Sending'),
                    ('sent', 'Sent'),
                    ('delivered', 'Delivered'),
                    ('read', 'Read'),
                ],
                default='sent',
                max_length=16,
                db_index=True
            ),
        ),
        migrations.AddField(
            model_name='message',
            name='delivered_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='message',
            name='read_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
