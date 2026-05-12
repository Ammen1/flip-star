"""
Campaign Scoring Engine - Flexible scoring system for Daily, Weekly, Monthly, and Grand campaigns
"""
from datetime import datetime, timedelta
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
import random

from .models import User, Reel, Vote, Comment
from .models_campaign import Campaign, CampaignEntry
from .models_gift import GiftTransaction
from .models_campaign_extended import (
    CampaignScoringConfig, UserCampaignStats, PostScore,
    Leaderboard, LeaderboardEntry, WinnerSelection, SelectedWinner
)


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
        breakdown = {
            'engagement': 0,
            'gamification': 0,
            'consistency': 0,
            'details': {}
        }
        
        # Get user's posts for this day
        day_start = timezone.make_aware(datetime.combine(date, datetime.min.time()))
        day_end = day_start + timedelta(days=1)
        
        user_posts = PostScore.objects.filter(
            user=user,
            campaign=self.campaign,
            created_at__range=(day_start, day_end),
            moderation_status='approved'
        ).select_related('reel')
        
        # 1. ENGAGEMENT SCORING
        total_likes = 0
        total_comments = 0
        total_shares = 0
        total_gifters = 0  # Number of unique users who gifted on the user's posts
        
        for post in user_posts:
            likes = Vote.objects.filter(reel=post.reel).count()
            comments = Comment.objects.filter(reel=post.reel).count()
            # TODO: shares tracking
            shares = 0
            gifters = GiftTransaction.objects.filter(reel=post.reel).values('sender').distinct().count()
            
            total_likes += likes
            total_comments += comments
            total_shares += shares
            total_gifters += gifters
        
        engagement_score = (
            total_likes * config['engagement']['likes_weight'] +
            total_comments * config['engagement']['comments_weight'] +
            total_shares * config['engagement']['shares_weight'] +
            total_gifters * config['engagement'].get('gifts_weight', 0)
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
            gamification['spin_rewards'] * config['gamification']['spin_reward'] +
            gamification['coin_gifts_received'] * config['gamification']['coin_gift'] +
            gamification['login_bonus'] * config['gamification']['login_bonus']
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
        
        return {
            'total_score': score,
            'breakdown': breakdown,
            'date': date.isoformat()
        }
    
    def select_daily_winners(self, entries, total_winners=None):
        """
        Select winners based on top scorers only.
        Enforces 7-day win limit.
        Awards points to winners.
        """
        if total_winners is None:
            total_winners = self.campaign.winner_count
        
        config = self.type_config
        
        # Filter out users who won in the last 7 days
        cooldown_days = config['win_cooldown_days']
        cutoff_date = timezone.now() - timedelta(days=cooldown_days)
        
        eligible_entries = []
        for entry in entries:
            user = entry.user
            # Check if user won recently in this campaign
            recent_win = SelectedWinner.objects.filter(
                selection__campaign=self.campaign,
                user=user,
                created_at__gte=cutoff_date
            ).exists()
            
            if not recent_win:
                eligible_entries.append(entry)
        
        # Sort by score
        eligible_entries.sort(key=lambda x: x.score, reverse=True)
        
        winners = []
        
        # Get point reward from wallet config
        from .models_wallet import WalletConfig
        wallet_config = WalletConfig.get_config()
        point_reward = wallet_config.daily_winner_points
        
        # Select top scorers and award points
        for idx, entry in enumerate(eligible_entries[:total_winners], start=1):
            # Award points to winner
            user_profile = entry.user.profile
            user_profile.points += point_reward
            user_profile.points_earned_total += point_reward
            user_profile.save()
            
            winners.append({
                'rank': idx,
                'user': entry.user,
                'score': entry.score,
                'method': 'top_scorer',
                'points_awarded': point_reward
            })
        
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
            'details': {}
        }
        
        # Get all posts for the week
        week_start_dt = timezone.make_aware(datetime.combine(week_start, datetime.min.time()))
        week_end_dt = timezone.make_aware(datetime.combine(week_end, datetime.min.time()))
        
        user_posts = PostScore.objects.filter(
            user=user,
            campaign=self.campaign,
            created_at__range=(week_start_dt, week_end_dt),
            moderation_status='approved'
        ).select_related('reel')
        
        # 1. ENGAGEMENT (cumulative across week)
        total_likes = 0
        total_comments = 0
        total_shares = 0
        total_gifters = 0
        
        for post in user_posts:
            likes = Vote.objects.filter(reel=post.reel).count()
            comments = Comment.objects.filter(reel=post.reel).count()
            shares = 0  # TODO: implement shares tracking
            
            total_likes += likes
            total_comments += comments
            total_shares += shares
            total_gifters += GiftTransaction.objects.filter(reel=post.reel).values('sender').distinct().count()
        
        engagement_score = (
            total_likes * config['engagement']['likes_weight'] +
            total_comments * config['engagement']['comments_weight'] +
            total_shares * config['engagement']['shares_weight'] +
            total_gifters * config['engagement'].get('gifts_weight', 0)
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
                daily_gamification['spin_rewards'] * config['gamification']['spin_reward'] +
                daily_gamification['coin_gifts_received'] * config['gamification']['coin_gift']
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
            'week_end': week_end.isoformat()
        }
    
    def select_weekly_winners(self, entries, winner_count=None):
        """
        Select top scorers as winners.
        Enforces one win per weekly cycle.
        Awards points to winners.
        """
        if winner_count is None:
            winner_count = self.campaign.winner_count
        
        # Filter out users who already won this cycle
        eligible_entries = []
        for entry in entries:
            user = entry.user
            stat = UserCampaignStats.objects.filter(user=user, campaign=self.campaign).first()
            
            if not stat or not stat.has_won_current_cycle:
                eligible_entries.append(entry)
        
        # Sort by score (highest first)
        eligible_entries.sort(key=lambda x: x.score, reverse=True)
        
        # Get point reward from wallet config
        from .models_wallet import WalletConfig
        wallet_config = WalletConfig.get_config()
        point_reward = wallet_config.weekly_winner_points
        
        winners = []
        for idx, entry in enumerate(eligible_entries[:winner_count], start=1):
            # Award points to winner
            user_profile = entry.user.profile
            user_profile.points += point_reward
            user_profile.points_earned_total += point_reward
            user_profile.save()
            
            winners.append({
                'rank': idx,
                'user': entry.user,
                'score': entry.score,
                'method': 'top_scorer',
                'points_awarded': point_reward
            })
            
            # Mark user as having won this cycle
            stat, _ = UserCampaignStats.objects.get_or_create(
                user=entry.user,
                campaign=self.campaign
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
            'details': {}
        }
        
        # Get all posts for the month
        month_start_dt = timezone.make_aware(datetime.combine(month_start, datetime.min.time()))
        month_end_dt = timezone.make_aware(datetime.combine(month_end, datetime.max.time()))
        
        user_posts = PostScore.objects.filter(
            user=user,
            campaign=self.campaign,
            created_at__range=(month_start_dt, month_end_dt),
            moderation_status='approved'
        ).select_related('reel')
        
        # 1. ENGAGEMENT (with potential high engagement bonuses)
        total_likes = 0
        total_comments = 0
        total_shares = 0
        total_gifters = 0
        high_engagement_posts = 0
        
        for post in user_posts:
            likes = Vote.objects.filter(reel=post.reel).count()
            comments = Comment.objects.filter(reel=post.reel).count()
            shares = 0
            
            total_likes += likes
            total_comments += comments
            total_shares += shares
            total_gifters += GiftTransaction.objects.filter(reel=post.reel).values('sender').distinct().count()
            
            # Check for high engagement bonus
            if likes >= config['high_engagement']['threshold']:
                high_engagement_posts += 1
        
        engagement_score = (
            total_likes * config['engagement']['likes_weight'] +
            total_comments * config['engagement']['comments_weight'] +
            total_shares * config['engagement']['shares_weight'] +
            total_gifters * config['engagement'].get('gifts_weight', 0)
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
                daily_gamification['spin_rewards'] * config['gamification']['spin_reward'] +
                daily_gamification['coin_gifts_received'] * config['gamification']['coin_gift']
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
            created_at__range=(month_start_dt, month_end_dt)
        ).count()
        
        weekly_bonus = weekly_wins * config['weekly_winner_bonus']
        score += weekly_bonus
        breakdown['weekly_winner_bonus'] = weekly_bonus
        breakdown['details']['weekly_wins_this_month'] = weekly_wins
        
        return {
            'total_score': score,
            'breakdown': breakdown,
            'month': month_date.strftime('%Y-%m')
        }
    
    def select_monthly_winners(self, entries, winner_count=None):
        """
        Select top scorers as winners.
        Enforces one win per monthly cycle.
        Awards points to winners.
        """
        if winner_count is None:
            winner_count = self.campaign.winner_count
        
        # Filter out users who already won this cycle
        eligible_entries = []
        for entry in entries:
            user = entry.user
            stat = UserCampaignStats.objects.filter(user=user, campaign=self.campaign).first()
            
            if not stat or not stat.has_won_current_cycle:
                eligible_entries.append(entry)
        
        # Sort by score
        eligible_entries.sort(key=lambda x: x.score, reverse=True)
        
        # Get point reward from wallet config
        from .models_wallet import WalletConfig
        wallet_config = WalletConfig.get_config()
        point_reward = wallet_config.monthly_winner_points
        
        winners = []
        for idx, entry in enumerate(eligible_entries[:winner_count], start=1):
            # Award points to winner
            user_profile = entry.user.profile
            user_profile.points += point_reward
            user_profile.points_earned_total += point_reward
            user_profile.save()
            
            winners.append({
                'rank': idx,
                'user': entry.user,
                'score': entry.score,
                'method': 'top_scorer',
                'points_awarded': point_reward
            })
            
            # Mark user as having won this cycle
            stat, _ = UserCampaignStats.objects.get_or_create(
                user=entry.user,
                campaign=self.campaign
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
            moderation_status='approved'
        ).select_related('reel')
        
        # Calculate qualification score (similar to monthly)
        total_likes = 0
        total_comments = 0
        total_shares = 0
        total_gifters = 0
        
        for post in user_posts:
            likes = Vote.objects.filter(reel=post.reel).count()
            comments = Comment.objects.filter(reel=post.reel).count()
            shares = 0
            gifters = GiftTransaction.objects.filter(reel=post.reel).values('sender').distinct().count()
            
            total_likes += likes
            total_comments += comments
            total_shares += shares
            total_gifters += gifters
        
        score = (
            total_likes * config['likes_weight'] +
            total_comments * config['comments_weight'] +
            total_shares * config['shares_weight'] +
            total_gifters * config.get('gifts_weight', 0)
        )
        
        return {
            'total_score': score,
            'details': {
                'likes': total_likes,
                'comments': total_comments,
                'shares': total_shares,
                'gifters': total_gifters,
                'posts_count': user_posts.count()
            }
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
            judge_criteria['creativity_max'] +
            judge_criteria['quality_max'] +
            judge_criteria['theme_max'] +
            judge_criteria['impact_max']
        )
        
        # Sum up judge scores
        total_judge_score = sum([
            judge_scores.get('creativity', 0),
            judge_scores.get('quality', 0),
            judge_scores.get('theme', 0),
            judge_scores.get('impact', 0)
        ])
        
        # Normalize judge score to percentage
        judge_normalized = (total_judge_score / max_judge_score) * 100 if max_judge_score > 0 else 0
        
        # Calculate vote score
        vote_value = config['voting']['vote_value']
        vote_score = vote_count * vote_value
        
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
                'raw_judge_total': total_judge_score
            }
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
        from .models_wallet import WalletConfig
        wallet_config = WalletConfig.get_config()
        point_reward = wallet_config.grand_finalist_points
        
        # Award points to finalists
        for entry in finalists:
            user_profile = entry.user.profile
            user_profile.points += point_reward
            user_profile.points_earned_total += point_reward
            user_profile.save()
        
        return [
            {
                'rank': idx + 1,
                'user': entry.user,
                'qualification_score': entry.score,
                'points_awarded': point_reward
            }
            for idx, entry in enumerate(finalists)
        ]
    
    def select_grand_winners(self, entries, winner_count=None):
        """
        Select winners based on final scores (Phase 2).
        Awards points to winners.
        """
        if winner_count is None:
            winner_count = self.campaign.winner_count
        
        # Sort by final score
        sorted_entries = sorted(entries, key=lambda x: x.score, reverse=True)
        
        # Get point reward from wallet config
        from .models_wallet import WalletConfig
        wallet_config = WalletConfig.get_config()
        point_reward = wallet_config.grand_winner_points
        
        winners = []
        for idx, entry in enumerate(sorted_entries[:winner_count], start=1):
            # Award points to winner
            user_profile = entry.user.profile
            user_profile.points += point_reward
            user_profile.points_earned_total += point_reward
            user_profile.save()
            
            winners.append({
                'rank': idx,
                'user': entry.user,
                'final_score': entry.score,
                'method': 'final_score',
                'points_awarded': point_reward
            })
        
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
            'posted_today': False
        }
    
    def _calculate_longest_streak(self, user, start_date, end_date):
        """Calculate longest consecutive posting streak within date range."""
        posts = PostScore.objects.filter(
            user=user,
            campaign=self.campaign,
            created_at__date__range=(start_date, end_date),
            moderation_status='approved'
        ).dates('created_at', 'day')
        
        post_dates = sorted(set(posts))
        
        if not post_dates:
            return 0
        
        longest = 1
        current = 1
        
        for i in range(1, len(post_dates)):
            if (post_dates[i] - post_dates[i-1]).days == 1:
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
                    user,
                    kwargs.get('judge_scores', {}),
                    kwargs.get('vote_count', 0)
                )
        else:
            raise ValueError(f"Unknown campaign type: {self.campaign_type}")
    
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
            raise ValueError(f"Unknown campaign type: {self.campaign_type}")
