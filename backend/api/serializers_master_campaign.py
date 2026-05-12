from rest_framework import serializers
from django.contrib.auth.models import User
from .models_master_campaign import MasterCampaign, MasterCampaignParticipant

class MasterCampaignSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    duration_days = serializers.SerializerMethodField()
    current_phase = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()
    
    class Meta:
        model = MasterCampaign
        fields = [
            'id', 'title', 'description', 'image', 'start_date', 'end_date', 
            'status', 'auto_generate_daily', 'auto_generate_weekly', 
            'auto_generate_monthly', 'auto_generate_grand', 'min_followers', 
            'min_level', 'required_hashtags', 'created_by', 'created_by_username',
            'created_at', 'updated_at', 'total_participants', 'total_daily_campaigns',
            'total_weekly_campaigns', 'total_monthly_campaigns', 'total_grand_campaigns',
            'duration_days', 'current_phase', 'participant_count'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'total_participants']
    
    def get_duration_days(self, obj):
        return obj.get_duration_days()
    
    def get_current_phase(self, obj):
        return obj.get_current_phase()
    
    def get_participant_count(self, obj):
        return obj.participants.count()

class MasterCampaignParticipantSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    user_level = serializers.IntegerField(source='user.profile.level', read_only=True)
    
    class Meta:
        model = MasterCampaignParticipant
        fields = [
            'id', 'master_campaign', 'user', 'username', 'user_level',
            'joined_at', 'is_active', 'total_daily_wins', 'total_weekly_wins',
            'total_monthly_wins', 'total_grand_wins', 'total_score', 'total_posts'
        ]
        read_only_fields = ['joined_at', 'total_score']
