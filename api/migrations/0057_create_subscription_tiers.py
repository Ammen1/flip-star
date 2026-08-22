from django.db import migrations
import uuid


def create_subscription_tiers(apps, schema_editor):
    """Create subscription tiers with Onevas product IDs"""
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')
    
    # Create tiers if they don't exist
    tiers = [
        {
            'id': uuid.uuid4(),
            'name': 'Daily',
            'slug': 'daily',
            'description': 'Access for 24 hours',
            'duration_type': 'daily',
            'duration_days': 1,
            'price_etb': 3,
            'price_coins': None,
            'product_id': '10000302850',
            'onevas_code': 'A',
            'spid': '300263',
            'service_id': '30026300007331',
            'application_key': 'UPJG5ZM3X6C9LLDSKKCME4MA86UQRKWV',
            'short_code': '9286',
            'features': ['Full access for 24 hours', 'Ad-free experience', 'HD quality videos'],
            'is_active': True,
            'sort_order': 1
        },
        {
            'id': uuid.uuid4(),
            'name': 'Weekly',
            'slug': 'weekly',
            'description': 'Access for 7 days',
            'duration_type': 'weekly',
            'duration_days': 7,
            'price_etb': 20,
            'price_coins': None,
            'product_id': '10000302851',
            'onevas_code': 'B',
            'spid': '300263',
            'service_id': '30026300007332',
            'application_key': 'I6QEX9W5D341NN50QPB0KQ9HW6DH99TQ',
            'short_code': '9286',
            'features': ['Full access for 7 days', 'Ad-free experience', 'HD quality videos'],
            'is_active': True,
            'sort_order': 2
        },
        {
            'id': uuid.uuid4(),
            'name': 'Monthly',
            'slug': 'monthly',
            'description': 'Access for 30 days',
            'duration_type': 'monthly',
            'duration_days': 30,
            'price_etb': 70,
            'price_coins': None,
            'product_id': '10000302852',
            'onevas_code': 'C',
            'spid': '300263',
            'service_id': '30026300007333',
            'application_key': '0Y72TFLJP4ZAQ127K0O43IJSD9QAPTWQ',
            'short_code': '9286',
            'features': ['Full access for 30 days', 'Ad-free experience', 'HD quality videos'],
            'is_active': True,
            'sort_order': 3
        },
        {
            'id': uuid.uuid4(),
            'name': 'OnDemand',
            'slug': 'ondemand',
            'description': 'Pay per use with coins',
            'duration_type': 'ondemand',
            'duration_days': None,
            'price_etb': 10,
            'price_coins': 100,
            'product_id': '10000302853',
            'onevas_code': 'D',
            'spid': '300263',
            'service_id': '30026300007334',
            'application_key': '4CROFBT0EGCM1OK8R88EQBTEZOMI3138',
            'short_code': '9286',
            'features': ['Flexible payment', 'No recurring charges', 'Use coins as needed'],
            'is_active': True,
            'sort_order': 4
        }
    ]
    
    for tier_data in tiers:
        SubscriptionTier.objects.create(**tier_data)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0056_set_onevas_product_ids'),
    ]

    operations = [
        migrations.RunPython(create_subscription_tiers),
    ]
