"""
Regression tests for api/services/media_sanitization.py -- ported from the
master branch (was api/views.py::_strip_image_metadata / _strip_video_metadata
/ _sanitize_uploaded_media there), missing entirely in the current project
before this change, so uploaded reel photos/videos kept their embedded
EXIF/GPS data all the way through to storage.

No database is needed -- these functions operate purely on in-memory file
objects.
"""
from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from api.services.media_sanitization import sanitize_uploaded_media, strip_image_metadata

pytestmark = pytest.mark.unit


def _jpeg_with_gps_exif(*, lat=(37, 0, 0.0), lon=(122, 0, 0.0), camera_model='TestCameraModel'):
    image = Image.new('RGB', (20, 20), color='blue')
    exif = image.getexif()
    exif[0x8825] = {1: 'N', 2: lat, 3: 'E', 4: lon}  # GPSInfo IFD
    exif[0x0110] = camera_model  # Model tag
    buf = io.BytesIO()
    image.save(buf, format='JPEG', exif=exif.tobytes())
    buf.seek(0)
    return SimpleUploadedFile(name='photo.jpg', content=buf.getvalue(), content_type='image/jpeg')


def test_strip_image_metadata_removes_gps_data():
    upload = _jpeg_with_gps_exif()

    sanitized = strip_image_metadata(upload)

    reloaded = Image.open(io.BytesIO(sanitized.read()))
    reloaded_exif = reloaded.getexif()
    assert 0x8825 not in reloaded_exif, 'GPSInfo EXIF tag must not survive sanitization'


def test_strip_image_metadata_removes_camera_model():
    upload = _jpeg_with_gps_exif(camera_model='iPhone 15 Pro')

    sanitized = strip_image_metadata(upload)

    reloaded_exif = Image.open(io.BytesIO(sanitized.read())).getexif()
    assert 0x0110 not in reloaded_exif


def test_strip_image_metadata_preserves_pixel_content():
    """Sanitization re-encodes, but must not silently corrupt the image."""
    upload = _jpeg_with_gps_exif()

    sanitized = strip_image_metadata(upload)

    reloaded = Image.open(io.BytesIO(sanitized.read()))
    assert reloaded.size == (20, 20)
    assert reloaded.mode in ('RGB', 'L')


def test_strip_image_metadata_preserves_filename_and_content_type():
    upload = _jpeg_with_gps_exif()
    upload.content_type = 'image/jpeg'

    sanitized = strip_image_metadata(upload)

    assert sanitized.name == 'photo.jpg'
    assert sanitized.content_type == 'image/jpeg'


def test_strip_image_metadata_rejects_unsupported_format():
    buf = io.BytesIO()
    Image.new('RGB', (5, 5)).save(buf, format='BMP')
    buf.seek(0)
    upload = SimpleUploadedFile(name='photo.bmp', content=buf.getvalue(), content_type='image/bmp')

    with pytest.raises(ValueError, match='Unsupported image format'):
        strip_image_metadata(upload)


def test_strip_image_metadata_converts_cmyk_jpeg_to_rgb():
    """A CMYK JPEG (common from Adobe exports) exercises the mode-conversion
    branch -- must not crash, and must come out as a normal RGB JPEG."""
    buf = io.BytesIO()
    Image.new('CMYK', (10, 10)).save(buf, format='JPEG')
    buf.seek(0)
    upload = SimpleUploadedFile(name='photo.jpg', content=buf.getvalue(), content_type='image/jpeg')

    sanitized = strip_image_metadata(upload)

    reloaded = Image.open(io.BytesIO(sanitized.read()))
    assert reloaded.mode == 'RGB'


def test_sanitize_uploaded_media_passes_through_falsy_input():
    assert sanitize_uploaded_media(None, is_video=False) is None


def test_sanitize_uploaded_media_routes_images_to_image_stripping():
    upload = _jpeg_with_gps_exif()

    sanitized = sanitize_uploaded_media(upload, is_video=False)

    reloaded_exif = Image.open(io.BytesIO(sanitized.read())).getexif()
    assert 0x8825 not in reloaded_exif
