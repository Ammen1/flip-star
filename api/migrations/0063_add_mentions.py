# Generated migration for mention functionality

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        # Was ('api', '0001_initial'), which scheduled this migration immediately
        # after the initial one -- before 0002_comment creates the Comment model
        # that Mention's foreign key points at. Building any fresh database
        # aborted with "Related model 'api.comment' cannot be resolved".
        #
        # 0061 is the real predecessor (0062 does not exist; the numbering has
        # gaps at 18, 19, 62, 64 and 67). Deployed databases are unaffected:
        # they already record 0063 as applied, so nothing replays.
        ('api', '0061_subscriptionplan_setup_otp'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='allow_mentions',
            field=models.BooleanField(default=True, help_text='Allow other users to mention you in comments'),
        ),
        migrations.CreateModel(
            name='Mention',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('comment', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mentions', to='api.comment')),
                ('mentioned_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions_made', to='auth.User')),
                ('mentioned_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions_received', to='auth.User')),
                ('reply', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mentions', to='api.commentreply')),
            ],
        ),
    ]
