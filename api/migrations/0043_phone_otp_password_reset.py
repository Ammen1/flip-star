from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    

    dependencies = [
        ('api', '0042_perf_indexes'),
    ]

    operations = [
        # Add phone_number to UserProfile
        migrations.AddField(
            model_name='userprofile',
            name='phone_number',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
        # Create PhoneOTP model
        migrations.CreateModel(
            name='PhoneOTP',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone', models.CharField(db_index=True, max_length=20)),
                ('code', models.CharField(max_length=6)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('verified', models.BooleanField(default=False)),
            ],
            options={'indexes': [models.Index(fields=['phone', 'code'], name='api_phoneotp_phone_code_idx')]},
        ),
        # Create PasswordResetToken model
        migrations.CreateModel(
            name='PasswordResetToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=6)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('used', models.BooleanField(default=False)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='password_reset_token',
                    to='auth.user',
                )),
            ],
        ),
    ]
