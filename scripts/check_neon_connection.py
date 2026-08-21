#!/usr/bin/env python3
"""
Neon Database Connection Checker for SelfiStar
This script will verify the database connection and show table information
"""

import os
import sys
import django
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

try:
    django.setup()
except Exception as e:
    print(f"❌ Django setup failed: {e}")
    print("Make sure your .env file is configured correctly")
    sys.exit(1)

def check_database_connection():
    """Check if we can connect to the database"""
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            return result[0] == 1
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

def show_database_info():
    """Show database information and tables"""
    try:
        from django.db import connection
        
        with connection.cursor() as cursor:
            # Get database info
            cursor.execute("SELECT version()")
            db_version = cursor.fetchone()[0]
            print(f"✅ Database Version: {db_version}")
            
            # Get current database
            cursor.execute("SELECT current_database()")
            db_name = cursor.fetchone()[0]
            print(f"✅ Current Database: {db_name}")
            
            # Get current user
            cursor.execute("SELECT current_user")
            db_user = cursor.fetchone()[0]
            print(f"✅ Connected as: {db_user}")
            
            print("\n📋 Database Tables:")
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
            tables = cursor.fetchall()
            
            if tables:
                for table in tables:
                    table_name = table[0]
                    print(f"  📄 {table_name}")
                    
                    # Get row count for each table
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    print(f"     └─ {count} rows")
            else:
                print("  ❌ No tables found - need to run migrations!")
                
    except Exception as e:
        print(f"❌ Error getting database info: {e}")

def show_django_apps():
    """Show Django apps and their models"""
    try:
        from django.apps import apps
        
        print("\n🎯 Django Apps and Models:")
        for app in apps.get_app_configs():
            print(f"  📦 {app.name}")
            for model in app.get_models():
                print(f"     └─ {model.__name__}")
                
    except Exception as e:
        print(f"❌ Error getting Django apps: {e}")

def run_migrations():
    """Run Django migrations"""
    try:
        print("\n🔄 Running Django migrations...")
        from django.core.management import execute_from_command_line
        execute_from_command_line(['manage.py', 'migrate', '--verbosity=2'])
        print("✅ Migrations completed!")
    except Exception as e:
        print(f"❌ Migration error: {e}")

def create_sample_data():
    """Create sample data for testing"""
    try:
        print("\n📝 Creating sample data...")
        from django.contrib.auth.models import User
        from api.models import UserProfile, Reel
        
        # Create test user
        if not User.objects.filter(username='testuser').exists():
            user = User.objects.create_user(
                username='testuser',
                email='test@example.com',
                password='testpass123',
                first_name='Test',
                last_name='User'
            )
            UserProfile.objects.create(user=user, xp=0)
            print("✅ Created test user")
        else:
            print("ℹ️ Test user already exists")
            
        print("✅ Sample data check completed!")
        
    except Exception as e:
        print(f"❌ Error creating sample data: {e}")

def main():
    print("🔍 SelfiStar Neon Database Checker")
    print("=" * 50)
    
    # Step 1: Check connection
    print("\n🔌 Step 1: Checking database connection...")
    if check_database_connection():
        print("✅ Database connection successful!")
        
        # Step 2: Show database info
        print("\n📊 Step 2: Database information...")
        show_database_info()
        
        # Step 3: Show Django apps
        show_django_apps()
        
        # Step 4: Ask if user wants to run migrations
        print("\n🤔 Would you like to:")
        print("1. Run migrations (if no tables exist)")
        print("2. Create sample data")
        print("3. Both")
        print("4. Exit")
        
        try:
            choice = input("\nEnter choice (1-4): ").strip()
            
            if choice in ['1', '3']:
                run_migrations()
            if choice in ['2', '3']:
                create_sample_data()
            elif choice == '4':
                print("👋 Goodbye!")
                
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            
    else:
        print("❌ Database connection failed!")
        print("Please check your .env file and Neon credentials")

if __name__ == "__main__":
    main()
