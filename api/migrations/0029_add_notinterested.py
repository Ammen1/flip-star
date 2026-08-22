# Generated manually - Add NotInterested model

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0028_wipe_all_posts'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotInterested',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='not_interested_by', to='api.reel')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='not_interested_reels', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='notinterested',
            index=models.Index(fields=['user', 'reel'], name='api_notinte_user_id_7f6b3b_idx'),
        ),
        migrations.AddIndex(
            model_name='notinterested',
            index=models.Index(fields=['user', '-created_at'], name='api_notinte_user_id_e8f9c2_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='notinterested',
            unique_together={('user', 'reel')},
        ),
    ]
