# Generated migration to safely add missing Comment fields

from django.db import migrations, connection
from django.db.migrations.executor import MigrationExecutor


def is_field_exists(model_name, field_name):
    """Check if a field exists in the database"""
    try:
        with connection.cursor() as cursor:
            table_name = f'api_{model_name}'
            # Use SQLite-specific query to check column existence
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            return any(col[1] == field_name for col in columns)
    except:
        return False


def add_missing_fields(apps, schema_editor):
    """Add missing fields only if they don't exist"""
    
    # Check and add is_deleted to Comment
    if not is_field_exists('comment', 'is_deleted'):
        schema_editor.execute("ALTER TABLE api_comment ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE;")
    
    # Check and add edited_at to Comment  
    if not is_field_exists('comment', 'edited_at'):
        schema_editor.execute("ALTER TABLE api_comment ADD COLUMN edited_at TIMESTAMP NULL;")
    
    # Check and add is_deleted to CommentReply
    if not is_field_exists('commentreply', 'is_deleted'):
        schema_editor.execute("ALTER TABLE api_commentreply ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE;")
    
    # Check and add edited_at to CommentReply
    if not is_field_exists('commentreply', 'edited_at'):
        schema_editor.execute("ALTER TABLE api_commentreply ADD COLUMN edited_at TIMESTAMP NULL;")


def reverse_add_missing_fields(apps, schema_editor):
    """Reverse the operation"""
    pass  # We don't want to drop fields on reverse


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0040_rename_api_convers_last_me_idx_api_convers_last_me_eb2fc0_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(
            add_missing_fields,
            reverse_add_missing_fields,
        ),
    ]
