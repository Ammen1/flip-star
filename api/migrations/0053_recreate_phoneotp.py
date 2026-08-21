from django.db import migrations, models



class Migration(migrations.Migration):

    dependencies = [
        ('api', '0052_walletconfig_daily_winner_points_and_more'),
    ]

    operations = [
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
            options={
                'indexes': [models.Index(fields=['phone', 'code'], name='api_phoneotp_phone_code_idx')],
            },
        ),
    ]
