"""
Quality variants: the ladders, and the API contract that exposes them.

Why the ladders exist
---------------------
The pipeline produced one 720p transcode and one full-size still. For an
audience on Ethiopian mobile data that is often the difference between a video
that plays and one that buffers to a stop -- and the feed was fetching a
full-resolution image as a video POSTER, a megabyte to show one frame.

What these guard
----------------
  additive      every new field is optional and omitted when empty, so a client
                written before they existed sees the response it always saw
  no upscaling  a 480p source must not gain a manufactured 720p rung: larger,
                slower, no sharper
  partial ok    one failed rung must not cost the post; whatever encoded is
                advertised and the rest are simply absent
"""

import pytest
from django.contrib.auth.models import User

from api.models import Reel
from api.serializers.core import ReelSerializer
from api.tasks.media import IMAGE_LADDER, VIDEO_LADDER, _resize_image

pytestmark = pytest.mark.django_db


@pytest.fixture
def author():
    return User.objects.create_user(username='variant_author', password='x')


def serialize(reel):
    return ReelSerializer(reel, context={'request': None}).data


# ---------------------------------------------------------------------------
# The ladders
# ---------------------------------------------------------------------------


def test_video_ladder_covers_the_low_bandwidth_rungs():
    heights = [height for _f, height, _c in VIDEO_LADDER]
    assert heights == [360, 480, 720]


def test_no_1080p_rung():
    """
    Deliberately absent.

    The source is phone video and the feed renders a phone-width column, so a
    1080p rung costs storage and encode time to serve pixels nobody sees.
    """
    assert 1080 not in [height for _f, height, _c in VIDEO_LADDER]


def test_smaller_rungs_compress_harder():
    """A small frame tolerates more compression before artefacts show, and the
    point of the rung is bytes rather than fidelity."""
    crfs = [crf for _f, _h, crf in VIDEO_LADDER]
    assert crfs == sorted(crfs, reverse=True), f'CRF should fall as height rises: {crfs}'


def test_image_ladder_covers_phone_widths():
    assert [width for _f, width in IMAGE_LADDER] == [360, 720]


# ---------------------------------------------------------------------------
# Resizing
# ---------------------------------------------------------------------------


def _make_image(path, width, height):
    from PIL import Image

    Image.new('RGB', (width, height), (90, 140, 200)).save(path, 'JPEG', quality=95)
    return str(path)


def test_resize_produces_the_requested_width(tmp_path):
    from PIL import Image

    src = _make_image(tmp_path / 'src.jpg', 1600, 1200)
    out = str(tmp_path / 'out.jpg')

    assert _resize_image(src, out, 360) == out
    with Image.open(out) as img:
        assert img.width == 360


def test_resize_keeps_the_aspect_ratio(tmp_path):
    """These stand in for the post body, unlike the 320x720 thumbnail crop --
    a changed aspect would distort the picture rather than frame it."""
    from PIL import Image

    src = _make_image(tmp_path / 'src.jpg', 1600, 900)
    out = str(tmp_path / 'out.jpg')

    _resize_image(src, out, 720)
    with Image.open(out) as img:
        assert abs((img.width / img.height) - (1600 / 900)) < 0.02


def test_resize_refuses_to_upscale(tmp_path):
    """
    A source narrower than the target is left alone.

    Enlarging adds bytes without adding detail, and returning None lets the
    caller serve the original instead of a bigger copy of it.
    """
    src = _make_image(tmp_path / 'small.jpg', 300, 400)

    assert _resize_image(src, str(tmp_path / 'out.jpg'), 720) is None


def test_resize_survives_a_corrupt_source(tmp_path):
    broken = tmp_path / 'broken.jpg'
    broken.write_bytes(b'not an image')

    assert _resize_image(str(broken), str(tmp_path / 'out.jpg'), 360) is None


def test_resize_output_is_progressive(tmp_path):
    """Progressive renders a usable image before the bytes finish arriving --
    the whole point on a slow link."""
    from PIL import Image

    src = _make_image(tmp_path / 'src.jpg', 1200, 800)
    out = str(tmp_path / 'out.jpg')

    _resize_image(src, out, 360)
    with Image.open(out) as img:
        assert img.info.get('progressive') or img.info.get('progression')


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------


def test_a_post_without_variants_omits_them(author):
    """
    Backward compatibility, stated as a test.

    Every post predating the ladders has empty variant fields. The response
    must carry null rather than an empty object or a broken URL, so an old
    client and an old post both behave exactly as before.
    """
    reel = Reel.objects.create(user=author, caption='old post', media='reels/old.mp4')

    data = serialize(reel)

    assert data['media_variants'] is None
    assert data['image_variants'] is None
    # The primary is untouched -- that is what existing clients read.
    assert data['media']


def test_video_variants_are_exposed_when_present(author):
    reel = Reel.objects.create(
        user=author,
        caption='new post',
        media='reels/processed/reel_1_720p.mp4',
        media_360='reels/processed/reel_1_360p.mp4',
        media_480='reels/processed/reel_1_480p.mp4',
    )

    variants = serialize(reel)['media_variants']

    assert set(variants) == {'360', '480'}
    assert '360p' in variants['360']


def test_a_partially_encoded_post_advertises_only_what_exists(author):
    """
    One failed rung must not cost the post.

    The encoder is best-effort per rung, so a post with 360p but no 480p is a
    normal outcome -- and the client must be able to see that rather than
    request a URL that was never written.
    """
    reel = Reel.objects.create(
        user=author,
        caption='partial',
        media='reels/processed/reel_2_720p.mp4',
        media_360='reels/processed/reel_2_360p.mp4',
    )

    variants = serialize(reel)['media_variants']

    assert set(variants) == {'360'}


def test_image_variants_are_exposed_when_present(author):
    reel = Reel.objects.create(
        user=author,
        caption='picture',
        image='reels/reel_3.jpg',
        image_small='reels/variants/reel_3_360w.jpg',
        image_medium='reels/variants/reel_3_720w.jpg',
    )

    variants = serialize(reel)['image_variants']

    assert set(variants) == {'360', '720'}


def test_the_existing_fields_are_all_still_served(author):
    """
    The additive guarantee.

    Anything a client reads today must survive; this fails if a field is
    renamed or dropped rather than added alongside.
    """
    reel = Reel.objects.create(user=author, caption='c', media='reels/x.mp4')

    data = serialize(reel)

    for field in (
        'id',
        'user',
        'image',
        'media',
        'thumbnail',
        'blurhash',
        'duration',
        'processed',
        'caption',
        'votes',
        'view_count',
        'comment_count',
        'shares',
        'created_at',
        'is_liked',
        'is_saved',
        'category',
    ):
        assert field in data, f'{field} disappeared from the response'
