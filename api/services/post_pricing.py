"""
What posting costs.

    image                        2 coins
    video, under 60 seconds      2 coins
    video, 60 seconds and over   100 coins in total

One module because the price is decided in two places and they must agree: the
upload request charges the base price before the post exists, and the worker
adds the long-video difference once it has actually measured the file
(api/tasks/media.py). Splitting the rule between them is how a boundary drifts
-- and the boundary is the part a person notices, because a 60.0-second video
costs fifty times what a 59.9-second one does.

**60 seconds is a long video.** The charge is ``>= 60``, not ``> 60``, which
is the opposite of what the surcharge did before this module existed. A video
of exactly 60.0 seconds used to cost 2 coins.

**The duration is never the client's.** The base price is charged on upload,
when the only thing known is image-or-video; the long-video difference is
charged by the worker from the duration ffprobe measured
(``api/tasks/media.py::_probe``). A request that claims ``duration=10`` for a
100-second video changes nothing, because nothing here reads a request field.

The amounts live in ``WalletConfig`` (admin-editable, per campaign/non-campaign
as every other cost in this system is) rather than as constants here, so a
price change is a form edit and not a deploy. What this module owns is the
*rule*: which band a post is in, and what the difference between the bands is.
"""

#: At and above this many seconds, a video is a long video. Inclusive: 60.0
#: seconds is charged as long, 59.9 is not.
LONG_VIDEO_SECONDS = 60

#: The band the product defines an upper edge for. Videos longer than this are
#: refused -- but by the existing duration rule
#: (``settings.MEDIA_MAX_VIDEO_SECONDS``), not by pricing, so that one limit
#: keeps deciding what may be uploaded. Recorded here only so the two numbers
#: can be compared; see ``pricing_band_exceeds_upload_limit``.
LONG_VIDEO_MAX_SECONDS = 120


def is_long_video(duration) -> bool:
    """Whether a measured duration falls in the long-video band.

    An unknown duration is not long: the worker charges the difference only
    once it has a real measurement, and guessing would charge a photo's price
    difference to a video nobody has measured yet -- or worse, the other way.
    """
    if duration is None:
        return False
    try:
        return float(duration) >= LONG_VIDEO_SECONDS
    except (TypeError, ValueError):
        return False


def base_cost(config, *, is_campaign_post: bool) -> int:
    """What every post costs on upload, before any duration is known."""
    field = 'cost_post_create' if is_campaign_post else 'cost_post_create_non_campaign'
    return max(0, int(getattr(config, field, 0) or 0))


def long_video_extra(config, *, is_campaign_post: bool) -> int:
    """What a long video costs *on top of* the base price.

    Additive because that is how it is charged: the base is taken during the
    upload request and this is taken by the worker afterwards. A subscriber
    who posts a 90-second video is charged twice, 2 then 98, and their wallet
    history says so.
    """
    field = (
        'cost_post_create_long_video'
        if is_campaign_post
        else 'cost_post_create_long_video_non_campaign'
    )
    return max(0, int(getattr(config, field, 0) or 0))


def total_cost(config, *, is_campaign_post: bool, duration=None, is_video: bool = False) -> int:
    """What a post costs in total, for showing a price before it is paid.

    Never used to charge -- the two halves are charged where they are known --
    but it is what the create screen shows and what the tests assert against,
    so "the price" has one definition rather than one per caller.
    """
    total = base_cost(config, is_campaign_post=is_campaign_post)
    if is_video and is_long_video(duration):
        total += long_video_extra(config, is_campaign_post=is_campaign_post)
    return total


def quote(config, *, is_campaign_post: bool = False) -> dict:
    """The price list a client shows before anything is uploaded.

    Shaped as the bands themselves rather than as raw config fields, because
    what a person needs to be told is "2 coins" or "100 coins", not which
    column of a settings table it came from.
    """
    base = base_cost(config, is_campaign_post=is_campaign_post)
    long_total = base + long_video_extra(config, is_campaign_post=is_campaign_post)
    return {
        'image': base,
        'video_short': base,
        'video_long': long_total,
        'long_video_seconds': LONG_VIDEO_SECONDS,
        'long_video_max_seconds': LONG_VIDEO_MAX_SECONDS,
    }


def pricing_band_exceeds_upload_limit(max_upload_seconds) -> bool:
    """Is the priced band wider than what may actually be uploaded?

    The product's price list runs to 120 seconds, while
    ``MEDIA_MAX_VIDEO_SECONDS`` decides what is accepted. When the limit is
    lower, the top of the band is unreachable: no video between the limit and
    120 seconds is ever created, so it is never charged either. That is not a
    bug to fix here -- the upload limit is deliberately the one rule that says
    what may be posted -- but it is worth being able to ask.
    """
    try:
        return int(max_upload_seconds) < LONG_VIDEO_MAX_SECONDS
    except (TypeError, ValueError):
        return False
