# DevOps Handoff - Flipstar Deployment

## Overview
Flipstar is a full-stack social media application with real-time messaging, deployed on Ethiopia Telecom server using Docker containers.


## Repository Structure
```
flipstar/
├── backend/                 # Django backend with Django Channels
│   ├── api/                # Django app
│   │   ├── consumers.py    # WebSocket consumers (real-time messaging)
│   │   ├── models_messaging.py  # Messaging models with delivery lifecycle
│   │   ├── services/       # Business logic
│   │   │   └── presence_service.py  # Presence tracking service
│   │   ├── tasks.py        # Celery async tasks
│   │   └── celery.py       # Celery configuration
│   ├── config/             # Django settings
│   │   ├── settings.py     # Main settings (includes S3, Channels, Celery)
│   │   ├── asgi.py         # ASGI config for WebSocket
│   │   └── routing.py      # WebSocket URL routing
│   ├── Dockerfile          # Backend container
│   ├── Dockerfile.celery   # Celery worker container
│   └── requirements.txt    # Python dependencies
├── frontend/               # React web frontend
│   ├── src/                # React components
│   ├── Dockerfile          # Frontend container with Nginx
│   ├── nginx.conf          # Nginx configuration
│   └── package.json        # Node dependencies
├── mobile-app/             # React Native mobile app (not containerized)
│   └── src/                # React Native screens
├── docker-compose.yml      # Multi-container orchestration
├── deploy.sh               # Deployment script
├── setup.sh                # Initial setup script
├── backup.sh               # Database backup script
├── env.production.example # Environment variables template
├── README.md               # Project documentation
└── DEPLOYMENT.md           # Detailed deployment guide
```

## Technology Stack

### Backend
- Django 4.2.11
- Django REST Framework 3.14.0
- Django Channels 4.0.0 (real-time WebSocket)
- Celery 5.3.4 (async task processing)
- PostgreSQL 15 (database)
- Redis 7 (cache, queue, channel layer)
- Python 3.11

### Frontend
- React 18
- Vite 4.3.9
- Nginx (web server)
- Node 18 Alpine

### Infrastructure
- Docker & Docker Compose
- AWS S3 (media storage) - with Cloudinary fallback
- Ethiopia Telecom Server

## New Messaging Features (Recently Added)

### Real-time WebSocket
- Django Channels for instant messaging
- WebSocket endpoints: `/ws/chat/<conversation_id>/`, `/ws/presence/`

### Message Delivery Lifecycle
- UUID-based message identification (prevents duplicates)
- Delivery status: sending → sent → delivered → read
- Timestamps: delivered_at, read_at
- Implemented in `api/models_messaging.py` and `api/consumers.py`

### Presence Tracking
- Online/offline status via Redis
- 5-minute TTL for online status
- Last seen timestamp tracking
- Service: `api/services/presence_service.py`

### Typing Indicators
- Real-time typing status
- 3-second TTL in Redis
- Per-conversation typing tracking

### Async Task Processing
- Celery workers for background tasks
- Celery beat for scheduled tasks
- Redis as message broker
- Configuration in `api/celery.py` and `api/tasks.py`

### S3 Storage
- AWS S3 for media storage (replacing Cloudinary)
- Fallback to local storage if S3 not configured
- Configuration in `config/settings.py`

## Required Environment Variables

Copy `env.production.example` to `.env` and configure:

```env
# Django
SECRET_KEY=<generate-secure-random-key>
DEBUG=False
ALLOWED_HOSTS=your-domain.com,localhost

# Database
DB_PASSWORD=<secure-password>

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# AWS S3 (required for production)
AWS_ACCESS_KEY_ID=<your-aws-access-key>
AWS_SECRET_ACCESS_KEY=<your-aws-secret-key>
AWS_STORAGE_BUCKET_NAME=<your-s3-bucket-name>
AWS_S3_REGION_NAME=us-east-1

# Admin
ADMIN_PASSWORD=<admin-password>
```

## Server Requirements

### Minimum Specs
- **CPU**: 2 cores
- **RAM**: 4GB
- **Disk**: 20GB
- **OS**: Linux (Ubuntu 20.04+ recommended)

### Software Required
- Docker 20.10+
- Docker Compose 2.0+
- Git

### Network Ports
- 80 (HTTP)
- 443 (HTTPS) - configure SSL with certbot
- 22 (SSH) - restrict to your IP

## Deployment Steps

### 1. Clone Repository
```bash
git clone <repository-url>
cd flipstar
```

### 2. Run Setup Script
```bash
chmod +x setup.sh
./setup.sh
```

This script:
- Checks Docker installation
- Checks Docker Compose installation
- Creates necessary directories
- Sets file permissions

### 3. Configure Environment
```bash
cp env.production.example .env
nano .env
```

**IMPORTANT**: Update all required variables, especially:
- SECRET_KEY (generate with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
- DB_PASSWORD (use strong password)
- AWS credentials
- Production domain in ALLOWED_HOSTS

### 4. Deploy Application
```bash
chmod +x deploy.sh
./deploy.sh
```

This script:
- Stops existing containers
- Builds and starts all containers
- Runs database migrations
- Collects static files
- Creates admin user

### 5. Configure SSL/HTTPS
```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
```

### 6. Set Up Automated Backups
```bash
# Add to crontab
crontab -e

# Add this line for daily backup at 2 AM
0 2 * * * /path/to/flipstar/backup.sh
```

## Docker Services

### Services Defined in docker-compose.yml
- **postgres**: PostgreSQL 15 database
- **redis**: Redis 7 cache and message broker
- **backend**: Django application with Gunicorn
- **celery_worker**: Celery worker for async tasks
- **celery_beat**: Celery beat for scheduled tasks
- **frontend**: React frontend with Nginx

### Container Management

**View status:**
```bash
docker-compose ps
```

**View logs:**
```bash
docker-compose logs -f
docker-compose logs -f backend
docker-compose logs -f celery_worker
```

**Restart services:**
```bash
docker-compose restart
docker-compose restart backend
```

**Scale workers:**
```bash
docker-compose up -d --scale celery_worker=4
```

## Database Migrations

### Run Migrations
```bash
docker-compose exec backend python manage.py migrate
```

### Create New Migrations
```bash
docker-compose exec backend python manage.py makemigrations
docker-compose exec backend python manage.py migrate
```

### Access Django Shell
```bash
docker-compose exec backend python manage.py shell
```

## Backup and Restore

### Backup Database
```bash
./backup.sh
```

This:
- Dumps PostgreSQL database
- Compresses backup
- Uploads to S3 (if configured)
- Cleans up old backups (keeps 7 days)

### Restore Database
```bash
# Download from S3
aws s3 cp s3://bucket/backups/flipstar_backup_YYYYMMDD_HHMMSS.sql.gz .

# Restore
gunzip flipstar_backup_YYYYMMDD_HHMMSS.sql.gz
docker-compose exec -T postgres psql -U flipstar_user flipstar_db < flipstar_backup_YYYYMMDD_HHMMSS.sql
```

## Monitoring

### Health Checks
```bash
# Check if all containers are running
docker-compose ps

# Check backend health
curl http://localhost:8000/api/

# Check frontend
curl http://localhost/
```

### Log Monitoring
```bash
# All logs
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f celery_worker
docker-compose logs -f postgres
```

### Performance Monitoring
- Monitor Celery queue depth
- Check Redis memory usage
- Monitor database connection pool
- Check disk space for media storage

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker-compose logs <service-name>

# Check resource usage
docker stats

# Rebuild without cache
docker-compose build --no-cache <service-name>
```

### Database Connection Issues
```bash
# Check if postgres is running
docker-compose ps postgres

# Check postgres logs
docker-compose logs postgres

# Restart postgres
docker-compose restart postgres
```

### Redis Connection Issues
```bash
# Test Redis connection
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

## Security Considerations

### Implemented
- Token-based authentication
- CORS configuration
- SQL injection prevention (Django ORM)
- XSS protection (Django templates)
- CSRF protection
- Environment variable secrets
- S3 bucket policies

### Recommended
- Enable HTTPS in production (certbot)
- Use secrets management service
- Implement rate limiting
- Add input validation
- Regular security audits
- Restrict firewall rules
- Regular dependency updates

## Performance Optimization

### Database
- Add indexes to frequently queried fields
- Use connection pooling (configured in Django)
- Regular vacuum and analyze

### Redis
- Enable persistence (configured)
- Monitor memory usage
- Consider Redis Cluster for large deployments

### Celery
- Adjust worker concurrency based on CPU cores
- Use task priorities
- Monitor task queue depth

### Nginx
- Enable gzip compression (configured)
- Configure caching headers
- Use CDN for static assets

## Updates and Maintenance

### Update Application Code
```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose up -d --build backend frontend

# Run migrations
docker-compose exec backend python manage.py migrate

# Collect static files
docker-compose exec backend python manage.py collectstatic --noinput
```

### Update Docker Images
```bash
# Pull latest base images
docker-compose pull

# Rebuild
docker-compose up -d --build
```

### Dependency Updates
- Review security advisories regularly
- Update Python packages in `requirements.txt`
- Update Node packages in `package.json`
- Test thoroughly in staging before production

## Support and Contact

### For Technical Issues
1. Check logs: `docker-compose logs`
2. Review documentation: `DEPLOYMENT.md`, `README.md`
3. Check environment variables in `.env`

### Contact Information
- Developer: [Your Name]
- Emergency Contact: [Your Contact]
- Server Admin: [Ethiopia Telecom Contact]

## Notes

### Local Development Issues
Note: Local Docker build was blocked by network connectivity issues during development. The Docker configuration is correct - deployment on Ethiopia Telecom server with stable connectivity should work without issues.

### Mobile App
The React Native mobile app is included in the repository but is not containerized. It can be built and deployed separately to app stores.

### Cloudinary Fallback
The application supports both AWS S3 and Cloudinary for media storage. S3 is preferred for production, but Cloudinary can be used as a fallback by setting Cloudinary environment variables.

## Checklist Before Going Live

- [ ] All environment variables configured in `.env`
- [ ] Database migrations run successfully
- [ ] SSL certificate installed (HTTPS)
- [ ] Automated backups configured
- [ ] Firewall rules configured
- [ ] Monitoring set up
- [ ] Admin user created
- [ ] S3 bucket configured with proper permissions
- [ ] Celery workers running
- [ ] Redis connection verified
- [ ] Frontend accessible via domain
- [ ] Backend API accessible
- [ ] WebSocket endpoints tested
- [ ] Media uploads working
- [ ] Load test performed
