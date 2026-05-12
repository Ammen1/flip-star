from rest_framework import serializers
from django.db import DatabaseError
from .models import Comment, CommentLike, CommentReply, SavedPost
from .serializers import UserSerializer

class CommentReplySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    comment = serializers.PrimaryKeyRelatedField(queryset=Comment.objects.all(), required=False)
    parent_reply = serializers.PrimaryKeyRelatedField(queryset=CommentReply.objects.all(), required=False, allow_null=True)
    is_editable = serializers.SerializerMethodField()
    
    class Meta:
        model = CommentReply
        fields = ['id', 'user', 'comment', 'parent_reply', 'text', 'created_at', 'edited_at', 'is_deleted', 'is_editable']
        read_only_fields = ['user', 'created_at', 'edited_at', 'is_deleted']
    
    def validate(self, data):
        # Ensure either comment or parent_reply is provided
        if not data.get('comment') and not data.get('parent_reply'):
            raise serializers.ValidationError("Either comment or parent_reply must be provided")
        return data
    
    def get_is_editable(self, obj):
        try:
            return obj.is_editable
        except (DatabaseError, AttributeError):
            # If is_editable property fails due to missing fields, default to False
            return False

class CommentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    likes_count = serializers.SerializerMethodField()
    replies_count = serializers.SerializerMethodField()
    replies = CommentReplySerializer(many=True, read_only=True)
    is_liked = serializers.SerializerMethodField()
    is_editable = serializers.SerializerMethodField()
    
    class Meta:
        model = Comment
        fields = ['id', 'user', 'reel', 'text', 'created_at', 'edited_at', 'is_deleted', 'likes_count', 'replies_count', 'replies', 'is_liked', 'is_editable']
        read_only_fields = ['user', 'created_at', 'edited_at', 'is_deleted']
    
    def get_is_editable(self, obj):
        try:
            return obj.is_editable
        except (DatabaseError, AttributeError):
            # If is_editable property fails due to missing fields, default to False
            return False
    
    def get_likes_count(self, obj):
        return obj.likes_count
    
    def get_replies_count(self, obj):
        return obj.replies_count
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return CommentLike.objects.filter(user=request.user, comment=obj).exists()
        return False

class CommentLikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommentLike
        fields = ['id', 'user', 'comment', 'created_at']
        read_only_fields = ['user', 'created_at']

class SavedPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedPost
        fields = ['id', 'user', 'reel', 'created_at']
        read_only_fields = ['user', 'created_at']
