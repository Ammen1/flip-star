# Generated migration for global theme settings

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0036_add_view_count_to_reel'),
    ]

    operations = [
        migrations.AddField(
            model_name='platformsettings',
            name='theme_preset',
            field=models.CharField(default='flipstar', help_text='Theme preset name (flipstar, ocean, forest, etc.)', max_length=50),
        ),
        migrations.AddField(
            model_name='platformsettings',
            name='dark_mode_default',
            field=models.BooleanField(default=False, help_text='Default dark mode for all users'),
        ),
        migrations.AddField(
            model_name='platformsettings',
            name='primary_color_override',
            field=models.CharField(blank=True, help_text='Custom primary color or gradient override', max_length=200, null=True),
        ),
    ]
