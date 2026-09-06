"""
Generate media that predates the pipeline producing it.

Thumbnails arrived with FS-04 and the 360p/480p rungs and image widths arrived
after that, so every post older than each of those is missing what the feed now
expects. A video with no thumbnail falls back to its full-size still as a
poster -- a megabyte fetched to show one frame -- and a video with no small
rung serves 720p to a phone on 3G.

Deliberately cautious
---------------------
This walks over user content that already works, so every default errs towards
doing nothing:

  * dry-run unless --commit is passed, because a re-encode is not reversible
  * batched, with a pause between batches, so a backfill of thousands does not
    saturate the encoder or the S3 endpoint that also serves live traffic
  * only rows genuinely missing something; a post with every variant is skipped
    rather than re-encoded
  * queued through the existing Celery task rather than transcoding inline, so
    this command hands off work instead of becoming a second pipeline that can
    drift from the first

The last point is the important one. process_reel_media already knows how to
build every variant, upload it and record it. Re-implementing that here would
create a second definition of "processed" for exactly the posts least able to
tolerate one.
"""

import time

from django.core.management.base import BaseCommand
from django.db.models import Q

from api.models import Reel


class Command(BaseCommand):
    help = 'Queue media processing for posts missing thumbnails or quality variants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Actually queue the work. Without this the command only reports.',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=25,
            help='Reels queued per batch (default 25).',
        )
        parser.add_argument(
            '--sleep',
            type=float,
            default=2.0,
            help='Seconds to pause between batches (default 2.0).',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Stop after this many reels. 0 processes everything.',
        )
        parser.add_argument(
            '--only',
            choices=['thumbnails', 'video', 'images'],
            help='Restrict to one kind of gap instead of all of them.',
        )

    def handle(self, *args, **options):
        commit = options['commit']
        batch_size = options['batch_size']
        pause = options['sleep']
        limit = options['limit']
        only = options.get('only')

        # A reel needs work when it is missing something its media type should
        # have. Videos and images are asked about separately -- an image post
        # has no 360p rung to be missing, and treating that as a gap would
        # re-encode every image on the platform for ever.
        missing_thumbnail = Q(thumbnail='') | Q(thumbnail__isnull=True)
        has_video = ~Q(media='') & Q(media__isnull=False)
        has_image = ~Q(image='') & Q(image__isnull=False)

        missing_video_rungs = has_video & (Q(media_360='') | Q(media_480=''))
        missing_image_widths = has_image & (Q(image_small='') | Q(image_medium=''))

        if only == 'thumbnails':
            gaps = missing_thumbnail
        elif only == 'video':
            gaps = missing_video_rungs
        elif only == 'images':
            gaps = missing_image_widths
        else:
            gaps = missing_thumbnail | missing_video_rungs | missing_image_widths

        # A reel with neither media nor image has nothing to generate from, so
        # queueing it would only burn a task to discover that.
        queryset = Reel.objects.filter(gaps).filter(has_video | has_image).order_by('id').only('id')

        total = queryset.count()
        if limit:
            total = min(total, limit)

        self.stdout.write(f'Reels needing media: {total}')
        if total == 0:
            self.stdout.write(self.style.SUCCESS('Nothing to do.'))
            return

        if not commit:
            sample = list(queryset.values_list('id', flat=True)[:10])
            self.stdout.write(f'First ids: {sample}')
            self.stdout.write(
                self.style.WARNING(
                    f'Dry run -- nothing queued. Re-run with --commit to process '
                    f'{total} reel(s) in batches of {batch_size}.'
                )
            )
            return

        from api.tasks import process_reel_media

        queued = 0
        # Paginated by id rather than by offset: queueing changes the rows the
        # filter matches, so an offset-based walk would skip reels as the set
        # shrinks underneath it.
        last_id = 0
        while True:
            batch = list(queryset.filter(id__gt=last_id).values_list('id', flat=True)[:batch_size])
            if not batch:
                break

            for reel_id in batch:
                if limit and queued >= limit:
                    break
                process_reel_media.delay(reel_id)
                queued += 1

            last_id = batch[-1]
            self.stdout.write(f'  queued {queued}/{total}')

            if limit and queued >= limit:
                break
            if pause:
                time.sleep(pause)

        self.stdout.write(self.style.SUCCESS(f'Queued {queued} reel(s) for processing.'))
        self.stdout.write(
            'Work runs on the Celery workers; watch their logs for progress. '
            'Re-running is safe -- reels that finish stop matching the filter.'
        )
