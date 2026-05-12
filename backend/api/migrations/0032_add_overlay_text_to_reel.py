from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0031_add_report_moderation_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='reel',
            name='overlay_text',
            field=models.TextField(blank=True, default=''),
        ),
    ]
