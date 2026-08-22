from django.db import migrations

BROKEN_PATTERNS = [
    'id.jpg', 'leetcode.png', 'Screenshot_51.png', 'Screenshot_1.png',
    'lctjukfssmi09v63bbrl', 'rryx6fmwiqgzhixhd7rk',
    'demo_video', '/v1/media/reels/', '/v1/media/profile_photos/',
]

BROKEN_CAMPAIGN_PATTERNS = [
    'home.jpg', 'sub.jpg', 'about.jpg', 'sign.jpg',
    '/v1/media/campaigns/',
]


def is_broken(url, patterns):
    if not url:
        return False
    for p in patterns:
        if p in url:
            return True
    return False


def clear_broken_reel_media(apps, schema_editor):
    Reel = apps.get_model('api', 'Reel')
    fixed = 0
    for reel in Reel.objects.all():
        changed = False
        img = str(reel.image) if reel.image else ''
        med = str(reel.media) if reel.media else ''
        if is_broken(img, BROKEN_PATTERNS):
            reel.image = ''
            changed = True
        if is_broken(med, BROKEN_PATTERNS):
            reel.media = ''
            changed = True
        if changed:
            reel.save()
            fixed += 1
    print(f'[0023] Cleared broken media from {fixed} reels')


def clear_broken_campaign_images(apps, schema_editor):
    try:
        Campaign = apps.get_model('api', 'Campaign')
        fixed = 0
        for campaign in Campaign.objects.all():
            img = str(campaign.image) if campaign.image else ''
            if is_broken(img, BROKEN_CAMPAIGN_PATTERNS):
                campaign.image = ''
                campaign.save()
                fixed += 1
        print(f'[0023] Cleared broken images from {fixed} campaigns')
    except Exception as e:
        print(f'[0023] Campaign fix skipped: {e}')


def run_all(apps, schema_editor):
    clear_broken_reel_media(apps, schema_editor)
    clear_broken_campaign_images(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_fix_broken_media_urls'),
    ]

    operations = [
        migrations.RunPython(run_all, migrations.RunPython.noop),
    ]
