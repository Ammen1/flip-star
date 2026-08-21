from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0065_pushsubscription'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaignscoringconfig',
            name='daily_gifts_weight',
            field=models.DecimalField(
                decimal_places=2, default=5.0, max_digits=5,
                help_text='Points per unique gifter on a post (Daily)'
            ),
        ),
        migrations.AddField(
            model_name='campaignscoringconfig',
            name='weekly_gifts_weight',
            field=models.DecimalField(
                decimal_places=2, default=5.0, max_digits=5,
                help_text='Points per unique gifter on a post (Weekly)'
            ),
        ),
        migrations.AddField(
            model_name='campaignscoringconfig',
            name='monthly_gifts_weight',
            field=models.DecimalField(
                decimal_places=2, default=5.0, max_digits=5,
                help_text='Points per unique gifter on a post (Monthly)'
            ),
        ),
        migrations.AddField(
            model_name='campaignscoringconfig',
            name='grand_qualification_gifts_weight',
            field=models.DecimalField(
                decimal_places=2, default=5.0, max_digits=5,
                help_text='Points per unique gifter on a post (Qualification)'
            ),
        ),
    ]
