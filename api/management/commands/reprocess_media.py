"""
Process a post's media again from its original.

  manage.py reprocess_media --reel 123 --reel 456    specific posts
  manage.py reprocess_media --failed                 every FAILED post (dry run)
  manage.py reprocess_media --failed --commit        ... and actually queue them

For the case the pipeline cannot recover from by itself: a post that FAILED
after its retries -- a codec the encoder did not handle then, an outage that
outlasted the retries -- once the cause is fixed. It queues the same Celery
task with force=True; nothing here encodes anything.

Safe to re-run. The task claims each post, so a post queued twice is processed
once; a READY post re-processed stays READY on its current media until the new
media is in place; and output keys are versioned, so nothing a client already
holds is overwritten. A post whose original was deleted under
MEDIA_SOURCE_RETENTION_DAYS cannot be re-processed and is reported, not queued.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from api.models import MediaStatus, Reel


class Command(BaseCommand):
    help = 'Re-queue media processing for specific posts, or for every failed one'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reel', type=int, action='append', default=[], help='Post id (repeatable).'
        )
        parser.add_argument(
            '--failed', action='store_true', help='Every post whose processing FAILED.'
        )
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Queue the work. Without it --failed only reports; --reel always queues.',
        )

    def handle(self, *args, **options):
        ids = options['reel']
        if not ids and not options['failed']:
            raise CommandError('Pass --reel <id> (repeatable) or --failed.')

        if ids:
            posts = Reel.objects.filter(pk__in=ids)
            missing = set(ids) - set(posts.values_list('pk', flat=True))
            for pk in sorted(missing):
                self.stdout.write(self.style.WARNING(f'  post {pk}: not found'))
            commit = True
        else:
            posts = Reel.objects.filter(processing_status=MediaStatus.FAILED)
            commit = options['commit']

        has_original = ~Q(original_media='') | ~Q(original_image='') | ~Q(media='') | ~Q(image='')
        runnable = posts.filter(has_original, source_deleted_at__isnull=True).order_by('pk')
        gone = posts.exclude(pk__in=runnable.values('pk'))
        for post in gone:
            self.stdout.write(self.style.WARNING(f'  post {post.pk}: original no longer available'))

        total = runnable.count()
        self.stdout.write(f'Posts to re-process: {total}')
        if not total:
            return
        if not commit:
            self.stdout.write(f'First ids: {list(runnable.values_list("pk", flat=True)[:10])}')
            self.stdout.write(
                self.style.WARNING('Dry run -- nothing queued. Re-run with --commit.')
            )
            return

        from api.tasks import process_reel_media

        for pk in runnable.values_list('pk', flat=True):
            process_reel_media.delay(pk, force=True)
        self.stdout.write(self.style.SUCCESS(f'Queued {total} post(s).'))
