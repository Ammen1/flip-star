from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0038_messaging'),
    ]

    operations = [
        migrations.AlterField(
            model_name='message',
            name='text',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='message',
            name='media',
            field=models.FileField(blank=True, null=True, upload_to='messages/%Y/%m/'),
        ),
        migrations.AddField(
            model_name='message',
            name='media_type',
            field=models.CharField(
                choices=[
                    ('text', 'Text'),
                    ('image', 'Image'),
                    ('video', 'Video'),
                    ('audio', 'Audio / Voice'),
                    ('file', 'File'),
                ],
                default='text',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='message',
            name='media_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='message',
            name='media_size',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='message',
            name='media_duration',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
