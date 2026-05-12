#!/usr/bin/env python3
"""
Database Comparison Tool - Local vs Neon
This script will compare your local pgAdmin database with Neon
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
    sys.exit(1)

def get_database_info():
    """Get current database connection info"""
    try:
        from django.db import connection
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, version()")
            db_info = cursor.fetchone()
            return {
                'database': db_info[0],
                'user': db_info[1], 
                'version': db_info[2]
            }
    except Exception as e:
        print(f"❌ Error getting database info: {e}")
        return None

def get_all_tables():
    """Get all tables in the database"""
    try:
        from django.db import connection
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT table_name, 
                       (SELECT COUNT(*) FROM information_schema.columns 
                        WHERE table_name = t.table_name AND table_schema = 'public') as column_count,
                       (SELECT COALESCE(SUM(n_tup_ins), 0) FROM pg_stat_user_tables 
                        WHERE relname = t.table_name) as row_count
                FROM information_schema.tables t
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = cursor.fetchall()
            return [{'name': row[0], 'columns': row[1], 'rows': row[2]} for row in tables]
    except Exception as e:
        print(f"❌ Error getting tables: {e}")
        return []

def get_table_schema(table_name):
    """Get detailed schema for a specific table"""
    try:
        from django.db import connection
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = 'public'
                ORDER BY ordinal_position
            """, [table_name])
            columns = cursor.fetchall()
            return [{'name': col[0], 'type': col[1], 'nullable': col[2], 'default': col[3]} for col in columns]
    except Exception as e:
        print(f"❌ Error getting schema for {table_name}: {e}")
        return []

def get_django_model_info():
    """Get Django model information"""
    try:
        from django.apps import apps
        models_info = {}
        
        for app in apps.get_app_configs():
            for model in app.get_models():
                app_label = app.label
                if app_label not in models_info:
                    models_info[app_label] = []
                
                # Get model fields
                fields = []
                for field in model._meta.get_fields():
                    fields.append({
                        'name': field.name,
                        'type': field.__class__.__name__,
                        'required': not field.null,
                        'default': field.default if hasattr(field, 'default') else None
                    })
                
                models_info[app_label].append({
                    'name': model.__name__,
                    'table': model._meta.db_table,
                    'fields': fields
                })
        
        return models_info
    except Exception as e:
        print(f"❌ Error getting Django models: {e}")
        return {}

def check_sample_data():
    """Check for sample data in key tables"""
    try:
        from django.db import connection
        from django.contrib.auth.models import User
        
        sample_data = {}
        
        # Check users
        user_count = User.objects.count()
        sample_data['users'] = user_count
        
        # Check other tables
        key_tables = ['api_userprofile', 'api_reel', 'api_comment', 'api_hashtag']
        
        with connection.cursor() as cursor:
            for table in key_tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    sample_data[table] = count
                except:
                    sample_data[table] = 0
        
        return sample_data
    except Exception as e:
        print(f"❌ Error checking sample data: {e}")
        return {}

def generate_comparison_report():
    """Generate a comprehensive comparison report"""
    print("🔍 Database Comparison Report")
    print("=" * 60)
    
    # Get database info
    db_info = get_database_info()
    if db_info:
        print(f"\n📊 Current Database:")
        print(f"  🗄️  Database: {db_info['database']}")
        print(f"  👤 User: {db_info['user']}")
        print(f"  🔧 Version: {db_info['version'][:50]}...")
    
    # Get all tables
    tables = get_all_tables()
    print(f"\n📋 Database Tables ({len(tables)} found):")
    
    for table in tables:
        print(f"  📄 {table['name']:<30} | Columns: {table['columns']:<3} | Rows: {table['rows']:<5}")
    
    # Get Django model info
    models_info = get_django_model_info()
    print(f"\n🎯 Django Apps & Models:")
    
    for app_label, models in models_info.items():
        print(f"  📦 {app_label}:")
        for model in models:
            print(f"     └─ {model['name']:<20} → {model['table']}")
    
    # Check sample data
    sample_data = check_sample_data()
    print(f"\n📊 Sample Data:")
    for table, count in sample_data.items():
        print(f"  📄 {table:<20}: {count} rows")
    
    # Generate expected tables list
    expected_tables = [
        'django_migrations',
        'django_session', 
        'auth_user',
        'auth_group',
        'auth_user_groups',
        'api_userprofile',
        'api_reel',
        'api_comment',
        'api_like',
        'api_follow',
        'api_hashtag',
        'api_reel_hashtags',
        'api_savedpost',
        'api_notification',
        'api_report',
        'api_campaign',
        'api_campaignentry'
    ]
    
    print(f"\n✅ Expected vs Actual Tables:")
    actual_tables = [t['name'] for t in tables]
    
    for expected in expected_tables:
        if expected in actual_tables:
            status = "✅"
        else:
            status = "❌"
        print(f"  {status} {expected}")
    
    # Check for unexpected tables
    unexpected = [t for t in actual_tables if t not in expected_tables]
    if unexpected:
        print(f"\n⚠️  Unexpected Tables:")
        for table in unexpected:
            print(f"  ❓ {table}")
    
    return {
        'db_info': db_info,
        'tables': tables,
        'models': models_info,
        'sample_data': sample_data,
        'expected_missing': [t for t in expected_tables if t not in actual_tables],
        'unexpected': unexpected
    }

def main():
    print("🔍 SelfiStar Database Comparison Tool")
    print("This will check your current database and compare with expected structure")
    print("=" * 70)
    
    # Generate report
    report = generate_comparison_report()
    
    # Summary
    print(f"\n📋 Summary:")
    print(f"  📄 Total Tables: {len(report['tables'])}")
    print(f"  ❌ Missing Tables: {len(report['expected_missing'])}")
    print(f"  ❓ Unexpected Tables: {len(report['unexpected'])}")
    
    if report['expected_missing']:
        print(f"\n❌ Missing Tables (need to run migrations):")
        for table in report['expected_missing']:
            print(f"  📄 {table}")
        print(f"\n💡 Solution: Run 'python manage.py migrate'")
    
    if report['sample_data']['users'] == 0:
        print(f"\n💡 No users found - create admin with 'python manage.py createsuperuser'")
    
    print(f"\n🎯 Next Steps:")
    print(f"1. If missing tables: Run migrations")
    print(f"2. If no data: Create sample data")
    print(f"3. Check Neon console for same tables")
    print(f"4. Verify frontend can connect")

if __name__ == "__main__":
    main()
