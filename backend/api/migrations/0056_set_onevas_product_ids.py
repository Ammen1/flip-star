
from django.db import migrations

def set_onevas_product_ids(apps, schema_editor):
    """Set Onevas product IDs for existing subscription tiers"""
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')
    
    # Update product IDs for each duration type
    SubscriptionTier.objects.filter(duration_type='daily').update(product_id='10000302850')
    SubscriptionTier.objects.filter(duration_type='weekly').update(product_id='10000302851')
    SubscriptionTier.objects.filter(duration_type='monthly').update(product_id='10000302852')
    SubscriptionTier.objects.filter(duration_type='ondemand').update(product_id='10000302853')

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0055_alter_subscriptionplan_user'),
    ]

    operations = [
        migrations.RunPython(set_onevas_product_ids),
    ]
