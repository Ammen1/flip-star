from django.core.management.base import BaseCommand

from api.models.subscription import SubscriptionTier

# The tiers' provisioning columns (spid / service_id / product_id /
# application_key) are deliberately not written here. They were seeded from
# OneVAS settings, which have been removed -- and product_id is what TIMWE's
# datasync matches a notification to a tier by (api/services/subscription_tiers
# .py), so re-running this must never blank the value already stored.
# `onevas_code` stays: despite the name it is the tier's identifier (A-D), used
# by the telebirr mandate flow.


class Command(BaseCommand):
    help = 'Seed subscription tiers (plans, prices and privileges)'

    def handle(self, *args, **options):
        tiers_data = [
            {
                'name': 'Daily Premium',
                'slug': 'daily',
                'description': '24-hour access to premium features',
                'duration_type': 'daily',
                'duration_days': 1,
                'price_etb': 3.00,
                'price_coins': None,
                'onevas_code': 'A',
                'short_code': '9286',
                'features': ['View all content', 'Basic interactions'],
                'privileges': {
                    'max_posts_per_day': 10,
                    'max_reels_per_day': 5,
                    'max_campaigns_per_month': 0,
                    'max_likes_per_day': 100,
                    'max_comments_per_day': 50,
                    'max_follows_per_day': 20,
                    'priority_support': False,
                    'custom_themes': False,
                    'analytics_access': False,
                    'api_access': False,
                    'ad_free': False,
                    'watermark_free': False,
                    'hd_quality': False,
                    'download_videos': False,
                    'profile_badge': 'Daily Premium',
                },
                'max_posts_per_day': 10,
                'max_reels_per_day': 5,
                'max_campaigns_per_month': 0,
                'max_likes_per_day': 100,
                'max_comments_per_day': 50,
                'max_follows_per_day': 20,
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
                'name': 'Weekly Premium',
                'slug': 'weekly',
                'description': '7-day access to premium features',
                'duration_type': 'weekly',
                'duration_days': 7,
                'price_etb': 20.00,
                'price_coins': None,
                'onevas_code': 'B',
                'short_code': '9286',
                'features': ['View all content', 'Extended interactions', 'HD quality'],
                'privileges': {
                    'max_posts_per_day': 15,
                    'max_reels_per_day': 8,
                    'max_campaigns_per_month': 1,
                    'max_likes_per_day': 200,
                    'max_comments_per_day': 100,
                    'max_follows_per_day': 50,
                    'priority_support': False,
                    'custom_themes': False,
                    'analytics_access': False,
                    'api_access': False,
                    'ad_free': False,
                    'watermark_free': False,
                    'hd_quality': True,
                    'download_videos': False,
                    'profile_badge': 'Weekly Premium',
                },
                'max_posts_per_day': 15,
                'max_reels_per_day': 8,
                'max_campaigns_per_month': 1,
                'max_likes_per_day': 200,
                'max_comments_per_day': 100,
                'max_follows_per_day': 50,
                'priority_support': False,
                'custom_themes': False,
                'analytics_access': False,
                'api_access': False,
                'ad_free': False,
                'watermark_free': False,
                'hd_quality': True,
                'download_videos': False,
                'is_active': True,
                'sort_order': 2,
            },
            {
                'name': 'Monthly Premium',
                'slug': 'monthly',
                'description': '30-day access to all premium features',
                'duration_type': 'monthly',
                'duration_days': 30,
                'price_etb': 70.00,
                'price_coins': None,
                'onevas_code': 'C',
                'short_code': '9286',
                'features': [
                    'All features',
                    'Priority support',
                    'Custom themes',
                    'Analytics',
                    'Ad-free',
                    'Download videos',
                ],
                'privileges': {
                    'max_posts_per_day': 30,
                    'max_reels_per_day': 15,
                    'max_campaigns_per_month': 5,
                    'max_likes_per_day': 500,
                    'max_comments_per_day': 250,
                    'max_follows_per_day': 100,
                    'priority_support': True,
                    'custom_themes': True,
                    'analytics_access': True,
                    'api_access': False,
                    'ad_free': True,
                    'watermark_free': True,
                    'hd_quality': True,
                    'download_videos': True,
                    'profile_badge': 'Monthly Premium',
                },
                'max_posts_per_day': 30,
                'max_reels_per_day': 15,
                'max_campaigns_per_month': 5,
                'max_likes_per_day': 500,
                'max_comments_per_day': 250,
                'max_follows_per_day': 100,
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
                'name': 'OnDemand Premium',
                'slug': 'ondemand',
                'description': 'One-time purchase with 100 coins',
                'duration_type': 'ondemand',
                'duration_days': None,
                'price_etb': 10.00,
                'price_coins': 100,
                'onevas_code': 'D',
                'short_code': '9286',
                'features': ['All features', 'API access', 'Lifetime access'],
                'privileges': {
                    'max_posts_per_day': 50,
                    'max_reels_per_day': 25,
                    'max_campaigns_per_month': 10,
                    'max_likes_per_day': 1000,
                    'max_comments_per_day': 500,
                    'max_follows_per_day': 200,
                    'priority_support': True,
                    'custom_themes': True,
                    'analytics_access': True,
                    'api_access': True,
                    'ad_free': True,
                    'watermark_free': True,
                    'hd_quality': True,
                    'download_videos': True,
                    'profile_badge': 'OnDemand Premium',
                },
                'max_posts_per_day': 50,
                'max_reels_per_day': 25,
                'max_campaigns_per_month': 10,
                'max_likes_per_day': 1000,
                'max_comments_per_day': 500,
                'max_follows_per_day': 200,
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
            tier, created = SubscriptionTier.objects.get_or_create(
                slug=tier_data['slug'], defaults=tier_data
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f'Created tier: {tier.name}'))
            else:
                # Update existing tier
                for key, value in tier_data.items():
                    setattr(tier, key, value)
                tier.save()
                self.stdout.write(self.style.WARNING(f'Updated tier: {tier.name}'))

        self.stdout.write(self.style.SUCCESS('Subscription tiers seeded successfully'))
