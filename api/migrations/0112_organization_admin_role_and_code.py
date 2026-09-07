"""
Organization code + contact details, and the ADMIN role.

Staged rather than single-shot
------------------------------
``code`` is unique and non-null in its final state, which Django cannot add in
one step to a table that may already hold rows -- there is no default that is
unique. So this migration does the three-step dance the data requires:

    1. add the column nullable and unconstrained
    2. backfill a value for every existing row
    3. tighten to NOT NULL + UNIQUE, once the data can satisfy it

Organization is a new table (added in 0111) and is expected to be empty in
every environment, so the backfill will usually touch nothing. It is written
anyway: "expected to be empty" is an assumption about deployment order, and a
migration that corrupts on a non-empty table is a bad bet against it.

Reversible
----------
Every step has a backwards path. The backfill's reverse is a no-op because
dropping the column discards the values anyway.
"""

import re

from django.db import migrations, models


def _slug(name):
    """A code derived from the organization's name: 'ABC Company' -> 'ABC-COMPANY'."""
    cleaned = re.sub(r'[^A-Za-z0-9]+', '-', (name or '').strip()).strip('-').upper()
    return (cleaned or 'ORG')[:40]


def backfill_codes(apps, schema_editor):
    """Give every existing organization a unique code derived from its name.

    Uniqueness is settled here rather than left to the constraint: two
    organizations named similarly enough to slug identically would otherwise
    fail step 3 with an integrity error and no indication which rows collided.
    A numeric suffix is appended until the code is free.
    """
    Organization = apps.get_model('api', 'Organization')

    taken = set()
    for org in Organization.objects.all().order_by('id'):
        base = _slug(org.name)
        candidate = base
        suffix = 2
        while candidate in taken:
            candidate = f'{base[:44]}-{suffix}'
            suffix += 1
        taken.add(candidate)
        org.code = candidate
        org.save(update_fields=['code'])


def drop_codes(apps, schema_editor):
    """Reverse of the backfill.

    A no-op: step 1's reverse drops the column, taking the values with it.
    Present so the migration is reversible as a whole rather than failing at
    this step.
    """


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0111_user_realm_organization_campaign_owner'),
    ]

    operations = [
        # ── 1. Add nullable, unconstrained ──────────────────────────────────
        migrations.AddField(
            model_name='organization',
            name='code',
            field=models.CharField(
                max_length=50,
                null=True,
                blank=True,
                help_text='Short unique identifier, e.g. ABC-CO. Stable across renames.',
            ),
        ),
        migrations.AddField(
            model_name='organization',
            name='contact_email',
            field=models.EmailField(blank=True, default='', max_length=254),
        ),
        migrations.AddField(
            model_name='organization',
            name='contact_phone',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        # ── 2. Backfill ─────────────────────────────────────────────────────
        migrations.RunPython(backfill_codes, drop_codes),
        # ── 3. Tighten, now that the data can satisfy it ────────────────────
        migrations.AlterField(
            model_name='organization',
            name='code',
            field=models.CharField(
                max_length=50,
                unique=True,
                help_text='Short unique identifier, e.g. ABC-CO. Stable across renames.',
            ),
        ),
        # The ADMIN role. A choices change is metadata only -- no column is
        # rewritten and no existing value becomes invalid, since ADMIN is
        # added alongside MAKER and CHECKER rather than replacing either.
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ADMIN', 'Administrator'),
                    ('MAKER', 'Maker'),
                    ('CHECKER', 'Checker'),
                ],
                db_index=True,
                help_text='Optional responsibility (maker/checker) within the realm.',
                max_length=20,
                null=True,
            ),
        ),
    ]
