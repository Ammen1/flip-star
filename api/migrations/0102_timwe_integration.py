"""
Add the TIMWE Master Aggregator audit tables.

Additive only. Nothing belonging to OneVAS is touched: OnevasWebhookLog and
OnevasChargingTransaction stay live and serving traffic until the TIMWE
integration is credentialed and cut over, at which point a later migration
removes them.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0101_stabilise_message_media_storage'),
    ]

    operations = [
        migrations.CreateModel(
            name='TimweSyncOrderLog',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    'event_type',
                    models.CharField(
                        choices=[
                            ('subscription', 'Subscription'),
                            ('unsubscription', 'Unsubscription'),
                            ('update', 'Update'),
                            ('unknown', 'Unknown'),
                        ],
                        default='unknown',
                        max_length=20,
                    ),
                ),
                (
                    'update_type',
                    models.IntegerField(
                        blank=True, help_text='1 Add, 2 Delete, 3 Update', null=True
                    ),
                ),
                ('msisdn', models.CharField(blank=True, db_index=True, max_length=30)),
                ('sp_id', models.CharField(blank=True, max_length=21)),
                ('product_id', models.CharField(blank=True, db_index=True, max_length=21)),
                ('service_id', models.CharField(blank=True, max_length=21)),
                ('transaction_id', models.CharField(blank=True, db_index=True, max_length=64)),
                ('order_key', models.CharField(blank=True, max_length=64)),
                ('keyword', models.CharField(blank=True, max_length=32)),
                ('update_reason', models.CharField(blank=True, max_length=16)),
                ('update_time', models.DateTimeField(blank=True, null=True)),
                ('expiry_time', models.DateTimeField(blank=True, null=True)),
                (
                    'raw_payload',
                    models.TextField(help_text='Verbatim SOAP request as received'),
                ),
                ('extensions', models.JSONField(blank=True, default=dict)),
                (
                    'applied',
                    models.BooleanField(
                        default=False,
                        help_text='Whether the subscription change was applied locally',
                    ),
                ),
                (
                    'result_code',
                    models.CharField(
                        blank=True,
                        help_text='Code returned to the MA; 0 is success',
                        max_length=8,
                    ),
                ),
                ('result_description', models.TextField(blank=True)),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    'user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='timwe_sync_logs',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': 'TIMWE Sync Order Log',
                'verbose_name_plural': 'TIMWE Sync Order Logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='TimweChargeTransaction',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ('reference_code', models.CharField(db_index=True, max_length=30, unique=True)),
                ('msisdn', models.CharField(db_index=True, max_length=30)),
                (
                    'amount',
                    models.DecimalField(
                        decimal_places=0,
                        help_text='Whole currency units; the MA rejects a decimal point',
                        max_digits=6,
                    ),
                ),
                ('currency', models.CharField(max_length=3)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('charge_code', models.CharField(blank=True, max_length=30)),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('pending', 'Pending'),
                            ('success', 'Success'),
                            ('failed', 'Failed'),
                            ('timeout', 'Timeout'),
                            ('unknown', 'Unknown'),
                        ],
                        default='pending',
                        max_length=16,
                    ),
                ),
                (
                    'error_code',
                    models.CharField(
                        blank=True,
                        help_text='SVC/POL code returned by the MA',
                        max_length=16,
                    ),
                ),
                ('error_message', models.TextField(blank=True)),
                ('retryable', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                (
                    'subscription_tier',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='timwe_charge_transactions',
                        to='api.subscriptiontier',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='timwe_charge_transactions',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': 'TIMWE Charge Transaction',
                'verbose_name_plural': 'TIMWE Charge Transactions',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='timwesyncorderlog',
            index=models.Index(
                fields=['msisdn', '-created_at'], name='api_timwesy_msisdn_9b1f3a_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='timwesyncorderlog',
            index=models.Index(
                fields=['event_type', '-created_at'], name='api_timwesy_event_t_4c7e21_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='timwechargetransaction',
            index=models.Index(
                fields=['status', '-created_at'], name='api_timwech_status_6d2b84_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='timwechargetransaction',
            index=models.Index(
                fields=['msisdn', '-created_at'], name='api_timwech_msisdn_1e5a07_idx'
            ),
        ),
    ]
