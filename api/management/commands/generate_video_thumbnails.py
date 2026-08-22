from django.core.management.base import BaseCommand
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from api.models import Reel
import os
import tempfile
import ffmpeg


class Command(BaseCommand):
    help = 'Generate thumbnails for existing videos that don\'t have them'

    def handle(self, *args, **options):
        # Find all reels that have media (video) but no image (thumbnail)
        videos_without_thumbnails = Reel.objects.filter(
            media__isnull=False,
            media__exact='',
            image__isnull=True
        ) | Reel.objects.filter(
            media__isnull=False,
            media__exact='',
            image=''
        )

        total = videos_without_thumbnails.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No videos without thumbnails found.'))
            return

        self.stdout.write(f'Found {total} videos without thumbnails. Generating thumbnails...')

        success_count = 0
        error_count = 0

        for reel in videos_without_thumbnails:
            try:
                self.stdout.write(f'Processing reel {reel.id} by {reel.user.username}...')
                
                # Get the video file path
                video_path = reel.media.path if hasattr(reel.media, 'path') else None
                
                if not video_path or not os.path.exists(video_path):
                    self.stdout.write(self.style.WARNING(f'  Video file not found locally, skipping.'))
                    error_count += 1
                    continue
                
                # Generate thumbnail
                thumbnail_path = video_path.rsplit('.', 1)[0] + '_thumb.jpg'
                
                (
                    ffmpeg
                    .input(video_path, ss='00:00:01')
                    .output(thumbnail_path, vframes=1, format='image2', vcodec='mjpeg')
                    .overwrite_output()
                    .run(quiet=True)
                )
                
                # Read thumbnail and create Django file
                with open(thumbnail_path, 'rb') as thumb_file:
                    thumbnail_file = SimpleUploadedFile(
                        name=f"{os.path.basename(video_path).rsplit('.', 1)[0]}_thumb.jpg",
                        content=thumb_file.read(),
                        content_type='image/jpeg'
                    )
                
                # Save thumbnail to reel
                reel.image.save(thumbnail_file.name, thumbnail_file, save=True)
                
                # Clean up temp thumbnail
                if os.path.exists(thumbnail_path):
                    os.unlink(thumbnail_path)
                
                self.stdout.write(self.style.SUCCESS(f'  Thumbnail generated successfully.'))
                success_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error generating thumbnail: {str(e)}'))
                error_count += 1
                continue

        self.stdout.write(self.style.SUCCESS(
            f'\nThumbnail generation complete!\n'
            f'Success: {success_count}\n'
            f'Errors: {error_count}\n'
            f'Total: {total}'
        ))
