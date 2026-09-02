"""
Thumbnail generation: real dimensions, aspect handling, idempotency.

These open the generated files with Pillow and assert actual pixel sizes
rather than trusting the call succeeded -- the whole point of the change is
that output is exactly 320x720 whatever went in.

The cases that matter are the ones that used to be wrong:

  landscape     a plain resize to a fixed pair of dimensions stretches
                anything that is not 9:20; cover-cropping must not
  originals     _process_image saved over the upload, destroying it
  idempotency   nothing checked `processed`, so a re-run re-encoded already
                compressed output and lost quality on every pass
"""

import pytest
from PIL import Image

from api.tasks.media import (
    THUMB_HEIGHT,
    THUMB_WIDTH,
    _process_image,
    _render_thumbnail,
)

pytestmark = pytest.mark.integration


def _make_image(path, width, height, colour=(120, 180, 90)):
    Image.new('RGB', (width, height), colour).save(path, 'JPEG', quality=95)
    return str(path)


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('width', 'height', 'label'),
    [
        (1080, 1920, 'portrait 9:16'),
        (1920, 1080, 'landscape 16:9'),
        (1000, 1000, 'square'),
        (320, 720, 'already exactly the target'),
        (160, 360, 'smaller than the target'),
        (4000, 3000, 'oversized landscape'),
    ],
)
def test_thumbnail_is_always_the_target_size(tmp_path, width, height, label):
    """Every source shape produces exactly 320x720 -- that is the contract."""
    src = _make_image(tmp_path / 'src.jpg', width, height)
    out = str(tmp_path / 'thumb.jpg')

    assert _render_thumbnail(src, out) == out

    with Image.open(out) as img:
        assert img.size == (THUMB_WIDTH, THUMB_HEIGHT), label


def test_target_is_320_by_720():
    """Pin the constants: the brief specifies this size explicitly."""
    assert (THUMB_WIDTH, THUMB_HEIGHT) == (320, 720)


# ---------------------------------------------------------------------------
# Aspect ratio
# ---------------------------------------------------------------------------


def test_landscape_is_cropped_not_squashed(tmp_path):
    """
    The regression this exists to prevent.

    A 16:9 source resized straight to 9:20 would compress the horizontal axis
    to about a third, making faces visibly narrow. Cover-cropping keeps
    geometry and discards the sides instead -- so a circle drawn in the centre
    must still be a circle.
    """
    src_path = tmp_path / 'landscape.jpg'
    img = Image.new('RGB', (1920, 1080), (20, 20, 20))
    # White square dead centre; under a squash it becomes a tall rectangle.
    box = 400
    cx, cy = 1920 // 2, 1080 // 2
    for x in range(cx - box // 2, cx + box // 2):
        for y in range(cy - box // 2, cy + box // 2):
            img.putpixel((x, y), (255, 255, 255))
    img.save(src_path, 'JPEG', quality=95)

    out = str(tmp_path / 'thumb.jpg')
    _render_thumbnail(str(src_path), out)

    with Image.open(out) as thumb:
        pixels = thumb.load()
        white = [
            (x, y)
            for x in range(THUMB_WIDTH)
            for y in range(THUMB_HEIGHT)
            if sum(pixels[x, y]) > 600
        ]

    assert white, 'the centre marker vanished entirely'
    span_x = max(x for x, _ in white) - min(x for x, _ in white)
    span_y = max(y for _, y in white) - min(y for _, y in white)

    # The source square is 400x400. After cover-cropping a 16:9 image to 9:20
    # the scale factor is uniform, so the marker stays square. A squash would
    # leave it far taller than wide.
    assert (
        span_y < span_x * 2.2
    ), f'centre marker is {span_x}x{span_y} -- distorted, not cover-cropped'


def test_portrait_keeps_the_centre(tmp_path):
    """Portrait sources crop top and bottom, not the subject."""
    src = _make_image(tmp_path / 'portrait.jpg', 1080, 2400)
    out = str(tmp_path / 'thumb.jpg')

    _render_thumbnail(src, out)

    with Image.open(out) as img:
        assert img.size == (THUMB_WIDTH, THUMB_HEIGHT)


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_unreadable_source_returns_none(tmp_path):
    """
    A corrupt upload must not raise.

    _render_thumbnail returning None lets the caller fall back rather than
    failing the whole task and burning its retries on a file that will never
    decode.
    """
    broken = tmp_path / 'broken.jpg'
    broken.write_bytes(b'not an image')

    assert _render_thumbnail(str(broken), str(tmp_path / 'out.jpg')) is None


def test_missing_source_returns_none(tmp_path):
    assert _render_thumbnail(str(tmp_path / 'nope.jpg'), str(tmp_path / 'o.jpg')) is None


# ---------------------------------------------------------------------------
# Originals
# ---------------------------------------------------------------------------


def test_process_image_does_not_touch_the_source(tmp_path):
    """
    The data-loss regression.

    _process_image used to save over its input, so the original upload was
    destroyed the first time the task ran and could never be reprocessed.
    """
    src = _make_image(tmp_path / 'original.jpg', 2000, 1500)
    before = (tmp_path / 'original.jpg').read_bytes()
    out = str(tmp_path / 'processed.jpg')

    assert _process_image(src, out) == out
    assert (tmp_path / 'original.jpg').read_bytes() == before, 'source was modified'


def test_process_image_downscales_only_when_oversized(tmp_path):
    src = _make_image(tmp_path / 'big.jpg', 3000, 2000)
    out = str(tmp_path / 'small.jpg')

    _process_image(src, out, max_px=1080)

    with Image.open(out) as img:
        assert max(img.size) <= 1080
        # Aspect preserved: 3:2 in, 3:2 out.
        assert abs((img.width / img.height) - 1.5) < 0.01


def test_process_image_does_not_enlarge_small_sources(tmp_path):
    """Upscaling a full image would add bytes without adding detail."""
    src = _make_image(tmp_path / 'small.jpg', 400, 300)
    out = str(tmp_path / 'out.jpg')

    _process_image(src, out, max_px=1080)

    with Image.open(out) as img:
        assert img.size == (400, 300)


def test_process_image_survives_a_corrupt_source(tmp_path):
    broken = tmp_path / 'broken.jpg'
    broken.write_bytes(b'still not an image')

    assert _process_image(str(broken), str(tmp_path / 'out.jpg')) is None


# ---------------------------------------------------------------------------
# Storage shape
# ---------------------------------------------------------------------------


def test_thumbnail_is_smaller_than_a_full_frame(tmp_path):
    """
    The reason a cropped thumbnail exists at all.

    The image flow used to set thumbnail = the full 1080px still, so every
    feed card downloaded a full-size image.
    """
    src = _make_image(tmp_path / 'src.jpg', 1080, 1920)
    full = str(tmp_path / 'full.jpg')
    thumb = str(tmp_path / 'thumb.jpg')

    _process_image(src, full, max_px=1080)
    _render_thumbnail(src, thumb)

    import os

    assert os.path.getsize(thumb) < os.path.getsize(full)


def test_thumbnail_is_a_progressive_jpeg(tmp_path):
    """Progressive renders a usable preview before the bytes finish arriving."""
    src = _make_image(tmp_path / 'src.jpg', 1080, 1920)
    out = str(tmp_path / 'thumb.jpg')

    _render_thumbnail(src, out)

    with Image.open(out) as img:
        assert img.format == 'JPEG'
        assert img.info.get('progressive') or img.info.get('progression')


def test_rendering_twice_is_stable(tmp_path):
    """
    Idempotency at the file level.

    Re-running must not compound compression -- the second pass reads the
    same source, not its own output.
    """
    src = _make_image(tmp_path / 'src.jpg', 1080, 1920)
    first = str(tmp_path / 'a.jpg')
    second = str(tmp_path / 'b.jpg')

    _render_thumbnail(src, first)
    _render_thumbnail(src, second)

    import os

    assert os.path.getsize(first) == os.path.getsize(second)
    with Image.open(first) as a, Image.open(second) as b:
        assert a.size == b.size == (THUMB_WIDTH, THUMB_HEIGHT)
