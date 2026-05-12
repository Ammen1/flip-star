from django.db import migrations

def cleanup_broken_video_urls(apps, schema_editor):
    """Delete reels with broken full-URL media fields (before public_id fix)."""
    Reel = apps.get_model('api', 'Reel')
    # Delete reels where media field contains full http URLs (old broken format)
    broken_reels = Reel.objects.filter(media__startswith='https://')
    count = broken_reels.count()
    broken_reels.delete()
    print(f"[cleanup] Deleted {count} reels with broken full-URL media fields.")


def reverse_cleanup(apps, schema_editor):
    pass  # Cannot restore deleted reels


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_cleanup_broken_reels'),
    ]

    operations = [
        migrations.RunPython(cleanup_broken_video_urls, reverse_cleanup),
    ]
