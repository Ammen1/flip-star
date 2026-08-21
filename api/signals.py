from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from .models import UserProfile, Subscription, NotificationPreference, Notification, Vote, Comment, Follow

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
        Subscription.objects.create(user=instance)
        NotificationPreference.objects.create(user=instance)
        Token.objects.create(user=instance)
        
        # Give welcome bonus coins
        try:
            from .models.contest import UserCoinBalance, CoinTransaction
            from .models.wallet import WalletConfig
            config = WalletConfig.get_config()
            welcome_amount = config.welcome_bonus
            
            if welcome_amount > 0:
                balance, _ = UserCoinBalance.objects.get_or_create(user=instance)
                balance.earned_balance = (balance.earned_balance or 0) + welcome_amount
                balance.total_earned = (balance.total_earned or 0) + welcome_amount
                balance._sync_balance()
                balance.save()
                
                CoinTransaction.objects.create(
                    user=instance,
                    transaction_type='welcome_bonus',
                    coins=welcome_amount,
                    description=f'Welcome bonus: {welcome_amount} coins'
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to give welcome bonus: {e}")

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

@receiver(post_save, sender=Vote)
def create_like_notification(sender, instance, created, **kwargs):
    """Create notification when someone likes a reel"""
    if created and instance.user != instance.reel.user:
        # Check if recipient has like notifications enabled
        try:
            prefs = instance.reel.user.notification_prefs
            if not prefs.likes:
                return
        except NotificationPreference.DoesNotExist:
            pass
        Notification.objects.create(
            recipient=instance.reel.user,
            sender=instance.user,
            notification_type='like',
            reel=instance.reel,
            message=f"{instance.user.username} liked your reel"
        )

@receiver(post_save, sender=Comment)
def create_comment_notification(sender, instance, created, **kwargs):
    """Create notification when someone comments on a reel"""
    try:
        if created and instance.user != instance.reel.user:
            # Check if recipient has comment notifications enabled
            try:
                prefs = instance.reel.user.notification_prefs
                if not prefs.comments:
                    return
            except NotificationPreference.DoesNotExist:
                pass
            Notification.objects.create(
                recipient=instance.reel.user,
                sender=instance.user,
                notification_type='comment',
                reel=instance.reel,
                comment=instance,
                message=f"{instance.user.username} commented on your reel: {instance.text[:50]}"
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to create comment notification: {e}")

@receiver(post_save, sender=Follow)
def create_follow_notification(sender, instance, created, **kwargs):
    """Create notification when someone follows a user"""
    if created:
        # Check if recipient has follow notifications enabled
        try:
            prefs = instance.following.notification_prefs
            if not prefs.follows:
                return
        except NotificationPreference.DoesNotExist:
            pass
        Notification.objects.create(
            recipient=instance.following,
            sender=instance.follower,
            notification_type='follow',
            message=f"{instance.follower.username} started following you"
        )

@receiver(post_delete, sender=Vote)
def delete_like_notification(sender, instance, **kwargs):
    """Delete notification when someone unlikes a reel"""
    Notification.objects.filter(
        sender=instance.user,
        recipient=instance.reel.user,
        notification_type='like',
        reel=instance.reel
    ).delete()


@receiver(post_save, sender=Notification)
def push_notification_on_create(sender, instance, created, **kwargs):
    """Fan out a new Notification row to FCM (mobile) and Web Push (browser)."""
    if not created:
        return
    type_titles = {
        'like': 'New Like',
        'comment': 'New Comment',
        'follow': 'New Follower',
        'mention': 'You were mentioned',
        'gift': 'You received a gift!',
    }
    title = type_titles.get(instance.notification_type, 'FlipStar')
    payload = {
        'title': title,
        'body': instance.message,
        'data': {
            'notification_type': instance.notification_type,
            'reel_id': instance.reel_id,
            'comment_id': instance.comment_id,
            'notification_id': instance.id,
        },
    }
    # FCM / mobile push (best-effort, async via Celery if configured)
    try:
        from api.tasks import send_push_notification
        send_push_notification.delay(instance.recipient_id, payload)
    except Exception:
        pass
    # Web Push (browser) — synchronous but cheap; ignored if VAPID unset
    try:
        from .integrations.push.webpush import send_web_push_to_user
        send_web_push_to_user(instance.recipient, payload)
    except Exception:
        pass


@receiver(post_save, sender=UserProfile)
def optimize_profile_photo_on_save(sender, instance, **kwargs):
    """Queue profile photo optimisation whenever it changes."""
    if instance.profile_photo and not str(instance.profile_photo).startswith('http'):
        try:
            from api.tasks import optimize_profile_image
            optimize_profile_image.delay(instance.user_id)
        except Exception:
            pass
