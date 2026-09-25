"""
Campaign Scoring Engine - Flexible scoring system for Daily, Weekly, Monthly, and Grand campaigns
"""

from contextlib import contextmanager
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from api.models import Comment, Vote
from api.models.campaign_extended import (
    CampaignScoringConfig,
    PostScore,
    SelectedWinner,
    UserCampaignStats,
    WinnerFrequencyRecord,
)
from api.models.gift import GiftTransaction
from api.services.campaign_eligibility import campaign_eligibility


class CampaignScoringEngine:
    """
    Flexible scoring engine that switches calculation logic based on campaign type.
    Supports Daily, Weekly, Monthly, and Grand campaign types.
    """

    def __init__(self, campaign):
        self.campaign = campaign
        self.config, _ = CampaignScoringConfig.objects.get_or_create(campaign=campaign)
        self.campaign_type = campaign.campaign_type
        self.type_config = self.config.get_config_for_type(self.campaign_type)

    # ========================================================================
    # WHO MAY WIN
    # ========================================================================
    #
    # Scoring high is not the same as qualifying. Three separate questions
    # have to be answered yes before an entry can take a prize, and until
    # this section existed only the third was asked:
    #
    #   1. did they take part? -- the 5-of-7 / 20-of-30 participation rule,
    #      computed in api/services/campaign_eligibility.py;
    #   2. are they allowed to win again yet? -- the rolling 30-day
    #      restriction and its cooldown, in WinnerFrequencyRecord; and
    #   3. have they already won this cycle? -- each selector's own check,
    #      which is all that used to be enforced.
    #
    # So a subscriber who posted once in a month could out-score everybody
    # and win Monthly Star, and a subscriber could win repeatedly because
    # nothing recorded their wins where the restriction would see them.

    def _documented_winner_count(self):
        """How many winners this tier pays: 20, 10, 5 or 1.

        From api/services/prize_structure.py rather than
        Campaign.winner_count, which defaults to 1 on every row -- so a
        Daily Sprint advertised as having twenty winners was selecting one.
        The figures are contractual, so the table is the authority and an
        explicit count passed by a caller still overrides it.
        """
        from api.services.prize_structure import PRIZES

        prize = PRIZES.get(self.campaign_type)
        if prize is None:
            return self.campaign.winner_count
        return prize.winner_count

    def _qualifies(self, user, winner_type):
        """Whether `user` may take a prize in this campaign at all."""
        if not campaign_eligibility(user, self.campaign).eligible:
            return False

        allowed, _wins, _limit = WinnerFrequencyRecord.check_frequency_eligibility(
            user, winner_type, self.campaign
        )
        return allowed

    def _record_win(self, user, winner_type):
        """Write the win where the frequency restriction will see it.

        Without this the restriction reads an empty table and lets everybody
        through -- which is why it never bit: only the CRM gift flow in
        api/views/crm.py recorded anything, so wins awarded here were
        invisible to it. record_win is idempotent per period, so re-running a
        selection does not stack up records.
        """
        WinnerFrequencyRecord.record_win(user=user, winner_type=winner_type, campaign=self.campaign)

    @contextmanager
    def _selection_lock(self):
        """Serialise winner selection for this campaign.

        Every selector reads who has already won, decides, then writes that
        decision. Two runs overlapping -- the Celery beat task and an admin
        pressing the button, a retried task -- both read "nobody has won yet"
        and both award, so the prize goes out twice and the frequency
        restriction is bypassed by the pair of them.

        The campaign row is the lock because it is the one row every
        selection for this campaign has in common. See strategy 2 in
        api/services/concurrency.py: the lock is taken before the reads that
        the decision depends on, not after them.
        """
        from api.models.campaign import Campaign
        from api.services.concurrency import locked

        with transaction.atomic():
            locked(Campaign, self.campaign.pk)
            yield

    # ========================================================================
    # DAILY CAMPAIGN SCORING
    # ========================================================================

    def calculate_daily_score(self, user, date=None):
        """
        Calculate daily score for a user.
        Includes: engagement (likes, comments, shares), gamification (spins, gifts, login),
        and daily consistency (posted today).
        """
        if date is None:
            date = timezone.now().date()

        config = self.type_config
        score = 0.0
        breakdown = {'engagement': 0, 'gamification': 0, 'consistency': 0, 'details': {}}

        # Get user's posts for this day
        day_start = timezone.make_aware(datetime.combine(date, datetime.min.time()))
        day_end = day_start + timedelta(days=1)

        user_posts = PostScore.objects.filter(
            user=user,
            campaign=self.campaign,
            created_at__range=(day_start, day_end),
            moderation_status='approved',
        ).select_related('reel')

        # 1. ENGAGEMENT SCORING
        total_likes = 0
        total_comments = 0
        total_shares = 0
        total_gifters = 0  # Number of unique users who gifted on the user's posts

        for post in user_posts:
            likes = Vote.objects.filter(reel=post.reel).count()
            # Soft-deleted comments are not engagement; counting them let a
            # user comment, collect the points and then delete the comment.
            comments = Comment.objects.filter(reel=post.reel, is_deleted=False).count()
            # Was hardcoded to 0 behind a TODO in all four scoring paths, so
            # shares_weight multiplied nothing and no share ever scored.
            # Reel.shares is what the share endpoint has always incremented.
            shares = max(0, post.reel.shares or 0)
            gifters = (
                GiftTransaction.objects.filter(reel=post.reel).values('sender').distinct().count()
            )

            total_likes += likes
            total_comments += comments
            total_shares += shares
            total_gifters += gifters

        engagement_score = (
            total_likes * config['engagement']['likes_weight']
            + total_comments * config['engagement']['comments_weight']
            + total_shares * config['engagement']['shares_weight']
            + total_gifters * config['engagement'].get('gifts_weight', 0)
        )
        score += engagement_score
        breakdown['engagement'] = engagement_score
        breakdown['details']['likes'] = total_likes
        breakdown['details']['comments'] = total_comments
        breakdown['details']['shares'] = total_shares
        breakdown['details']['gifters'] = total_gifters

        # 2. GAMIFICATION SCORING
        # Get user's gamification data for the day
        gamification = self._get_daily_gamification(user, date)

        gamification_score = (
            gamification['spin_rewards'] * config['gamification']['spin_reward']
            + gamification['coin_gifts_received'] * config['gamification']['coin_gift']
            + gamification['login_bonus'] * config['gamification']['login_bonus']
        )
        score += gamification_score
        breakdown['gamification'] = gamification_score
        breakdown['details']['spin_rewards'] = gamification['spin_rewards']
        breakdown['details']['coin_gifts'] = gamification['coin_gifts_received']
        breakdown['details']['login_bonus'] = gamification['login_bonus']

        # 3. DAILY CONSISTENCY (posted today)
        posted_today = user_posts.exists()
        if posted_today:
            consistency_score = config['consistency']['daily_post_points']
            score += consistency_score
            breakdown['consistency'] = consistency_score
            breakdown['details']['posted_today'] = True
        else:
            breakdown['details']['posted_today'] = False

        return {'total_score': score, 'breakdown': breakdown, 'date': date.isoformat()}

    def select_daily_winners(self, entries, total_winners=None):
        """
        Select winners based on top scorers only.
        Enforces 7-day win limit.
        Awards points to winners.
        """
        if total_winners is None:
            total_winners = self._documented_winner_count()

        config = self.type_config

        with self._selection_lock():
            # Filter out users who won in the last 7 days
            cooldown_days = config['win_cooldown_days']
            cutoff_date = timezone.now() - timedelta(days=cooldown_days)

            eligible_entries = []
            for entry in entries:
                user = entry.user
                # Check if user won recently in this campaign
                recent_win = SelectedWinner.objects.filter(
                    selection__campaign=self.campaign, user=user, created_at__gte=cutoff_date
                ).exists()

                if recent_win:
                    continue

                # Posting on the competition day is what earns the entry a
                # place here, and the 30-day restriction decides whether they
                # may take another prize yet.
                if not self._qualifies(user, 'daily'):
                    continue

                eligible_entries.append(entry)

            # Sort by score
            eligible_entries.sort(key=lambda x: x.score, reverse=True)

            winners = []

            # Get point reward from wallet config
            from api.models.wallet import WalletConfig

            wallet_config = WalletConfig.get_config()
            point_reward = wallet_config.daily_winner_points

            # Select top scorers and award points
            for idx, entry in enumerate(eligible_entries[:total_winners], start=1):
                # Award points to winner
                user_profile = entry.user.profile
                # Row-locked via add_points -- see UserProfile._apply_delta's
                # docstring: without this, two point-award paths landing on the
                # same user in the same moment (e.g. this batch overlapping a
                # gift arriving) would lose one of the credits.
                user_profile.add_points(point_reward, reason='campaign_reward')
                self._record_win(entry.user, 'daily')

                winners.append(
                    {
                        'rank': idx,
                        'user': entry.user,
                        'score': entry.score,
                        'method': 'top_scorer',
                        'points_awarded': point_reward,
                    }
                )

            return winners

    # ========================================================================
    # WEEKLY CAMPAIGN SCORING
    # ========================================================================

    def calculate_weekly_score(self, user, week_start=None):
        """
        Calculate cumulative weekly score with streak bonuses and decay.
        """
        if week_start is None:
            # Default to current week (Monday)
            today = timezone.now().date()
            week_start = today - timedelta(days=today.weekday())

        week_end = week_start + timedelta(days=7)
        config = self.type_config

        score = 0.0
        breakdown = {
            'engagement': 0,
            'gamification': 0,
            'streak_bonuses': 0,
            'decay': 0,
            'details': {},
        }

        # Get all posts for the week
        week_start_dt = timezone.make_aware(datetime.combine(week_start, datetime.min.time()))
        week_end_dt = timezone.make_aware(datetime.combine(week_end, datetime.min.time()))

        user_posts = PostScore.objects.filter(
            user=user,
            campaign=self.campaign,
            created_at__range=(week_start_dt, week_end_dt),
            moderation_status='approved',
        ).select_related('reel')

        # 1. ENGAGEMENT (cumulative across week)
        total_likes = 0
        total_comments = 0
        total_shares = 0
        total_gifters = 0

        for post in user_posts:
            likes = Vote.objects.filter(reel=post.reel).count()
            # Soft-deleted comments are not engagement; counting them let a
            # user comment, collect the points and then delete the comment.
            comments = Comment.objects.filter(reel=post.reel, is_deleted=False).count()
            # Was hardcoded to 0 behind a TODO in all four scoring paths, so
            # shares_weight multiplied nothing and no share ever scored.
            # Reel.shares is what the share endpoint has always incremented.
            shares = max(0, post.reel.shares or 0)

            total_likes += likes
            total_comments += comments
            total_shares += shares
            total_gifters += (
                GiftTransaction.objects.filter(reel=post.reel).values('sender').distinct().count()
            )

        engagement_score = (
            total_likes * config['engagement']['likes_weight']
            + total_comments * config['engagement']['comments_weight']
            + total_shares * config['engagement']['shares_weight']
            + total_gifters * config['engagement'].get('gifts_weight', 0)
        )
        score += engagement_score
        breakdown['engagement'] = engagement_score

        # 2. GAMIFICATION (cumulative)
        # Aggregate gamification across the week
        gamification_score = 0
        days_participated = 0

        for day_offset in range(7):
            day = week_start + timedelta(days=day_offset)
            daily_gamification = self._get_daily_gamification(user, day)

            day_score = (
                daily_gamification['spin_rewards'] * config['gamification']['spin_reward']
                + daily_gamification['coin_gifts_received'] * config['gamification']['coin_gift']
            )
            gamification_score += day_score

            if daily_gamification['posted_today']:
                days_participated += 1

        # Consistency boost per day participated
        consistency_score = days_participated * config['gamification']['consistency_boost']
        gamification_score += consistency_score

        score += gamification_score
        breakdown['gamification'] = gamification_score
        breakdown['details']['days_participated'] = days_participated

        # 3. STREAK BONUSES
        streak_bonus = 0
        if days_participated >= 7:
            streak_bonus = config['streak_bonuses']['7_day']
        elif days_participated >= 5:
            streak_bonus = config['streak_bonuses']['5_day']
        elif days_participated >= 3:
            streak_bonus = config['streak_bonuses']['3_day']

        score += streak_bonus
        breakdown['streak_bonuses'] = streak_bonus
        breakdown['details']['streak_days'] = days_participated

        # 4. DECAY (penalty for missed days)
        missed_days = 7 - days_participated
        max_decay_days = config['decay']['max_days']
        decay_days = min(missed_days, max_decay_days)
        decay_penalty = decay_days * config['decay']['per_missed_day']

        score -= decay_penalty
        breakdown['decay'] = -decay_penalty
        breakdown['details']['missed_days'] = missed_days
        breakdown['details']['decay_applied'] = decay_penalty

        return {
            'total_score': max(0, score),
            'breakdown': breakdown,
            'week_start': week_start.isoformat(),
            'week_end': week_end.isoformat(),
        }

    def select_weekly_winners(self, entries, winner_count=None):
        """
        Select top scorers as winners.
        Enforces one win per weekly cycle.
        Awards points to winners.
        """
        if winner_count is None:
            winner_count = self._documented_winner_count()

        with self._selection_lock():
            # Filter out users who already won this cycle
            eligible_entries = []
            for entry in entries:
                user = entry.user
                stat = UserCampaignStats.objects.filter(user=user, campaign=self.campaign).first()

                if stat and stat.has_won_current_cycle:
                    continue

                # Weekly Battle asks for posts on 5 of the 7 days. Scoring
                # high across two of them is not qualification.
                if not self._qualifies(user, 'weekly'):
                    continue

                eligible_entries.append(entry)

            # Sort by score (highest first)
            eligible_entries.sort(key=lambda x: x.score, reverse=True)

            # Get point reward from wallet config
            from api.models.wallet import WalletConfig

            wallet_config = WalletConfig.get_config()
            point_reward = wallet_config.weekly_winner_points

            winners = []
            for idx, entry in enumerate(eligible_entries[:winner_count], start=1):
                # Award points to winner
                user_profile = entry.user.profile
                # Row-locked via add_points -- see UserProfile._apply_delta's
                # docstring: without this, two point-award paths landing on the
                # same user in the same moment (e.g. this batch overlapping a
                # gift arriving) would lose one of the credits.
                user_profile.add_points(point_reward, reason='campaign_reward')
                self._record_win(entry.user, 'weekly')

                winners.append(
                    {
                        'rank': idx,
                        'user': entry.user,
                        'score': entry.score,
                        'method': 'top_scorer',
                        'points_awarded': point_reward,
                    }
                )

                # Mark user as having won this cycle
                stat, _ = UserCampaignStats.objects.get_or_create(
                    user=entry.user, campaign=self.campaign
                )
                stat.has_won_current_cycle = True
                stat.last_win_date = timezone.now()
                stat.save()

            return winners

    # ========================================================================
    # MONTHLY CAMPAIGN SCORING
    # ========================================================================

    def calculate_monthly_score(self, user, month_date=None):
        """
        Calculate cumulative monthly score with deep weighting.
        Includes: engagement, gamification, weekly winner bonuses, streak multipliers.
        """
        if month_date is None:
            month_date = timezone.now().date()

        # Get month range
        month_start = month_date.replace(day=1)
        if month_date.month == 12:
            next_month = month_date.replace(year=month_date.year + 1, month=1, day=1)
        else:
            next_month = month_date.replace(month=month_date.month + 1, day=1)
        month_end = next_month - timedelta(days=1)

        config = self.type_config
        score = 0.0
        breakdown = {
            'engagement': 0,
            'gamification': 0,
            'weekly_winner_bonus': 0,
            'streak_multipliers': 0,
            'high_engagement_bonus': 0,
            'details': {},
        }

        # Get all posts for the month
        month_start_dt = timezone.make_aware(datetime.combine(month_start, datetime.min.time()))
        month_end_dt = timezone.make_aware(datetime.combine(month_end, datetime.max.time()))

        user_posts = PostScore.objects.filter(
            user=user,
            campaign=self.campaign,
            created_at__range=(month_start_dt, month_end_dt),
            moderation_status='approved',
        ).select_related('reel')

        # 1. ENGAGEMENT (with potential high engagement bonuses)
        total_likes = 0
        total_comments = 0
        total_shares = 0
        total_gifters = 0
        high_engagement_posts = 0

        for post in user_posts:
            likes = Vote.objects.filter(reel=post.reel).count()
            # Soft-deleted comments are not engagement; counting them let a
            # user comment, collect the points and then delete the comment.
            comments = Comment.objects.filter(reel=post.reel, is_deleted=False).count()
            # Was hardcoded to 0 behind a TODO in all four scoring paths, so
            # shares_weight multiplied nothing and no share ever scored.
            # Reel.shares is what the share endpoint has always incremented.
            shares = max(0, post.reel.shares or 0)

            total_likes += likes
            total_comments += comments
            total_shares += shares
            total_gifters += (
                GiftTransaction.objects.filter(reel=post.reel).values('sender').distinct().count()
            )

            # Check for high engagement bonus
            if likes >= config['high_engagement']['threshold']:
                high_engagement_posts += 1

        engagement_score = (
            total_likes * config['engagement']['likes_weight']
            + total_comments * config['engagement']['comments_weight']
            + total_shares * config['engagement']['shares_weight']
            + total_gifters * config['engagement'].get('gifts_weight', 0)
        )
        score += engagement_score
        breakdown['engagement'] = engagement_score

        # High engagement bonus
        he_bonus = high_engagement_posts * config['high_engagement']['bonus']
        score += he_bonus
        breakdown['high_engagement_bonus'] = he_bonus
        breakdown['details']['high_engagement_posts'] = high_engagement_posts

        # 2. GAMIFICATION with consistency multiplier
        # Track days with activity
        active_days = set()
        for post in user_posts:
            active_days.add(post.created_at.date())

        days_count = len(active_days)

        # Apply consistency multiplier to base gamification
        gamification_score = 0
        for day in active_days:
            daily_gamification = self._get_daily_gamification(user, day)
            day_score = (
                daily_gamification['spin_rewards'] * config['gamification']['spin_reward']
                + daily_gamification['coin_gifts_received'] * config['gamification']['coin_gift']
            )
            gamification_score += day_score

        # Apply consistency multiplier
        if days_count >= 7:
            gamification_score *= config['gamification']['consistency_multiplier']

        score += gamification_score
        breakdown['gamification'] = gamification_score
        breakdown['details']['active_days'] = days_count

        # 3. STREAK MULTIPLIERS
        # Calculate longest streak in the month
        longest_streak = self._calculate_longest_streak(user, month_start, month_end)

        streak_multiplier = 1.0
        if longest_streak >= 21:
            streak_multiplier = config['streak_multipliers']['21_day']
        elif longest_streak >= 14:
            streak_multiplier = config['streak_multipliers']['14_day']
        elif longest_streak >= 7:
            streak_multiplier = config['streak_multipliers']['7_day']

        streak_bonus = score * (streak_multiplier - 1.0)  # Bonus is the extra portion
        score *= streak_multiplier
        breakdown['streak_multipliers'] = streak_bonus
        breakdown['details']['longest_streak'] = longest_streak
        breakdown['details']['streak_multiplier_applied'] = streak_multiplier

        # 4. WEEKLY WINNER BONUS
        # Check if user won any weekly campaigns this month
        weekly_wins = SelectedWinner.objects.filter(
            user=user,
            selection__campaign__campaign_type='weekly',
            created_at__range=(month_start_dt, month_end_dt),
        ).count()

        weekly_bonus = weekly_wins * config['weekly_winner_bonus']
        score += weekly_bonus
        breakdown['weekly_winner_bonus'] = weekly_bonus
        breakdown['details']['weekly_wins_this_month'] = weekly_wins

        return {'total_score': score, 'breakdown': breakdown, 'month': month_date.strftime('%Y-%m')}

    def select_monthly_winners(self, entries, winner_count=None):
        """
        Select top scorers as winners.
        Enforces one win per monthly cycle.
        Awards points to winners.
        """
        if winner_count is None:
            winner_count = self._documented_winner_count()

        with self._selection_lock():
            # Filter out users who already won this cycle
            eligible_entries = []
            for entry in entries:
                user = entry.user
                stat = UserCampaignStats.objects.filter(user=user, campaign=self.campaign).first()

                if stat and stat.has_won_current_cycle:
                    continue

                # Monthly Star asks for posts on 20 of the 30 days.
                if not self._qualifies(user, 'monthly'):
                    continue

                eligible_entries.append(entry)

            # Sort by score
            eligible_entries.sort(key=lambda x: x.score, reverse=True)

            # Get point reward from wallet config
            from api.models.wallet import WalletConfig

            wallet_config = WalletConfig.get_config()
            point_reward = wallet_config.monthly_winner_points

            winners = []
            for idx, entry in enumerate(eligible_entries[:winner_count], start=1):
                # Award points to winner
                user_profile = entry.user.profile
                # Row-locked via add_points -- see UserProfile._apply_delta's
                # docstring: without this, two point-award paths landing on the
                # same user in the same moment (e.g. this batch overlapping a
                # gift arriving) would lose one of the credits.
                user_profile.add_points(point_reward, reason='campaign_reward')
                self._record_win(entry.user, 'monthly')

                winners.append(
                    {
                        'rank': idx,
                        'user': entry.user,
                        'score': entry.score,
                        'method': 'top_scorer',
                        'points_awarded': point_reward,
                    }
                )

                # Mark user as having won this cycle
                stat, _ = UserCampaignStats.objects.get_or_create(
                    user=entry.user, campaign=self.campaign
                )
                stat.has_won_current_cycle = True
                stat.last_win_date = timezone.now()
                stat.save()

            return winners

    # ========================================================================
    # GRAND CAMPAIGN SCORING (Two-Phase)
    # ========================================================================

    def calculate_grand_qualification_score(self, user):
        """
        Phase 1: Performance qualification (similar to monthly).
        Top performers qualify for finals.
        """
        config = self.type_config['phase1_qualification']
        score = 0.0

        # Get all posts during qualification period
        if self.campaign.start_date and self.campaign.voting_start:
            qual_start = self.campaign.start_date
            qual_end = self.campaign.voting_start
        else:
            # Default to all campaign posts
            qual_start = self.campaign.start_date or timezone.now() - timedelta(days=30)
            qual_end = timezone.now()

        user_posts = PostScore.objects.filter(
            user=user,
            campaign=self.campaign,
            created_at__range=(qual_start, qual_end),
            moderation_status='approved',
        ).select_related('reel')

        # Calculate qualification score (similar to monthly)
        total_likes = 0
        total_comments = 0
        total_shares = 0
        total_gifters = 0

        for post in user_posts:
            likes = Vote.objects.filter(reel=post.reel).count()
            # Soft-deleted comments are not engagement; counting them let a
            # user comment, collect the points and then delete the comment.
            comments = Comment.objects.filter(reel=post.reel, is_deleted=False).count()
            # Was hardcoded to 0 behind a TODO in all four scoring paths, so
            # shares_weight multiplied nothing and no share ever scored.
            # Reel.shares is what the share endpoint has always incremented.
            shares = max(0, post.reel.shares or 0)
            gifters = (
                GiftTransaction.objects.filter(reel=post.reel).values('sender').distinct().count()
            )

            total_likes += likes
            total_comments += comments
            total_shares += shares
            total_gifters += gifters

        score = (
            total_likes * config['likes_weight']
            + total_comments * config['comments_weight']
            + total_shares * config['shares_weight']
            + total_gifters * config.get('gifts_weight', 0)
        )

        return {
            'total_score': score,
            'details': {
                'likes': total_likes,
                'comments': total_comments,
                'shares': total_shares,
                'gifters': total_gifters,
                'posts_count': user_posts.count(),
            },
        }

    def calculate_grand_final_score(self, user, judge_scores, vote_count):
        """
        Phase 2: Final scoring with judging and voting.
        Final Score = (Judge Score * judging_weight) + (Vote Score * voting_weight)
        """
        config = self.type_config['phase2_judging']

        # Calculate judge score (out of 100 max)
        judge_criteria = config['judge_criteria']
        max_judge_score = (
            judge_criteria['creativity_max']
            + judge_criteria['quality_max']
            + judge_criteria['theme_max']
            + judge_criteria['impact_max']
        )

        # Sum up judge scores
        total_judge_score = sum(
            [
                judge_scores.get('creativity', 0),
                judge_scores.get('quality', 0),
                judge_scores.get('theme', 0),
                judge_scores.get('impact', 0),
            ]
        )

        # Normalize judge score to percentage
        judge_normalized = (total_judge_score / max_judge_score) * 100 if max_judge_score > 0 else 0

        # NOTE: config['voting']['vote_value'] is configured but does not reach
        # the final score. The normalisation below is a pure function of
        # vote_count, so raising or lowering vote_value changes nothing. Left as
        # found -- wiring it in would silently reweight every grand campaign --
        # but the setting is currently inert and should either be applied or
        # removed deliberately.

        # Normalize vote score (assuming max votes is 1000 for normalization)
        max_expected_votes = 1000
        vote_normalized = min(100, (vote_count / max_expected_votes) * 100)

        # Weighted combination
        judging_weight = config['judging_weight']
        voting_weight = config['voting_weight']

        final_score = (judge_normalized * judging_weight) + (vote_normalized * voting_weight)

        return {
            'total_score': final_score,
            'breakdown': {
                'judge_score': judge_normalized,
                'judge_weight': judging_weight,
                'judge_contribution': judge_normalized * judging_weight,
                'vote_score': vote_normalized,
                'vote_weight': voting_weight,
                'vote_contribution': vote_normalized * voting_weight,
                'raw_votes': vote_count,
                'raw_judge_total': total_judge_score,
            },
        }

    def select_grand_finalists(self, entries):
        """
        Select top X% of users to qualify for finals based on qualification score.
        Awards points to finalists.
        """
        config = self.type_config['phase1_qualification']
        qualification_pct = config['qualification_percentage'] / 100.0

        total_entries = len(entries)
        finalists_count = max(1, int(total_entries * qualification_pct))

        # Sort by qualification score
        sorted_entries = sorted(entries, key=lambda x: x.score, reverse=True)
        finalists = sorted_entries[:finalists_count]

        # Get point reward from wallet config
        from api.models.wallet import WalletConfig

        wallet_config = WalletConfig.get_config()
        point_reward = wallet_config.grand_finalist_points

        # Award points to finalists
        for entry in finalists:
            user_profile = entry.user.profile
            # Row-locked via add_points -- see UserProfile._apply_delta's
            # docstring: without this, two point-award paths landing on the
            # same user in the same moment (e.g. this batch overlapping a
            # gift arriving) would lose one of the credits.
            user_profile.add_points(point_reward, reason='campaign_reward')

        return [
            {
                'rank': idx + 1,
                'user': entry.user,
                'qualification_score': entry.score,
                'points_awarded': point_reward,
            }
            for idx, entry in enumerate(finalists)
        ]

    def select_grand_winners(self, entries, winner_count=None):
        """
        Select winners based on final scores (Phase 2).
        Awards points to winners.
        """
        if winner_count is None:
            winner_count = self._documented_winner_count()

        with self._selection_lock():
            # Grand Final asks for Monthly Star in 4 of the 6 campaign months.
            # The finalists were chosen on score in phase 1; this is where
            # the season-long requirement is actually checked.
            qualified = [entry for entry in entries if self._qualifies(entry.user, 'grand')]

            # Sort by final score
            sorted_entries = sorted(qualified, key=lambda x: x.score, reverse=True)

            # Get point reward from wallet config
            from api.models.wallet import WalletConfig

            wallet_config = WalletConfig.get_config()
            point_reward = wallet_config.grand_winner_points

            winners = []
            for idx, entry in enumerate(sorted_entries[:winner_count], start=1):
                # Award points to winner
                user_profile = entry.user.profile
                # Row-locked via add_points -- see UserProfile._apply_delta's
                # docstring: without this, two point-award paths landing on the
                # same user in the same moment (e.g. this batch overlapping a
                # gift arriving) would lose one of the credits.
                user_profile.add_points(point_reward, reason='campaign_reward')
                self._record_win(entry.user, 'grand')

                winners.append(
                    {
                        'rank': idx,
                        'user': entry.user,
                        'final_score': entry.score,
                        'method': 'final_score',
                        'points_awarded': point_reward,
                    }
                )

            return winners

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    def _get_daily_gamification(self, user, date):
        """
        Get gamification data for a user on a specific date.
        Returns dict with spin_rewards, coin_gifts_received, login_bonus, posted_today.
        """
        # This would query GamificationActivity model
        # For now, return zeros - implement when gamification tracking is added
        return {
            'spin_rewards': 0,
            'coin_gifts_received': 0,
            'login_bonus': 0,
            'posted_today': False,
        }

    def _calculate_longest_streak(self, user, start_date, end_date):
        """Calculate longest consecutive posting streak within date range."""
        posts = PostScore.objects.filter(
            user=user,
            campaign=self.campaign,
            created_at__date__range=(start_date, end_date),
            moderation_status='approved',
        ).dates('created_at', 'day')

        post_dates = sorted(set(posts))

        if not post_dates:
            return 0

        longest = 1
        current = 1

        for i in range(1, len(post_dates)):
            if (post_dates[i] - post_dates[i - 1]).days == 1:
                current += 1
                longest = max(longest, current)
            else:
                current = 1

        return longest

    # ========================================================================
    # MAIN INTERFACE METHODS
    # ========================================================================

    def calculate_user_score(self, user, **kwargs):
        """
        Main entry point to calculate score based on campaign type.
        Returns appropriate score calculation for the campaign type.
        """
        if self.campaign_type == 'daily':
            return self.calculate_daily_score(user, kwargs.get('date'))
        elif self.campaign_type == 'weekly':
            return self.calculate_weekly_score(user, kwargs.get('week_start'))
        elif self.campaign_type == 'monthly':
            return self.calculate_monthly_score(user, kwargs.get('month_date'))
        elif self.campaign_type == 'grand':
            phase = kwargs.get('phase', 'qualification')
            if phase == 'qualification':
                return self.calculate_grand_qualification_score(user)
            else:
                return self.calculate_grand_final_score(
                    user, kwargs.get('judge_scores', {}), kwargs.get('vote_count', 0)
                )
        else:
            raise ValueError(f'Unknown campaign type: {self.campaign_type}')

    def select_winners(self, entries, **kwargs):
        """
        Main entry point to select winners based on campaign type.
        """
        if self.campaign_type == 'daily':
            return self.select_daily_winners(entries, kwargs.get('total_winners'))
        elif self.campaign_type == 'weekly':
            return self.select_weekly_winners(entries, kwargs.get('winner_count'))
        elif self.campaign_type == 'monthly':
            return self.select_monthly_winners(entries, kwargs.get('winner_count'))
        elif self.campaign_type == 'grand':
            phase = kwargs.get('phase', 'finals')
            if phase == 'qualification':
                return self.select_grand_finalists(entries)
            else:
                return self.select_grand_winners(entries, kwargs.get('winner_count'))
        else:
            raise ValueError(f'Unknown campaign type: {self.campaign_type}')
