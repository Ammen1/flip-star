from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0068_add_coins_to_points_conversion'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SupportRequest',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(
                    choices=[
                        ('account', 'Account'),
                        ('payment', 'Payment / Wallet'),
                        ('technical', 'Technical Issue'),
                        ('content', 'Content / Post'),
                        ('abuse', 'Abuse / Report'),
                        ('suggestion', 'Suggestion / Feedback'),
                        ('other', 'Other'),
                    ],
                    default='other', max_length=20,
                )),
                ('subject', models.CharField(max_length=200)),
                ('message', models.TextField()),
                ('status', models.CharField(
                    choices=[
                        ('received', 'Received'),
                        ('pending', 'Pending'),
                        ('in_progress', 'In Progress'),
                        ('solved', 'Solved'),
                        ('closed', 'Closed'),
                    ],
                    default='received', max_length=20,
                )),
                ('admin_response', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('handled_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='handled_support_requests',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='support_requests',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'support_requests',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['user', '-created_at'], name='support_req_user_id_e1cd47_idx'),
                    models.Index(fields=['status', '-created_at'], name='support_req_status_5b3c4d_idx'),
                ],
            },
        ),
    ]
