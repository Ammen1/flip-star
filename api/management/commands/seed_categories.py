"""
Seed the post categories used by Explore and the post composer.

Categories are admin-managed and nothing created them, so a fresh database
has none -- which leaves the composer's picker empty and Explore with only its
"All" pill. The slugs below are the filter keys in ?category=<slug>, so
renaming one breaks any link or client already using it; add new rows rather
than editing existing slugs.

Idempotent: matches on slug and updates the display fields, so re-running
after adding a category is safe and never duplicates.
"""

from django.core.management.base import BaseCommand

from api.models import Category

# `icon` is rendered directly by the frontend, which expects an emoji.
CATEGORIES = [
    {'name': 'Dance', 'slug': 'dance', 'icon': '💃', 'order': 1},
    {'name': 'Comedy', 'slug': 'comedy', 'icon': '😂', 'order': 2},
    {'name': 'Music', 'slug': 'music', 'icon': '🎵', 'order': 3},
    {'name': 'Food', 'slug': 'food', 'icon': '🍲', 'order': 4},
    {'name': 'Sports', 'slug': 'sports', 'icon': '⚽', 'order': 5},
    {'name': 'Fashion', 'slug': 'fashion', 'icon': '👗', 'order': 6},
    {'name': 'Travel', 'slug': 'travel', 'icon': '✈️', 'order': 7},
    {'name': 'Education', 'slug': 'education', 'icon': '📚', 'order': 8},
    {'name': 'Lifestyle', 'slug': 'lifestyle', 'icon': '✨', 'order': 9},
    {'name': 'Other', 'slug': 'other', 'icon': '🎬', 'order': 99},
]


class Command(BaseCommand):
    help = 'Seed post categories (idempotent - safe to re-run)'

    def handle(self, *args, **options):
        created = updated = 0

        for entry in CATEGORIES:
            # Keyed on slug, not name: the slug is the API contract, so a
            # renamed display name must update the existing row rather than
            # create a second one and split its posts across both.
            _, was_created = Category.objects.update_or_create(
                slug=entry['slug'],
                defaults={
                    'name': entry['name'],
                    'icon': entry['icon'],
                    'order': entry['order'],
                    'is_active': True,
                },
            )
            created += was_created
            updated += not was_created

        self.stdout.write(self.style.SUCCESS(f'Categories: {created} created, {updated} updated'))
        self.stdout.write(f'Active total: {Category.objects.filter(is_active=True).count()}')
