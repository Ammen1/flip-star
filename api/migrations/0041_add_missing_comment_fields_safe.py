# Generated migration to safely add missing Comment fields

from django.db import connection, migrations


def is_field_exists(model_name, field_name):
    """Check whether a column exists, on any database backend.

    Previously this queried ``information_schema.columns``, which exists in
    PostgreSQL but not SQLite. On SQLite the query raised, a bare ``except``
    swallowed it and returned False, and the migration then tried to ADD a
    column that was already there -- so no fresh SQLite database could be
    built ("duplicate column name: is_deleted").

    Django's introspection API is portable and gives the same answer on
    PostgreSQL, so deployed behaviour is unchanged.
    """
    table_name = f'api_{model_name}'
    with connection.cursor() as cursor:
        if table_name not in connection.introspection.table_names(cursor):
            return False
        columns = connection.introspection.get_table_description(cursor, table_name)
        return any(column.name == field_name for column in columns)


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
