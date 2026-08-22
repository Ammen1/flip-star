"""Campaign scoring.

``engine`` selects a calculation strategy from ``Campaign.campaign_type``
(daily / weekly / monthly / grand) and computes scores, leaderboards and
winner selection from the admin-tunable ``CampaignScoringConfig``.
"""

from api.services.scoring.engine import CampaignScoringEngine

__all__ = ['CampaignScoringEngine']
