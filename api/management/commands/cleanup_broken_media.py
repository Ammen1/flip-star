"""
Detach media references that do not point at object storage.

Replaces the unauthenticated ``POST /api/cleanup-reels/`` endpoint, which any
anonymous caller could use to null the media on every Reel and Campaign in the
database (audit finding C-11).

Defaults to a dry run. Destructive execution requires ``--apply`` *and*
``--confirm``, and reports exactly what it changed.

    python manage.py cleanup_broken_media                    # report only
    python manage.py cleanup_broken_media --apply --confirm  # actually detach
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)

VALID_PREFIX = 'https://'


class Command(BaseCommand):
    help = 'Detach Reel/Campaign media whose stored path is not an https:// URL.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Perform the changes. Without this the command only reports.',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Required alongside --apply. Guards against accidental execution.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Process at most N records of each type (0 = no limit).',
        )

    def handle(self, *args, **options):
        from api.models import Reel
        from api.models.campaign import Campaign

        apply_changes = options['apply']
        limit = options['limit']

        if apply_changes and not options['confirm']:
            raise CommandError(
                'Refusing to modify data. --apply requires --confirm as well.\n'
                'Run without --apply first to see what would change.'
            )

        mode = 'APPLY' if apply_changes else 'DRY RUN'
        self.stdout.write(self.style.MIGRATE_HEADING(f'cleanup_broken_media [{mode}]'))

        reels = Reel.objects.all()
        campaigns = Campaign.objects.all()
        if limit:
            reels = reels[:limit]
            campaigns = campaigns[:limit]

        reel_hits: list[tuple[int, list[str]]] = []
        for reel in reels:
            broken = [
                field
                for field in ('image', 'media')
                if (name := getattr(getattr(reel, field, None), 'name', '') or '')
                and not name.startswith(VALID_PREFIX)
            ]
            if broken:
                reel_hits.append((reel.pk, broken))

        campaign_hits = [
            campaign.pk
            for campaign in campaigns
            if (name := getattr(campaign.image, 'name', '') or '')
            and not name.startswith(VALID_PREFIX)
        ]

        self.stdout.write(f'  reels with non-https media:     {len(reel_hits)}')
        self.stdout.write(f'  campaigns with non-https image: {len(campaign_hits)}')

        if not apply_changes:
            for pk, fields in reel_hits[:20]:
                self.stdout.write(f'    would clear Reel #{pk}: {", ".join(fields)}')
            if len(reel_hits) > 20:
                self.stdout.write(f'    ... and {len(reel_hits) - 20} more')
            self.stdout.write(self.style.WARNING('\nDry run - nothing was modified.'))
            return

        with transaction.atomic():
            for pk, fields in reel_hits:
                updates = {field: None for field in fields}
                Reel.objects.filter(pk=pk).update(**updates)
                logger.info('Cleared %s on reel %s', fields, pk)

            if campaign_hits:
                Campaign.objects.filter(pk__in=campaign_hits).update(image=None)
                logger.info('Cleared image on %d campaigns', len(campaign_hits))

        self.stdout.write(
            self.style.SUCCESS(
                f'Detached media on {len(reel_hits)} reels and {len(campaign_hits)} campaigns.'
            )
        )
