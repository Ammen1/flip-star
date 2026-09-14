"""
Check that READY posts' media is really in storage and readable.

  manage.py check_media                  READY posts from the last 7 days
  manage.py check_media --days 30
  manage.py check_media --reel 50 --reel 51
  manage.py check_media --repair         ... and re-process posts with missing files

"Video unavailable", from the server's side. Every rendition a post
advertises -- the primary file, the 480p/360p rungs, the photo sizes and
their WebP twins, the thumbnail -- is asked for with the app's own
credentials (HEAD: nothing is downloaded) and reported as missing (404),
denied (403) or unreachable. The command also prints how media URLs are
signed and for how long, and how far this server's clock is from storage's:
a signed URL issued by a server whose clock is off is refused by storage.

Read-only unless --repair, which queues the same task reprocess_media does
for posts with a missing file and an original to rebuild from.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import MediaStatus, Reel
from api.services.media_availability import SKEW_TOLERANCE, current_keys, probe_storage


class Command(BaseCommand):
    help = "Check that READY posts' media files exist in storage and can be read"

    def add_arguments(self, parser):
        parser.add_argument(
            '--reel', type=int, action='append', default=[], help='Post id (repeatable).'
        )
        parser.add_argument(
            '--days', type=int, default=7, help='READY posts created in the last N days.'
        )
        parser.add_argument('--limit', type=int, default=500, help='At most N posts.')
        parser.add_argument(
            '--repair',
            action='store_true',
            help='Re-process posts with a missing file (their original is intact).',
        )

    def handle(self, *args, **options):
        from api.tasks.media import process_reel_media

        signed = getattr(settings, 'AWS_QUERYSTRING_AUTH', False) and bool(settings.S3_BUCKET_NAME)
        where = (
            f'{settings.S3_ENDPOINT_URL or "AWS S3"} / {settings.S3_BUCKET_NAME}'
            if settings.S3_BUCKET_NAME
            else f'local filesystem ({settings.MEDIA_ROOT})'
        )
        self.stdout.write(f'storage: {where}')
        self.stdout.write(
            f'media URLs: signed, valid for {getattr(settings, "AWS_QUERYSTRING_EXPIRE", 3600)} s'
            if signed
            else 'media URLs: unsigned (objects are public, or local files)'
        )

        posts = Reel.objects.filter(processing_status=MediaStatus.READY)
        if options['reel']:
            posts = posts.filter(pk__in=options['reel'])
        else:
            posts = posts.filter(created_at__gte=timezone.now() - timedelta(days=options['days']))
        posts = posts.order_by('-created_at')[: options['limit']]

        counts = {'ok': 0, 'missing': 0, 'denied': 0, 'error': 0}
        elsewhere = 0
        skews = []
        repaired = 0
        checked = 0
        for post in posts:
            checked += 1
            keys = current_keys(post)
            if not keys:
                elsewhere += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'  post {post.pk}: no media in this storage (legacy or external URL)'
                    )
                )
                continue
            problems = []
            for field, key in keys.items():
                result = probe_storage(key)
                counts[result.state] = counts.get(result.state, 0) + 1
                if result.skew is not None:
                    skews.append(result.skew)
                if result.state != 'ok':
                    status = f' {result.status}' if result.status else ''
                    problems.append(f'{field} {result.state}{status} ({key})')
            if not problems:
                continue
            for problem in problems:
                self.stdout.write(self.style.ERROR(f'  post {post.pk}: {problem}'))
            has_original = (post.original_media or post.original_image) and not getattr(
                post, 'source_deleted_at', None
            )
            if options['repair'] and has_original and any(' missing' in p for p in problems):
                process_reel_media.delay(post.pk, force=True)
                repaired += 1
                self.stdout.write(f'  post {post.pk}: queued for re-processing')

        self.stdout.write(
            f'checked {checked} post(s): files ok {counts["ok"]}, missing {counts["missing"]}, '
            f'denied {counts["denied"]}, unreachable {counts["error"]}; '
            f'not in this storage {elsewhere}'
        )
        if skews:
            worst = max(skews, key=abs)
            line = f'clock: storage is {worst:+.0f} s from this server'
            self.stdout.write(
                self.style.ERROR(line + ' -- signed URLs will be refused')
                if abs(worst) > SKEW_TOLERANCE
                else line
            )
        if options['repair']:
            self.stdout.write(f'queued {repaired} post(s) for re-processing')
        elif counts['missing']:
            self.stdout.write('run again with --repair to re-process posts with missing files')
