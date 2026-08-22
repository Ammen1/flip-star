from django.db import migrations


def fix_broken_media_urls(apps, schema_editor):
    """Null out reel image/media fields that don't have valid Cloudinary https URLs"""
    Reel = apps.get_model('api', 'Reel')
    fixed = 0
    for reel in Reel.objects.all():
        changed = False
        if reel.image and not str(reel.image).startswith('https://'):
            reel.image = ''
            changed = True
        if reel.media and not str(reel.media).startswith('https://'):
            reel.media = ''
            changed = True
        if changed:
            reel.save()
            fixed += 1
    print(f'[0022] Fixed {fixed} reels with broken media URLs')


def fix_broken_campaign_images(apps, schema_editor):
    """Null out campaign image fields that don't have valid Cloudinary https URLs"""
    try:
        Campaign = apps.get_model('api', 'Campaign')
        fixed = 0
        for campaign in Campaign.objects.all():
            if campaign.image and not str(campaign.image).startswith('https://'):
                campaign.image = ''
                campaign.save()
                fixed += 1
        print(f'[0022] Fixed {fixed} campaigns with broken image URLs')
    except Exception as e:
        print(f'[0022] Campaign fix skipped: {e}')


def run_fixes(apps, schema_editor):
    fix_broken_media_urls(apps, schema_editor)
    fix_broken_campaign_images(apps, schema_editor)


def reverse_fixes(apps, schema_editor):
    pass  # Cannot reverse data migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_add_hashtags_to_campaign_theme'),
    ]

    operations = [
        migrations.RunPython(run_fixes, reverse_fixes),
    ]
