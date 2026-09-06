"""
The backfill command: what it selects, and what it refuses to touch.

This walks over content that already works and queues re-encodes for it, so
the interesting behaviour is all in the negative space -- what it leaves
alone. A selection bug here is not a failed test run, it is thousands of
needless transcodes against the same S3 endpoint that serves the live feed.

The three that matter
---------------------
  dry-run     the default must queue nothing at all, because a re-encode is
              not reversible
  precision   an image post has no 360p rung to be missing; treating that as a
              gap would re-queue every image on the platform on every run
  idempotent  a reel that finishes stops matching, so re-running settles
"""

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from api.models import Reel

pytestmark = pytest.mark.django_db


@pytest.fixture
def author():
    return User.objects.create_user(username='backfill_author', password='x')


@pytest.fixture
def queued(monkeypatch):
    """Capture what would be queued instead of reaching a broker."""
    calls = []

    class FakeTask:
        @staticmethod
        def delay(reel_id):
            calls.append(reel_id)

    import api.tasks

    monkeypatch.setattr(api.tasks, 'process_reel_media', FakeTask, raising=False)
    return calls


def run(**kwargs):
    kwargs.setdefault('sleep', 0)
    call_command('generate_missing_media', **kwargs)


# ---------------------------------------------------------------------------
# The default is to do nothing
# ---------------------------------------------------------------------------


def test_dry_run_queues_nothing(author, queued):
    """
    The safety property.

    Without --commit the command reports and exits. Anyone running it to see
    the size of the backlog must not thereby start it.
    """
    Reel.objects.create(user=author, media='reels/a.mp4', thumbnail='')

    run()

    assert queued == []


def test_commit_is_what_queues(author, queued):
    reel = Reel.objects.create(user=author, media='reels/a.mp4', thumbnail='')

    run(commit=True)

    assert queued == [reel.id]


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_a_fully_processed_video_is_left_alone(author, queued):
    """Nothing is missing, so re-encoding would spend the encoder to produce
    files that already exist."""
    Reel.objects.create(
        user=author,
        media='reels/processed/x_720p.mp4',
        media_360='reels/processed/x_360p.mp4',
        media_480='reels/processed/x_480p.mp4',
        thumbnail='thumbnails/x.jpg',
    )

    run(commit=True)

    assert queued == []


def test_an_image_post_is_not_judged_on_video_rungs(author, queued):
    """
    The precision case.

    An image post has empty media_360 and media_480 for ever -- it has no
    video. If the query asked about those unconditionally, every image on the
    platform would match on every run, permanently.
    """
    Reel.objects.create(
        user=author,
        image='reels/pic.jpg',
        image_small='reels/variants/pic_360w.jpg',
        image_medium='reels/variants/pic_720w.jpg',
        thumbnail='thumbnails/pic.jpg',
    )

    run(commit=True)

    assert queued == []


def test_a_video_post_is_not_judged_on_image_widths(author, queued):
    """The mirror of the above: a video has no image variants to be missing."""
    Reel.objects.create(
        user=author,
        media='reels/processed/v_720p.mp4',
        media_360='reels/processed/v_360p.mp4',
        media_480='reels/processed/v_480p.mp4',
        thumbnail='thumbnails/v.jpg',
    )

    run(commit=True)

    assert queued == []


def test_a_reel_with_no_media_at_all_is_skipped(author, queued):
    """
    Nothing to generate from.

    Queueing it would burn a worker task purely to discover there is no source
    file -- and these rows exist, from drafts and failed uploads.
    """
    Reel.objects.create(user=author, caption='text only', media='', image='')

    run(commit=True)

    assert queued == []


def test_a_missing_thumbnail_is_a_gap(author, queued):
    reel = Reel.objects.create(
        user=author,
        media='reels/processed/t_720p.mp4',
        media_360='reels/processed/t_360p.mp4',
        media_480='reels/processed/t_480p.mp4',
        thumbnail='',
    )

    run(commit=True)

    assert queued == [reel.id]


def test_a_partial_rung_set_is_a_gap(author, queued):
    """360p present, 480p missing -- the reel still needs work."""
    reel = Reel.objects.create(
        user=author,
        media='reels/processed/p_720p.mp4',
        media_360='reels/processed/p_360p.mp4',
        thumbnail='thumbnails/p.jpg',
    )

    run(commit=True)

    assert queued == [reel.id]


# ---------------------------------------------------------------------------
# --only
# ---------------------------------------------------------------------------


def test_only_thumbnails_ignores_variant_gaps(author, queued):
    """Lets an operator run the cheap pass first: a thumbnail is one frame,
    while the rungs are a full re-encode."""
    needs_thumb = Reel.objects.create(user=author, media='reels/a.mp4', thumbnail='')
    Reel.objects.create(user=author, media='reels/b.mp4', thumbnail='thumbnails/b.jpg')

    run(commit=True, only='thumbnails')

    assert queued == [needs_thumb.id]


def test_only_images_ignores_videos(author, queued):
    picture = Reel.objects.create(user=author, image='reels/pic.jpg', thumbnail='thumbnails/p.jpg')
    Reel.objects.create(user=author, media='reels/vid.mp4', thumbnail='')

    run(commit=True, only='images')

    assert queued == [picture.id]


# ---------------------------------------------------------------------------
# Pacing and repetition
# ---------------------------------------------------------------------------


def test_limit_stops_where_it_says(author, queued):
    for i in range(10):
        Reel.objects.create(user=author, media=f'reels/{i}.mp4', thumbnail='')

    run(commit=True, limit=3, batch_size=2)

    assert len(queued) == 3


def test_every_reel_is_queued_exactly_once_across_batches(author, queued):
    """
    The pagination guard.

    Batches are walked by id, not by offset. An offset walk would be correct
    only if the matching set held still -- and it does not, because the whole
    point of the run is to change it. This fails on duplicates as well as on
    skips.
    """
    ids = {
        Reel.objects.create(user=author, media=f'reels/{i}.mp4', thumbnail='').id for i in range(12)
    }

    run(commit=True, batch_size=5)

    assert sorted(queued) == sorted(ids)
    assert len(queued) == len(set(queued)), 'a reel was queued twice'


def test_rerunning_after_completion_settles(author, queued):
    """
    Idempotence, as an operator experiences it.

    A backfill of thousands gets interrupted and re-run. Once the workers have
    filled the gaps, the next run must find nothing rather than start again.
    """
    reel = Reel.objects.create(user=author, media='reels/a.mp4', thumbnail='')

    run(commit=True)
    assert queued == [reel.id]

    # Stand in for the worker having finished.
    Reel.objects.filter(pk=reel.pk).update(
        thumbnail='thumbnails/a.jpg',
        media_360='reels/processed/a_360p.mp4',
        media_480='reels/processed/a_480p.mp4',
    )
    queued.clear()

    run(commit=True)

    assert queued == []
