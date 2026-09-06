"""
Campaign engagement counts and leaderboard scoring.

    score = likes x LIKE_WEIGHT
          + comments x COMMENT_WEIGHT
          + shares x SHARE_WEIGHT
          + gifts x GIFT_WEIGHT

One definition, used by every caller
------------------------------------
The formula was written out by hand in at least two places -- the leaderboard
endpoint and the scoring engine -- and the two disagreed, because each also
decided for itself what counted as a like or a gift. This module is the single
place either question is answered.

What was wrong with the counting
--------------------------------
Both call sites carried ``total_shares = 0  # TODO: implement shares tracking``,
so the share weight multiplied zero and no share ever moved a score, whatever
the configuration said. ``Reel.shares`` had been incremented by the share
endpoint the whole time.

Comments were counted with a plain ``.count()`` over the relation, which
includes soft-deleted rows: deleting a comment left its points on the board.

Both also ran a query per user per metric inside a Python loop over
participants -- three counts each, so a campaign with 200 participants issued
600 queries to render one page. The aggregation below is one query per metric
for the whole campaign.

Weights
-------
Weights are per-campaign and per-campaign-type, stored on
CampaignScoringConfig; the constants here are the defaults that model declares
and the fallback when a campaign has no configuration yet. They are named
rather than inlined so the formula reads the same everywhere and a change lands
in one place.
"""

from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

#: Points per engagement. Defaults; a campaign's own configuration wins.
LIKE_WEIGHT = Decimal('1')
COMMENT_WEIGHT = Decimal('2')
SHARE_WEIGHT = Decimal('5')
GIFT_WEIGHT = Decimal('10')

DEFAULT_WEIGHTS = {
    'likes': LIKE_WEIGHT,
    'comments': COMMENT_WEIGHT,
    'shares': SHARE_WEIGHT,
    'gifts': GIFT_WEIGHT,
}

#: The canonical response keys. Named here so serializers, views and tests
#: cannot drift into `likes_count` / `comments_count` / `votes` variants again.
ENGAGEMENT_FIELDS = ('likes', 'comments', 'shares', 'gifts')


def resolve_weights(campaign=None):
    """The four weights for a campaign, falling back to the defaults.

    Reads the same CampaignScoringConfig the scoring engine uses rather than
    introducing a second source of configuration. A campaign with no config, or
    a config missing a key, falls back per-key -- so a partially configured
    campaign still scores on the documented formula instead of silently
    weighting something at zero, which is how shares came to be worth nothing.
    """
    if campaign is None:
        return dict(DEFAULT_WEIGHTS)

    try:
        from api.services.scoring.engine import CampaignScoringEngine

        engine = CampaignScoringEngine(campaign)
        config = engine.type_config or {}
        section = config.get('engagement') or {}
        if campaign.campaign_type == 'grand':
            # Grand campaigns keep their engagement weights under the
            # qualification phase; same keys, different home.
            section = config.get('phase1_qualification') or section
    except Exception:
        # Scoring configuration is a refinement, not a prerequisite. A campaign
        # whose config cannot be built must still produce a leaderboard, on the
        # documented default weights.
        return dict(DEFAULT_WEIGHTS)

    def pick(key, fallback):
        value = section.get(f'{key}_weight')
        if value is None:
            return fallback
        try:
            return Decimal(str(value))
        except (TypeError, ValueError, ArithmeticError):
            return fallback

    return {
        'likes': pick('likes', LIKE_WEIGHT),
        'comments': pick('comments', COMMENT_WEIGHT),
        'shares': pick('shares', SHARE_WEIGHT),
        'gifts': pick('gifts', GIFT_WEIGHT),
    }


def compute_score(counts, weights=None):
    """Apply the formula to a mapping of engagement counts.

    Accepts anything with the four keys, so a caller holding freshly updated
    counts can score them without another round trip to the database.
    """
    weights = weights or DEFAULT_WEIGHTS
    total = Decimal('0')
    for field in ENGAGEMENT_FIELDS:
        count = counts.get(field) or 0
        total += Decimal(str(count)) * Decimal(str(weights.get(field, 0)))
    return total


def reel_engagement(reel):
    """Live engagement counts for one post, straight from the database.

    Deliberately re-reads rather than trusting ``Reel.votes``, the denormalised
    column: it is maintained by several code paths and drifts. The counts a
    score is built from should come from the rows that represent the actual
    engagement.
    """
    from api.models import Comment, Vote
    from api.models.gift import GiftTransaction

    return {
        'likes': Vote.objects.filter(reel=reel).count(),
        # Soft-deleted comments are not engagement. Counting them let a user
        # comment, collect the points, delete the comment and keep them.
        'comments': Comment.objects.filter(reel=reel, is_deleted=False).count(),
        # The share counter on the post itself -- what the share endpoint has
        # always incremented, and what the leaderboard never read.
        'shares': max(0, reel.shares or 0),
        'gifts': GiftTransaction.objects.filter(reel=reel).count(),
    }


def reel_engagement_payload(reel, campaign=None):
    """The canonical engagement block returned by the engagement endpoints.

    Every engagement endpoint returns the same shape, so a client never has to
    know which action it just performed to read the result back.
    """
    counts = reel_engagement(reel)
    weights = resolve_weights(campaign)
    return {
        **counts,
        'leaderboard_score': float(compute_score(counts, weights)),
    }


def campaign_participant_totals(campaign, posts_queryset):
    """Per-participant engagement totals for a campaign, ranked.

    ``posts_queryset`` is a PostScore queryset already narrowed to the campaign
    and period the caller cares about; this adds the counting and the ordering.

    Returns a list of dicts, highest score first, each carrying the four counts,
    the score and the participant's rank.

    Aggregation rather than iteration
    ---------------------------------
    Everything here is computed by the database over the whole campaign at
    once. The previous implementation looped over participants in Python and
    issued three counts inside the loop.

    Counting likes and comments in a single annotate would multiply them
    together -- two joins against the same rows produce a cross product, so a
    post with 10 likes and 5 comments reports 50 of each. They are therefore
    aggregated separately and joined in Python, which is four queries in total
    regardless of how many participants a campaign has.
    """
    from api.models import Comment, Vote
    from api.models.gift import GiftTransaction

    reel_to_user = dict(posts_queryset.values_list('reel_id', 'user_id'))
    if not reel_to_user:
        return []

    reel_ids = list(reel_to_user)
    totals = {
        user_id: {
            'user_id': user_id,
            'likes': 0,
            'comments': 0,
            'shares': 0,
            'gifts': 0,
            'posts': 0,
        }
        for user_id in set(reel_to_user.values())
    }

    for user_id in reel_to_user.values():
        totals[user_id]['posts'] += 1

    def add(field, rows):
        for row in rows:
            owner = reel_to_user.get(row['reel_id'])
            if owner is not None:
                totals[owner][field] += row['n'] or 0

    add(
        'likes',
        Vote.objects.filter(reel_id__in=reel_ids).values('reel_id').annotate(n=Count('id')),
    )
    add(
        'comments',
        Comment.objects.filter(reel_id__in=reel_ids, is_deleted=False)
        .values('reel_id')
        .annotate(n=Count('id')),
    )
    add(
        'gifts',
        GiftTransaction.objects.filter(reel_id__in=reel_ids)
        .values('reel_id')
        .annotate(n=Count('id')),
    )

    # Shares live on the post as a counter rather than as rows, so they are
    # summed from the posts themselves.
    from api.models import Reel

    for row in (
        Reel.objects.filter(id__in=reel_ids).values('id').annotate(n=Coalesce(Sum('shares'), 0))
    ):
        owner = reel_to_user.get(row['id'])
        if owner is not None:
            totals[owner]['shares'] += max(0, row['n'] or 0)

    weights = resolve_weights(campaign)
    rows = []
    for entry in totals.values():
        entry['leaderboard_score'] = float(compute_score(entry, weights))
        rows.append(entry)

    return rank(rows)


def rank(rows):
    """Order participants and stamp a rank on each.

    Ranking is by score, then by the campaign's tie-break. There was none: the
    old endpoint sorted on score alone, over a queryset with no ordering, so
    two participants on equal points could swap places between two requests --
    and rank decides who gets rewarded.

    The tie-break is most engagement first (a participant who earned the same
    score from more actions placed higher), then lowest user id, which reaches
    the same answer every time and never depends on row order.
    """
    ordered = sorted(
        rows,
        key=lambda r: (
            -float(r.get('leaderboard_score') or 0),
            -sum(int(r.get(f) or 0) for f in ENGAGEMENT_FIELDS),
            int(r.get('user_id') or 0),
        ),
    )
    for position, entry in enumerate(ordered, start=1):
        entry['rank'] = position
    return ordered


def campaign_reels(campaign):
    """Approved campaign posts, as a Reel queryset.

    Only approved posts score. Anything pending or rejected is excluded, which
    is also what stops a non-campaign post from contributing: it has no
    PostScore row at all.
    """
    from api.models.campaign_extended import PostScore

    return PostScore.objects.filter(campaign=campaign, moderation_status='approved')


def campaign_for_reel(reel):
    """The campaign a post belongs to, or None for an ordinary post."""
    try:
        score = reel.campaign_score
    except Exception:
        return None
    return getattr(score, 'campaign', None) if score else None


__all__ = [
    'COMMENT_WEIGHT',
    'DEFAULT_WEIGHTS',
    'ENGAGEMENT_FIELDS',
    'GIFT_WEIGHT',
    'LIKE_WEIGHT',
    'SHARE_WEIGHT',
    'campaign_for_reel',
    'campaign_participant_totals',
    'campaign_reels',
    'compute_score',
    'rank',
    'reel_engagement',
    'reel_engagement_payload',
    'resolve_weights',
]
