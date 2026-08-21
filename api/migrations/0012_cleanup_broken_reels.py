from django.db import migrations



def cleanup_broken_reels(apps, schema_editor):
    """Delete all reels whose media files were on Render's ephemeral filesystem (now wiped)."""
    Reel = apps.get_model('api', 'Reel')
    count = Reel.objects.count()
    Reel.objects.all().delete()
    print(f"[cleanup] Deleted {count} reels with broken ephemeral-storage media URLs.")


def reverse_cleanup(apps, schema_editor):
    pass  # Cannot restore deleted reels


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_report'),
    ]

    operations = [
        migrations.RunPython(cleanup_broken_reels, reverse_cleanup),
    ]
