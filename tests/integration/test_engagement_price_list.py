"""
What engagement costs and what it scores, as the requirement sets it.

    like     1 coin   ->  1 point
    comment  2 coins  ->  2 points
    share    5 coins  ->  5 points

The mechanics are covered elsewhere and not repeated here: the deduction
itself, the transaction boundaries, idempotent shares and the concurrent-click
race are in tests/integration/test_campaign_engagement_charges.py and
test_concurrency_engagement.py. Those deliberately set their own prices, so
that a change to the shipped defaults cannot make them pass for the wrong
reason -- which is exactly why none of them noticed that the shipped defaults
were **zero** and engagement had been free all along.

This file is the missing half: the prices themselves. It fails if a deploy
ships engagement for free again, and it fails if the coin price and the score
award stop agreeing with each other -- the requirement sets them to the same
figure, and a change to one without the other is almost certainly a mistake.
"""

import pytest

from api.models.campaign_extended import CampaignScoringConfig
from api.models.wallet import WalletConfig

pytestmark = pytest.mark.django_db

#: action -> (coins charged, points awarded)
PRICE_LIST = {
    'like': (1, 1),
    'comment': (2, 2),
    'share': (5, 5),
}


def field_default(model, name):
    """The shipped default, independent of any row in the database."""
    return model._meta.get_field(name).default


# ── the coin price ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(('action', 'coins'), [(a, v[0]) for a, v in PRICE_LIST.items()])
def test_each_campaign_action_costs_what_the_requirement_says(action, coins):
    assert field_default(WalletConfig, f'cost_{action}') == coins


@pytest.mark.parametrize(('action', 'coins'), [(a, v[0]) for a, v in PRICE_LIST.items()])
def test_the_same_price_applies_off_campaign(action, coins):
    """A like costs a coin wherever it happens.

    The two sets existed so a campaign could be priced differently from the
    ordinary feed; the requirement sets one price, so they match. Charging
    different amounts for the same act depending on which endpoint the client
    happened to call is the bug test_campaign_engagement_charges.py records
    for posts.
    """
    assert field_default(WalletConfig, f'cost_{action}_non_campaign') == coins


@pytest.mark.parametrize('action', list(PRICE_LIST))
def test_a_fresh_config_row_carries_the_price_list(action):
    """Not just the field default -- what a new environment actually gets."""
    config = WalletConfig.objects.create()
    try:
        assert getattr(config, f'cost_{action}') == PRICE_LIST[action][0]
    finally:
        config.delete()


def test_engagement_is_not_free():
    """The state this requirement was written to correct.

    Every one of these was 0, so the charging code ran, found nothing to
    charge and returned early. Nothing was broken and nothing was billed.
    """
    for action in PRICE_LIST:
        assert field_default(WalletConfig, f'cost_{action}') > 0, action
        assert field_default(WalletConfig, f'cost_{action}_non_campaign') > 0, action


# ── the score award ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('level', 'action', 'points'),
    [
        (level, action, value[1])
        for level in ('daily', 'weekly', 'monthly')
        for action, value in PRICE_LIST.items()
    ],
)
def test_each_action_scores_what_the_requirement_says(level, action, points):
    """Every campaign level awards the same, per the requirement."""
    field = f'{level}_{action}s_weight'
    assert float(field_default(CampaignScoringConfig, field)) == float(points)


@pytest.mark.parametrize('action', list(PRICE_LIST))
def test_what_an_action_costs_is_what_it_scores(action):
    """The requirement sets one figure for both.

    Coupled deliberately: a coin price raised without the score, or the other
    way round, changes the deal being offered and is far more likely to be an
    oversight than an intention.
    """
    coins = field_default(WalletConfig, f'cost_{action}')
    points = float(field_default(CampaignScoringConfig, f'daily_{action}s_weight'))

    assert float(coins) == points, f'{action} costs {coins} but scores {points}'


def test_the_legacy_weights_are_not_what_scoring_uses():
    """likes_weight/comments_weight/shares_weight are 0.6/1.5/2.0 and marked
    legacy on the model. Pinned so that nobody reads them as the live figures
    and 'corrects' the per-level weights to match."""
    assert float(field_default(CampaignScoringConfig, 'likes_weight')) == 0.6
    assert float(field_default(CampaignScoringConfig, 'comments_weight')) == 1.5
    assert float(field_default(CampaignScoringConfig, 'shares_weight')) == 2.0


# ── the price list reaches the charging service ─────────────────────────────


@pytest.mark.parametrize(('action', 'coins'), [(a, v[0]) for a, v in PRICE_LIST.items()])
def test_the_charging_service_reads_the_shipped_price(django_user_model, action, coins):
    """End of the chain: what engagement_cost answers for a real post."""
    from api.models import Reel
    from api.services.campaign_charges import engagement_cost

    WalletConfig.objects.all().delete()
    WalletConfig.objects.create()

    author = django_user_model.objects.create_user(username=f'price_{action}', password='x')
    reel = Reel.objects.create(user=author, caption='priced')
    try:
        assert engagement_cost(reel, action) == coins
    finally:
        reel.delete()
        author.delete()
