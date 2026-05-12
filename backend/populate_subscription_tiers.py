import os
import django
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.models_subscription import SubscriptionTier

def populate_subscription_tiers():
    """Populate subscription tiers from Onevas configuration"""
    print("🚀 Populating subscription tiers...")
    
    tiers_data = [
        {
            'name': 'Daily Subscription',
            'slug': 'daily',
            'description': 'Daily subscription plan',
            'duration_type': 'daily',
            'duration_days': 1,
            'price_etb': 3.00,
            'price_coins': None,
            'onevas_code': 'A',
            'spid': '300263',
            'service_id': '30026300007331',
            'product_id': '10000302850',
            'application_key': 'UPJG5ZM3X6C9LLDSKKCME4MA86UQRKWV',
            'short_code': '9286',
            'features': ['Daily access', 'Basic features'],
            'privileges': {},
            'max_posts_per_day': 10,
            'max_reels_per_day': 5,
            'max_campaigns_per_month': 5,
            'max_likes_per_day': 50,
            'max_comments_per_day': 20,
            'max_follows_per_day': 30,
            'priority_support': False,
            'custom_themes': False,
            'analytics_access': False,
            'api_access': False,
            'ad_free': False,
            'watermark_free': False,
            'hd_quality': False,
            'download_videos': False,
            'is_active': True,
            'sort_order': 1,
        },
        {
            'name': 'Weekly Subscription',
            'slug': 'weekly',
            'description': 'Weekly subscription plan',
            'duration_type': 'weekly',
            'duration_days': 7,
            'price_etb': 15.00,
            'price_coins': None,
            'onevas_code': 'B',
            'spid': '300263',
            'service_id': '30026300007332',
            'product_id': '10000302851',
            'application_key': 'I6QEX9W5D341NN50QPB0KQ9HW6DH99TQ',
            'short_code': '9286',
            'features': ['Weekly access', 'Basic features', 'Priority support'],
            'privileges': {},
            'max_posts_per_day': 20,
            'max_reels_per_day': 10,
            'max_campaigns_per_month': 10,
            'max_likes_per_day': 100,
            'max_comments_per_day': 50,
            'max_follows_per_day': 60,
            'priority_support': True,
            'custom_themes': False,
            'analytics_access': False,
            'api_access': False,
            'ad_free': False,
            'watermark_free': False,
            'hd_quality': False,
            'download_videos': False,
            'is_active': True,
            'sort_order': 2,
        },
        {
            'name': 'Monthly Subscription',
            'slug': 'monthly',
            'description': 'Monthly subscription plan',
            'duration_type': 'monthly',
            'duration_days': 30,
            'price_etb': 50.00,
            'price_coins': None,
            'onevas_code': 'C',
            'spid': '300263',
            'service_id': '30026300007333',
            'product_id': '10000302852',
            'application_key': '0Y72TFLJP4ZAQ127K0O43IJSD9QAPTWQ',
            'short_code': '9286',
            'features': ['Monthly access', 'All features', 'Priority support', 'Custom themes'],
            'privileges': {},
            'max_posts_per_day': 50,
            'max_reels_per_day': 25,
            'max_campaigns_per_month': 30,
            'max_likes_per_day': 300,
            'max_comments_per_day': 150,
            'max_follows_per_day': 200,
            'priority_support': True,
            'custom_themes': True,
            'analytics_access': True,
            'api_access': False,
            'ad_free': True,
            'watermark_free': True,
            'hd_quality': True,
            'download_videos': True,
            'is_active': True,
            'sort_order': 3,
        },
        {
            'name': 'OnDemand Subscription',
            'slug': 'ondemand',
            'description': 'OnDemand subscription plan - pay per use',
            'duration_type': 'ondemand',
            'duration_days': None,
            'price_etb': 0.00,
            'price_coins': 100,
            'onevas_code': 'D',
            'spid': '300263',
            'service_id': '30026300007334',
            'product_id': '10000302853',
            'application_key': '4CROFBT0EGCM1OK8R88EQBTEZOMI3138',
            'short_code': '9286',
            'features': ['OnDemand access', 'Coin-based'],
            'privileges': {},
            'max_posts_per_day': 100,
            'max_reels_per_day': 50,
            'max_campaigns_per_month': 50,
            'max_likes_per_day': 500,
            'max_comments_per_day': 250,
            'max_follows_per_day': 500,
            'priority_support': True,
            'custom_themes': True,
            'analytics_access': True,
            'api_access': True,
            'ad_free': True,
            'watermark_free': True,
            'hd_quality': True,
            'download_videos': True,
            'is_active': True,
            'sort_order': 4,
        },
    ]
    
    for tier_data in tiers_data:
        tier, created = SubscriptionTier.objects.update_or_create(
            slug=tier_data['slug'],
            defaults=tier_data
        )
        if created:
            print(f"  ✓ Created tier: {tier.name} ({tier.duration_type})")
        else:
            print(f"  ✓ Updated tier: {tier.name} ({tier.duration_type})")
    
    print("\n✅ Subscription tiers populated successfully!")
    print(f"\n📊 Summary:")
    print(f"  • Total tiers: {SubscriptionTier.objects.count()}")
    print(f"  • Active tiers: {SubscriptionTier.objects.filter(is_active=True).count()}")

if __name__ == '__main__':
    populate_subscription_tiers()
