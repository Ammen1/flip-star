"""
Strip EXIF/GPS and other embedded metadata from user uploads before they
reach storage.

Uploaded photos and videos routinely carry embedded GPS coordinates and
device identifiers in their metadata -- persisting them as-is on a
public-facing platform means anyone who downloads a post's original file can
recover where (and often what device) it was taken with. Re-encoding images
and stripping the video container's metadata removes that before the file
is ever written to disk/S3.
"""
import io
import os
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps


def strip_image_metadata(upload_file):
    """Re-encode an uploaded image so EXIF and ancillary metadata are not persisted."""
    upload_file.seek(0)
    image = Image.open(upload_file)

    # Read format before exif_transpose(): it always returns a new Image
    # with .format cleared to None (Pillow 10.2, confirmed for every input
    # format, not just ones that actually needed transposing) -- reading it
    # afterwards silently coerces every upload to the '' -> 'JPEG' fallback
    # below, which both makes the format check dead code and flattens PNG
    # transparency by force-converting everything to JPEG.
    image_format = (image.format or '').upper()
    if image_format in {'', 'JPG'}:
        image_format = 'JPEG'

    if image_format not in {'JPEG', 'PNG', 'WEBP'}:
        raise ValueError(f'Unsupported image format for privacy sanitization: {image_format or "unknown"}')

    image = ImageOps.exif_transpose(image)

    save_kwargs = {}
    sanitized_image = image
    if image_format == 'JPEG':
        if image.mode not in ('RGB', 'L'):
            sanitized_image = image.convert('RGB')
        save_kwargs = {'quality': 95, 'optimize': True}
    elif image_format == 'PNG':
        save_kwargs = {'optimize': True}
    elif image_format == 'WEBP':
        save_kwargs = {'quality': 95, 'method': 6}

    buffer = io.BytesIO()
    sanitized_image.save(buffer, format=image_format, **save_kwargs)
    buffer.seek(0)

    return SimpleUploadedFile(
        name=upload_file.name,
        content=buffer.getvalue(),
        content_type=getattr(upload_file, 'content_type', None) or 'application/octet-stream',
    )


def strip_video_metadata(upload_file):
    """Remove container-level metadata from an uploaded video before storage."""
    suffix = os.path.splitext(upload_file.name)[1] or '.mp4'
    input_path = None
    output_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_input:
            for chunk in upload_file.chunks():
                temp_input.write(chunk)
            input_path = temp_input.name

        output_path = input_path.replace(suffix, f'_clean{suffix}')

        import ffmpeg
        (
            ffmpeg
            .input(input_path)
            .output(output_path, c='copy', map_metadata='-1', movflags='+faststart')
            .overwrite_output()
            .run(quiet=True)
        )

        with open(output_path, 'rb') as sanitized_file:
            return SimpleUploadedFile(
                name=upload_file.name,
                content=sanitized_file.read(),
                content_type=getattr(upload_file, 'content_type', None) or 'application/octet-stream',
            )
    finally:
        for temp_path in (input_path, output_path):
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)


def sanitize_uploaded_media(upload_file, is_video=False):
    """Strip metadata from an uploaded image or video. Pass-through for a falsy upload_file."""
    if not upload_file:
        return upload_file
    return strip_video_metadata(upload_file) if is_video else strip_image_metadata(upload_file)
