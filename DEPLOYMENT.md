# Flipstar - Docker Deployment Guide

## Overview

Flipstar is a full-stack social media application with real-time messaging, deployed on Ethiopia Telecom server using Docker containers.

## Architecture


### Components

1. **Backend** - Django REST Framework with Django Channels for real-time WebSocket
2. **Frontend** - React with Vite, served by Nginx
3. **Database** - PostgreSQL
4. **Cache/Queue** - Redis for Celery and Django Channels
5. **Async Processing** - Celery workers for background tasks
6. **Media Storage** - AWS S3 (or local fallback)

### Docker Containers

- `postgres` - PostgreSQL database
- `redis` - Redis cache and message broker
- `backend` - Django application with Gunicorn
- `celery_worker` - Celery worker for async tasks
- `celery_beat` - Celery beat for scheduled tasks
- `frontend` - React frontend with Nginx

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- AWS S3 bucket (for media storage)
- Ethiopia Telecom server access

## Initial Setup

### 1. Clone/Deploy Code

```bash
# Copy the flipstar folder to your server
scp -r flipstar user@ethiotelecom-server:/path/to/deploy/
```

### 2. Run Setup Script

```bash
cd flipstar
./setup.sh
```

### 3. Configure Environment Variables

Edit `.env` file:

```bash
nano .env
```

Required variables:
```env
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=your-domain.com,localhost

# Database
DB_PASSWORD=your-secure-password

# AWS S3
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_STORAGE_BUCKET_NAME=flipstar-media
AWS_S3_REGION_NAME=us-east-1

# Redis (default works for Docker)
REDIS_HOST=redis
REDIS_PORT=6379
```

### 4. Deploy Application

```bash
./deploy.sh
```

## Deployment Process

The `deploy.sh` script performs the following:

1. Stops existing containers
2. Builds and starts all containers
3. Waits for database to be ready
4. Runs database migrations
5. Collects static files
6. Creates admin user if not exists

## Database Migrations

To run migrations manually:

```bash
docker-compose exec backend python manage.py migrate
```

To create new migrations:

```bash
docker-compose exec backend python manage.py makemigrations
docker-compose exec backend python manage.py migrate
```

## Backup and Restore

### Backup Database

```bash
./backup.sh
```

This creates a PostgreSQL backup and uploads it to S3.

### Restore Database

```bash
# Download backup from S3
aws s3 cp s3://flipstar-media/backups/flipstar_backup_YYYYMMDD_HHMMSS.sql.gz .

# Restore
gunzip flipstar_backup_YYYYMMDD_HHMMSS.sql.gz
docker-compose exec -T postgres psql -U flipstar_user flipstar_db < flipstar_backup_YYYYMMDD_HHMMSS.sql
```

## Monitoring

### View Logs

```bash
# All containers
docker-compose logs -f

# Specific container
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f celery_worker
```

### Check Container Status

```bash
docker-compose ps
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart backend
```

## Scaling

### Scale Celery Workers

```bash
docker-compose up -d --scale celery_worker=4
```

### Scale Backend

```bash
docker-compose up -d --scale backend=2
```

Note: You'll need a load balancer for scaling backend.

## Security

### Firewall Configuration

Ensure these ports are open:
- 80 (HTTP)
- 443 (HTTPS) - configure SSL with certbot
- 22 (SSH) - restrict to your IP

### SSL/HTTPS Setup

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
```

## Troubleshooting

### Database Connection Issues

```bash
# Check if database is running
docker-compose ps postgres

# View database logs
docker-compose logs postgres

# Restart database
docker-compose restart postgres
```

### Redis Connection Issues

```bash
# Check Redis
docker-compose exec redis redis-cli ping

# Should return: PONG
```

### Celery Not Processing Tasks

```bash
# Check Celery logs
docker-compose logs celery_worker

# Restart Celery
docker-compose restart celery_worker celery_beat
```

### Media Not Uploading to S3

1. Verify AWS credentials in `.env`
2. Check S3 bucket permissions
3. Ensure bucket is in correct region
4. Test S3 connectivity:
```bash
docker-compose exec backend python -c "
import boto3
s3 = boto3.client('s3')
print(s3.list_buckets())
"
```

## Performance Optimization

### Database

- Add indexes to frequently queried fields
- Use connection pooling (already configured in Django)
- Regular vacuum and analyze

### Redis

- Enable persistence (already configured)
- Monitor memory usage
- Consider Redis Cluster for large deployments

### Celery

- Adjust worker concurrency based on CPU cores
- Use task priorities
- Monitor task queue depth

## Updates

### Update Application Code

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose up -d --build backend frontend

# Run migrations
docker-compose exec backend python manage.py migrate
```

### Update Docker Images

```bash
# Pull latest base images
docker-compose pull

# Rebuild
docker-compose up -d --build
```

## Support

For issues or questions:
1. Check logs: `docker-compose logs`
2. Review documentation
3. Contact system administrator
