import os
import django
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from api.models import UserProfile, Reel, Quest, Competition, Subscription
from django.utils import timezone
from datetime import timedelta

def create_sample_data():
    print("🚀 Creating sample data for Selfie Star platform...")
    
    # Create sample users
    print("\n👥 Creating sample users...")
    users_data = [
        {'username': 'sarah_creator', 'email': 'sarah@example.com', 'first_name': 'Sarah', 'last_name': 'Johnson'},
        {'username': 'mike_photos', 'email': 'mike@example.com', 'first_name': 'Mike', 'last_name': 'Chen'},
        {'username': 'emma_star', 'email': 'emma@example.com', 'first_name': 'Emma', 'last_name': 'Williams'},
        {'username': 'alex_creative', 'email': 'alex@example.com', 'first_name': 'Alex', 'last_name': 'Rodriguez'},
        {'username': 'lisa_vibes', 'email': 'lisa@example.com', 'first_name': 'Lisa', 'last_name': 'Anderson'},
    ]
    
    created_users = []
    for user_data in users_data:
        user, created = User.objects.get_or_create(
            username=user_data['username'],
            defaults={
                'email': user_data['email'],
                'first_name': user_data['first_name'],
                'last_name': user_data['last_name'],
            }
        )
        if created:
            user.set_password('password123')
            user.save()
            print(f"  ✓ Created user: {user.username}")
        created_users.append(user)
    
    # Update user profiles with sample data
    print("\n📊 Updating user profiles...")
    profile_updates = [
        {'xp': 1250, 'level': 5, 'streak': 7, 'bio': 'Photography enthusiast 📸 | Nature lover 🌿'},
        {'xp': 890, 'level': 4, 'streak': 3, 'bio': 'Street photographer | Urban explorer 🏙️'},
        {'xp': 2100, 'level': 8, 'streak': 12, 'bio': 'Content creator ✨ | Fashion & lifestyle'},
        {'xp': 650, 'level': 3, 'streak': 5, 'bio': 'Creative mind | Art & design 🎨'},
        {'xp': 1500, 'level': 6, 'streak': 9, 'bio': 'Travel photographer ✈️ | Adventure seeker'},
    ]
    
    for user, updates in zip(created_users, profile_updates):
        profile = user.profile
        profile.xp = updates['xp']
        profile.level = updates['level']
        profile.streak = updates['streak']
        profile.bio = updates['bio']
        profile.last_checkin = timezone.now() - timedelta(hours=2)
        profile.save()
        print(f"  ✓ Updated profile for {user.username}: Level {profile.level}, XP {profile.xp}")
    
    # Create sample reels
    print("\n📸 Creating sample reels...")
    reels_data = [
        {'caption': 'Beautiful sunset at the beach 🌅 #sunset #beach #nature', 'votes': 45, 'hashtags': 'sunset,beach,nature'},
        {'caption': 'Coffee and creativity ☕️ #coffee #morning #lifestyle', 'votes': 32, 'hashtags': 'coffee,morning,lifestyle'},
        {'caption': 'City lights at night 🌃 #city #night #urban', 'votes': 67, 'hashtags': 'city,night,urban'},
        {'caption': 'Weekend vibes 😎 #weekend #fun #friends', 'votes': 28, 'hashtags': 'weekend,fun,friends'},
        {'caption': 'Nature therapy 🌲 #nature #hiking #outdoors', 'votes': 51, 'hashtags': 'nature,hiking,outdoors'},
        {'caption': 'Fashion forward 👗 #fashion #style #ootd', 'votes': 89, 'hashtags': 'fashion,style,ootd'},
        {'caption': 'Foodie adventures 🍕 #food #foodie #delicious', 'votes': 42, 'hashtags': 'food,foodie,delicious'},
        {'caption': 'Fitness journey 💪 #fitness #gym #health', 'votes': 38, 'hashtags': 'fitness,gym,health'},
    ]
    
    for i, reel_data in enumerate(reels_data):
        user = created_users[i % len(created_users)]
        reel, created = Reel.objects.get_or_create(
            user=user,
            caption=reel_data['caption'],
            defaults={
                'votes': reel_data['votes'],
                'hashtags': reel_data['hashtags'],
            }
        )
        if created:
            print(f"  ✓ Created reel by {user.username}: {reel.caption[:40]}...")
    
    # Create sample quests
    print("\n🎮 Creating sample quests...")
    quests_data = [
        {'title': 'First Post', 'description': 'Upload your first reel to the platform', 'xp_reward': 100, 'is_active': True},
        {'title': 'Social Butterfly', 'description': 'Follow 10 other users', 'xp_reward': 150, 'is_active': True},
        {'title': 'Engagement Master', 'description': 'Get 50 votes on a single reel', 'xp_reward': 200, 'is_active': True},
        {'title': 'Daily Streak', 'description': 'Check in for 7 consecutive days', 'xp_reward': 250, 'is_active': True},
        {'title': 'Content Creator', 'description': 'Upload 10 reels', 'xp_reward': 300, 'is_active': True},
        {'title': 'Trending Star', 'description': 'Get 100 total votes across all reels', 'xp_reward': 500, 'is_active': True},
    ]
    
    for quest_data in quests_data:
        quest, created = Quest.objects.get_or_create(
            title=quest_data['title'],
            defaults={
                'description': quest_data['description'],
                'xp_reward': quest_data['xp_reward'],
                'is_active': quest_data['is_active'],
            }
        )
        if created:
            print(f"  ✓ Created quest: {quest.title} ({quest.xp_reward} XP)")
    
    # Create sample competitions
    print("\n🏆 Creating sample competitions...")
    competitions_data = [
        {
            'title': 'Spring Photo Contest',
            'description': 'Capture the beauty of spring! Best photo wins a premium subscription.',
            'start_date': timezone.now(),
            'end_date': timezone.now() + timedelta(days=30),
            'prize': 'Premium Subscription (3 months) + Featured Profile',
            'is_active': True,
        },
        {
            'title': 'Weekend Challenge',
            'description': 'Share your best weekend moment. Most votes win!',
            'start_date': timezone.now() - timedelta(days=2),
            'end_date': timezone.now() + timedelta(days=5),
            'prize': 'Pro Subscription (1 month) + 1000 XP',
            'is_active': True,
        },
    ]
    
    for comp_data in competitions_data:
        comp, created = Competition.objects.get_or_create(
            title=comp_data['title'],
            defaults={
                'description': comp_data['description'],
                'start_date': comp_data['start_date'],
                'end_date': comp_data['end_date'],
                'prize': comp_data['prize'],
                'is_active': comp_data['is_active'],
            }
        )
        if created:
            print(f"  ✓ Created competition: {comp.title}")
    
    # Create sample subscriptions
    print("\n💎 Creating sample subscriptions...")
    subscription_plans = ['free', 'pro', 'premium', 'free', 'pro']
    
    for user, plan in zip(created_users, subscription_plans):
        subscription, created = Subscription.objects.get_or_create(
            user=user,
            defaults={'plan': plan}
        )
        if plan != 'free':
            subscription.plan = plan
            subscription.expires_at = timezone.now() + timedelta(days=30)
            subscription.save()
        if created:
            print(f"  ✓ Created {plan} subscription for {user.username}")
    
    print("\n✅ Sample data creation complete!")
    print("\n📊 Summary:")
    print(f"  • Users: {User.objects.count()}")
    print(f"  • Reels: {Reel.objects.count()}")
    print(f"  • Quests: {Quest.objects.count()}")
    print(f"  • Competitions: {Competition.objects.count()}")
    print(f"  • Subscriptions: {Subscription.objects.count()}")
    print("\n🎉 Your admin panel is now populated with sample data!")
    print(f"\n🔗 Access the admin panel at: http://localhost:8000/admin/")
    print(f"   Username: admin")
    print(f"   Password: admin123")

if __name__ == '__main__':
    create_sample_data()
