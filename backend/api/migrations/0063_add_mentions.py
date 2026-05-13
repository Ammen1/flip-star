# Generated migration for mention functionality

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='allow_mentions',
            field=models.BooleanField(default=True, help_text='Allow other users to mention you in comments'),
        ),
        # Commented out Mention model creation due to missing comment/commentreply models
        # migrations.CreateModel(
        #     name='Mention',
        #     fields=[
        #         ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        #         ('created_at', models.DateTimeField(auto_now_add=True)),
        #         ('comment', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mentions', to='api.comment')),
        #         ('mentioned_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions_made', to='auth.User')),
        #         ('mentioned_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions_received', to='auth.User')),
        #         ('reply', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mentions', to='api.commentreply')),
        #     ],
        # ),
    ]
