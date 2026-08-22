#!/bin/bash

# Flipstar Database Backup Script
# This script backs up the PostgreSQL database to S3

set -e




BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="flipstar_backup_${DATE}.sql"

echo "=== Flipstar Database Backup ==="

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup PostgreSQL database
echo "Backing up database..."
docker-compose exec -T postgres pg_dump -U flipstar_user flipstar_db > $BACKUP_DIR/$BACKUP_FILE

# Compress backup
echo "Compressing backup..."
gzip $BACKUP_DIR/$BACKUP_FILE

# Upload to S3 (if AWS credentials are configured)
if [ -n "$AWS_STORAGE_BUCKET_NAME" ]; then
    echo "Uploading backup to S3..."
    aws s3 cp $BACKUP_DIR/${BACKUP_FILE}.gz s3://$AWS_STORAGE_BUCKET_NAME/backups/
fi

# Clean up old backups (keep last 7 days)
echo "Cleaning up old backups..."
find $BACKUP_DIR -name "flipstar_backup_*.sql.gz" -mtime +7 -delete

echo "=== Backup Complete ==="
echo "Backup saved to: $BACKUP_DIR/${BACKUP_FILE}.gz"
