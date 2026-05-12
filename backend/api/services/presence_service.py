import redis
from decouple import config
from django.utils import timezone


class PresenceService:
    """Service for tracking user presence (online/offline status)."""
    
    def __init__(self):
        self.redis = redis.Redis(
            host=config('REDIS_HOST', default='127.0.0.1'),
            port=int(config('REDIS_PORT', default=6379)),
            db=0,
            decode_responses=True
        )
        self.online_ttl = 300  # 5 minutes
        self.typing_ttl = 3  # 3 seconds
    
    def set_user_online(self, user_id):
        """Set user as online in Redis."""
        key = f'user_online:{user_id}'
        self.redis.set(key, '1', ex=self.online_ttl)
        # Update last seen timestamp
        self.redis.set(f'last_seen:{user_id}', timezone.now().isoformat(), ex=86400)  # 24 hours
    
    def set_user_offline(self, user_id):
        """Remove user from online status."""
        key = f'user_online:{user_id}'
        self.redis.delete(key)
        # Update last seen to now
        self.redis.set(f'last_seen:{user_id}', timezone.now().isoformat(), ex=86400)
    
    def is_user_online(self, user_id):
        """Check if user is currently online."""
        key = f'user_online:{user_id}'
        return self.redis.exists(key) > 0
    
    def get_last_seen(self, user_id):
        """Get user's last seen timestamp."""
        key = f'last_seen:{user_id}'
        last_seen = self.redis.get(key)
        if last_seen:
            return last_seen
        return None
    
    def set_typing(self, conversation_id, user_id):
        """Set user as typing in a conversation."""
        key = f'typing:{conversation_id}:{user_id}'
        self.redis.set(key, '1', ex=self.typing_ttl)
    
    def remove_typing(self, conversation_id, user_id):
        """Remove typing indicator for user."""
        key = f'typing:{conversation_id}:{user_id}'
        self.redis.delete(key)
    
    def get_typing_users(self, conversation_id):
        """Get list of users currently typing in a conversation."""
        pattern = f'typing:{conversation_id}:*'
        keys = self.redis.keys(pattern)
        typing_users = []
        for key in keys:
            user_id = key.split(':')[-1]
            typing_users.append(int(user_id))
        return typing_users
    
    def get_online_users(self, user_ids):
        """Get online status for multiple users."""
        online_users = []
        for user_id in user_ids:
            if self.is_user_online(user_id):
                online_users.append(user_id)
        return online_users


# Singleton instance
presence_service = PresenceService()
