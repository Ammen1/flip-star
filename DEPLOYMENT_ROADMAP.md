# Flipstar Production Deployment Roadmap
## Ethiopia Telecom Server Deployment

**Document Version:** 1.0  
**Target Server:** Ethiopia Telecom  
**Deployment Method:** Docker Compose  
**Last Updated:** May 4, 2026


---

## Table of Contents
1. [Overview](#overview)
2. [Server Requirements](#server-requirements)
3. [Pre-Deployment Checklist](#pre-deployment-checklist)
4. [Configuration Changes Required](#configuration-changes-required)
5. [DevOps Responsibilities](#devops-responsibilities)
6. [Development Team Responsibilities](#development-team-responsibilities)
7. [Step-by-Step Deployment Process](#step-by-step-deployment-process)
8. [Post-Deployment Verification](#post-deployment-verification)
9. [Maintenance & Monitoring](#maintenance--monitoring)
10. [Troubleshooting Guide](#troubleshooting-guide)

---

## Overview

Flipstar is a full-stack social media application with the following components:
- **Backend:** Django REST Framework with Django Channels (WebSocket)
- **Frontend:** React with Vite, served by Nginx
- **Database:** PostgreSQL 15
- **Cache/Queue:** Redis 7 for Celery and Django Channels
- **Async Processing:** Celery workers and beat scheduler
- **Media Storage:** AWS S3 (with Cloudinary fallback)
- **Mobile App:** React Native/Expo

---

## Server Requirements

### Hardware Requirements
- **CPU:** Minimum 4 cores (recommended: 8 cores)
- **RAM:** Minimum 8GB (recommended: 16GB)
- **Storage:** Minimum 100GB (recommended: 200GB SSD)
- **Network:** Stable internet connection with sufficient bandwidth

### Software Requirements
- **Operating System:** Ubuntu 20.04+ or CentOS 7+
- **Docker:** Version 20.10+
- **Docker Compose:** Version 2.0+
- **Python:** 3.11+ (via Docker)
- **Node.js:** 18+ (via Docker)
- **Open Ports:**
  - 80 (HTTP) - Frontend
  - 443 (HTTPS) - SSL/TLS
  - 22 (SSH) - Restricted to admin IPs
  - 8000 (Backend API) - Internal Docker network
  - 5433 (PostgreSQL) - Internal Docker network
  - 6379 (Redis) - Internal Docker network

### External Services Required
- **AWS S3 Bucket:** For media storage
- **Domain Name:** For SSL certificate and production URL
- **SSL Certificate:** Via Let's Encrypt/Certbot

---

## Pre-Deployment Checklist

### DevOps Checklist
- [ ] Server access credentials obtained
- [ ] Server hardware meets requirements
- [ ] Docker and Docker Compose installed on server
- [ ] Firewall configured with required ports
- [ ] Domain name pointed to server IP
- [ ] AWS S3 bucket created and configured
- [ ] AWS IAM credentials with S3 access created
- [ ] SSL certificate ready (or certbot installed)

### Development Team Checklist
- [ ] All placeholder values identified and documented
- [ ] Production environment variables prepared
- [ ] Database migrations tested locally
- [ ] Static files collected locally
- [ ] AWS S3 credentials provided to DevOps
- [ ] Production domain name provided to DevOps
- [ ] Mobile app production build prepared
- [ ] Code reviewed and tested

---

## Configuration Changes Required

### 1. Environment Variables (.env file)

**File Location:** `flipstar/.env`  
**Action Required:** Development team provides values, DevOps configures

```env
# ===== CRITICAL - MUST CHANGE =====
SECRET_KEY=your-secret-key-here-change-in-production
DB_PASSWORD=your-secure-db-password-here
ADMIN_PASSWORD=your-admin-password-here

# ===== AWS S3 Configuration =====
AWS_ACCESS_KEY_ID=your-aws-access-key-id
AWS_SECRET_ACCESS_KEY=your-aws-secret-access-key
AWS_STORAGE_BUCKET_NAME=flipstar-media
AWS_S3_REGION_NAME=us-east-1

# ===== Production Settings =====
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com,localhost
CORS_ALLOWED_ORIGINS=https://your-domain.com,https://www.your-domain.com

# ===== Database (Docker Compose - Internal) =====
DB_NAME=flipstar_db
DB_USER=flipstar_user
DB_HOST=postgres
DB_PORT=5432

# ===== Redis (Docker Compose - Internal) =====
REDIS_HOST=redis
REDIS_PORT=6379

# ===== Cloudinary (Optional - Legacy) =====
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

### 2. Backend Configuration Changes

**File:** `backend/config/settings.py`

#### Changes Required by Development Team:

**Line 22-23:** Remove local network IPs
```python
# BEFORE:
ALLOWED_HOSTS.append('192.168.1.8')
ALLOWED_HOSTS.append('10.0.2.2')

# AFTER:
# REMOVE THESE LINES - Not needed for production
```

**Lines 49-55:** Update CORS allowed origins
```python
# BEFORE:
CORS_ALLOWED_ORIGINS = [
    'https://postworqq.vercel.app',
    'https://postworq.onrender.com',
    'http://localhost:3000',
    'http://localhost:5173',
    'http://localhost:5174',
]

# AFTER:
CORS_ALLOWED_ORIGINS = [
    'https://your-domain.com',
    'https://www.your-domain.com',
]
```

**Lines 288-296:** Update CORS origins (duplicate section)
```python
# BEFORE:
CORS_ALLOWED_ORIGINS = [
    "https://postworqq.vercel.app",
    "https://postworq.onrender.com", 
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

# AFTER:
CORS_ALLOWED_ORIGINS = [
    "https://your-domain.com",
    "https://www.your-domain.com",
]
```

**Lines 13-16:** Remove Render-specific ALLOWED_HOSTS
```python
# BEFORE:
if 'postworq.onrender.com' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('postworq.onrender.com')
if '.onrender.com' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('.onrender.com')

# AFTER:
# REMOVE THESE LINES - Not needed for Ethiopia Telecom deployment
```

### 3. Frontend Configuration Changes

**File:** `frontend/config.js`

#### Changes Required by Development Team:

**Line 13:** Update production API URL
```javascript
// BEFORE:
API_BASE_URL: 'https://postworq.onrender.com/api', // Your actual backend URL

// AFTER:
API_BASE_URL: 'https://your-domain.com/api', // Production backend URL
```

**Line 24:** Update fallback URL
```javascript
// BEFORE:
API_BASE_URL: 'https://postworq.onrender.com/api', // Fallback

# AFTER:
API_BASE_URL: 'https://your-domain.com/api', // Production fallback
```

### 4. Mobile App Configuration Changes

**File:** `mobile-app/src/config.js`

#### Changes Required by Development Team:

**Line 3:** Update production API URL
```javascript
// BEFORE:
API_BASE_URL: 'http://192.168.1.8:8000/api',  // Physical phone via WiFi

// AFTER:
API_BASE_URL: 'https://your-domain.com/api',  // Production server
```

### 5. Docker Compose Configuration

**File:** `docker-compose.yml`

#### Changes Required by DevOps:

**Line 15:** PostgreSQL port (optional - for external access)
```yaml
# CURRENT:
ports:
  - "5433:5432"

# KEEP AS IS - This maps to host port 5433 for external access if needed
# Internal containers use port 5432
```

**No other changes required** - Docker Compose uses environment variables from `.env`

### 6. Nginx Configuration

**File:** `frontend/nginx.conf`

#### Changes Required by Development Team:

**Line 10:** Update server name (optional - for SSL)
```nginx
# BEFORE:
server_name _;

# AFTER (if using SSL):
server_name your-domain.com www.your-domain.com;
```

**No other changes required** - Nginx proxies to backend container correctly

---

## DevOps Responsibilities

### Phase 1: Server Preparation (Before Code Handoff)

1. **Server Setup**
   - Provision server on Ethiopia Telecom infrastructure
   - Install Ubuntu 20.04+ or CentOS 7+
   - Update system packages: `sudo apt update && sudo apt upgrade -y`
   - Create dedicated user for deployment: `sudo adduser flipstar`
   - Add user to docker group: `sudo usermod -aG docker flipstar`

2. **Docker Installation**
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   docker --version  # Verify installation
   ```

3. **Docker Compose Installation**
   ```bash
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   docker-compose --version  # Verify installation
   ```

4. **Firewall Configuration**
   ```bash
   # Allow HTTP
   sudo ufw allow 80/tcp
   # Allow HTTPS
   sudo ufw allow 443/tcp
   # Allow SSH (restrict to admin IPs)
   sudo ufw allow from YOUR_ADMIN_IP to any port 22
   # Enable firewall
   sudo ufw enable
   ```

5. **Domain Configuration**
   - Point domain A record to server IP address
   - Verify DNS propagation: `nslookup your-domain.com`

6. **SSL Certificate Setup**
   ```bash
   # Install certbot
   sudo apt-get install certbot python3-certbot-nginx -y
   
   # Get SSL certificate (after nginx is running)
   sudo certbot --nginx -d your-domain.com -d www.your-domain.com
   
   # Test auto-renewal
   sudo certbot renew --dry-run
   ```

### Phase 2: Code Deployment (After Code Handoff)

1. **Receive Code Package**
   - Receive `flipstar` folder from development team
   - Verify folder structure is intact
   - Check for all required files: docker-compose.yml, .env, etc.

2. **Upload to Server**
   ```bash
   # Upload via SCP (from local machine)
   scp -r flipstar user@ethiotelecom-server:/home/flipstar/
   
   # Or via SFTP/FTP
   ```

3. **Directory Setup**
   ```bash
   ssh user@ethiotelecom-server
   cd /home/flipstar/flipstar
   ls -la  # Verify files
   ```

4. **Environment Configuration**
   ```bash
   # Copy example env file
   cp env.production.example .env
   
   # Edit with production values (provided by dev team)
   nano .env
   ```

5. **Run Setup Script**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

6. **Deploy Application**
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

### Phase 3: Post-Deployment

1. **Container Verification**
   ```bash
   docker-compose ps
   # All containers should show "Up" status
   ```

2. **Log Monitoring**
   ```bash
   # Check all logs
   docker-compose logs -f
   
   # Check specific service logs
   docker-compose logs backend
   docker-compose logs frontend
   docker-compose logs postgres
   docker-compose logs redis
   docker-compose logs celery_worker
   ```

3. **Database Verification**
   ```bash
   # Test database connection
   docker-compose exec backend python manage.py dbshell
   # Exit with \q
   ```

4. **SSL Configuration**
   ```bash
   # Configure SSL with certbot if not done earlier
   sudo certbot --nginx -d your-domain.com -d www.your-domain.com
   ```

5. **Backup Setup**
   ```bash
   # Configure automated backups
   chmod +x backup.sh
   # Add to crontab for daily backups
   crontab -e
   # Add: 0 2 * * * /home/flipstar/flipstar/backup.sh
   ```

6. **Monitoring Setup**
   - Set up log rotation
   - Configure disk space monitoring
   - Set up container health checks
   - Configure alerting for container failures

### Phase 4: Ongoing Maintenance

1. **Daily Tasks**
   - Check container status: `docker-compose ps`
   - Review error logs: `docker-compose logs --tail=100`
   - Monitor disk space: `df -h`
   - Verify backup completion

2. **Weekly Tasks**
   - Review system logs
   - Check for security updates
   - Review container resource usage
   - Test backup restoration

3. **Monthly Tasks**
   - Update Docker images: `docker-compose pull`
   - Rebuild containers: `docker-compose up -d --build`
   - Review and rotate secrets
   - Performance tuning

---

## Development Team Responsibilities

### Phase 1: Pre-Deployment Preparation

1. **Code Review & Testing**
   - Review all code for production readiness
   - Test all features locally
   - Test database migrations
   - Verify static file collection

2. **Configuration Updates**
   - Update `backend/config/settings.py`:
     - Remove local network IPs (lines 22-23)
     - Update CORS origins (lines 49-55, 288-296)
     - Remove Render-specific ALLOWED_HOSTS (lines 13-16)
   
   - Update `frontend/config.js`:
     - Change API_BASE_URL to production domain (line 13)
     - Change fallback URL to production domain (line 24)
   
   - Update `mobile-app/src/config.js`:
     - Change API_BASE_URL to production domain (line 3)

3. **Environment Variables Preparation**
   - Generate strong SECRET_KEY
   - Generate strong DB_PASSWORD
   - Generate strong ADMIN_PASSWORD
   - Obtain AWS S3 credentials
   - Determine production domain name
   - Create production `.env` file template

4. **AWS S3 Setup**
   - Create S3 bucket: `flipstar-media`
   - Configure bucket policy for public read access
   - Set up CORS on S3 bucket
   - Create IAM user with S3 access
   - Generate access keys
   - Test S3 connectivity

5. **Database Preparation**
   - Create production database schema
   - Run all migrations: `python manage.py migrate`
   - Create initial data (if required)
   - Test backup/restore procedures

6. **Static Files**
   - Collect static files: `python manage.py collectstatic --noinput`
   - Verify static files are properly organized
   - Test static file serving

7. **Mobile App Build**
   - Update mobile app config with production URL
   - Build production APK/IPA
   - Test mobile app with production backend
   - Prepare app store submission

### Phase 2: Code Handoff

1. **Package Preparation**
   - Create clean `flipstar` folder
   - Remove unnecessary files (.git, node_modules, __pycache__)
   - Verify all configuration files are included
   - Create deployment checklist

2. **Documentation**
   - Provide `.env` file with all required values
   - Document any special configurations
   - Provide AWS S3 credentials securely
   - Provide admin credentials securely

3. **Handoff Meeting**
   - Walk through deployment process with DevOps
   - Explain configuration changes
   - Provide troubleshooting guide
   - Establish communication channels

### Phase 3: Post-Deployment Support

1. **Deployment Verification**
   - Test frontend URL: `https://your-domain.com`
   - Test backend API: `https://your-domain.com/api/`
   - Test WebSocket connection
   - Test file uploads to S3
   - Test authentication flow

2. **Bug Fixes**
   - Monitor for deployment issues
   - Fix critical bugs immediately
   - Provide hotfixes if needed

3. **Performance Tuning**
   - Monitor application performance
   - Optimize slow queries
   - Adjust Celery worker count
   - Tune Redis configuration

4. **Documentation Updates**
   - Update deployment documentation
   - Document any issues encountered
   - Update troubleshooting guide

---

## Step-by-Step Deployment Process

### Step 1: Development Team - Prepare Code (1-2 days)

1. Update all configuration files with production values
2. Test application locally with production configuration
3. Run database migrations
4. Collect static files
5. Create production `.env` file
6. Package `flipstar` folder for deployment

**Deliverables:**
- `flipstar` folder with all configuration updates
- `.env` file with production values
- AWS S3 credentials
- Deployment checklist

### Step 2: DevOps - Prepare Server (1 day)

1. Provision server on Ethiopia Telecom
2. Install Docker and Docker Compose
3. Configure firewall
4. Point domain to server IP
5. Install certbot for SSL

**Deliverables:**
- Server ready for deployment
- Domain pointing to server
- SSL certificate ready

### Step 3: Handoff Meeting (1 hour)

1. Development team hands off code package
2. DevOps receives code package
3. Review configuration changes
4. Verify environment variables
5. Establish communication protocol

**Deliverables:**
- Code uploaded to server
- Environment variables configured
- Deployment plan confirmed

### Step 4: DevOps - Deploy Application (1-2 hours)

1. Upload `flipstar` folder to server
2. Navigate to flipstar directory
3. Run setup script: `./setup.sh`
4. Edit `.env` file with production values
5. Run deployment script: `./deploy.sh`
6. Monitor deployment logs
7. Verify all containers are running

**Deliverables:**
- Application deployed and running
- All containers healthy
- Logs showing no errors

### Step 5: Development Team - Verify Deployment (1-2 hours)

1. Access frontend URL: `https://your-domain.com`
2. Test user registration
3. Test user login
4. Test post creation
5. Test file uploads
6. Test WebSocket functionality
7. Test mobile app connection
8. Verify CORS settings

**Deliverables:**
- All features tested and working
- Bug report (if any issues)

### Step 6: DevOps - Configure SSL (30 minutes)

1. Run certbot to obtain SSL certificate
2. Configure nginx for HTTPS
3. Test SSL certificate
4. Configure auto-renewal
5. Redirect HTTP to HTTPS

**Deliverables:**
- SSL certificate installed
- HTTPS working
- Auto-renewal configured

### Step 7: DevOps - Setup Backups (30 minutes)

1. Configure backup script
2. Test backup procedure
3. Setup cron job for daily backups
4. Test restore procedure
5. Configure S3 backup upload

**Deliverables:**
- Automated backups configured
- Backup retention policy set
- Restore procedure tested

### Step 8: DevOps - Setup Monitoring (1 hour)

1. Configure log rotation
2. Setup disk space monitoring
3. Configure container health checks
4. Setup alerting for failures
5. Configure performance monitoring

**Deliverables:**
- Monitoring system active
- Alerts configured
- Performance metrics collected

### Step 9: Final Verification (1 hour)

1. Full end-to-end testing
2. Load testing (if required)
3. Security scan
4. Performance baseline
5. Documentation handoff

**Deliverables:**
- Production-ready application
- Monitoring dashboard
- Support documentation

---

## Post-Deployment Verification

### Frontend Verification
- [ ] Frontend loads at `https://your-domain.com`
- [ ] All pages render correctly
- [ ] No console errors in browser
- [ ] Images and static files load
- [ ] Responsive design works

### Backend Verification
- [ ] Backend API responds at `https://your-domain.com/api/`
- [ ] Authentication endpoints work
- [ ] Database queries execute
- [ ] File uploads to S3 work
- [ ] CORS headers are correct

### WebSocket Verification
- [ ] WebSocket connection established
- [ ] Real-time messages work
- [ ] Connection stays stable
- [ ] Reconnection logic works

### Mobile App Verification
- [ ] Mobile app connects to production API
- [ ] Authentication works
- [ ] File uploads work
- [ ] Real-time features work
- [ ] Push notifications (if configured)

### Database Verification
- [ ] PostgreSQL container running
- [ ] Database migrations applied
- [ ] Data persists after restart
- [ ] Backup procedure works

### Redis Verification
- [ ] Redis container running
- [ ] Celery workers connected
- [ ] Cache operations work
- [ ] Channel layer working

### Security Verification
- [ ] SSL certificate valid
- [ ] HTTPS redirects work
- [ ] DEBUG=False in production
- [ ] SECRET_KEY is secure
- [ ] Database password is secure
- [ ] AWS credentials are secure

---

## Maintenance & Monitoring

### Daily Monitoring Checklist

**DevOps:**
- [ ] Check container status: `docker-compose ps`
- [ ] Check disk space: `df -h`
- [ ] Check memory usage: `free -h`
- [ ] Review error logs: `docker-compose logs --tail=50`
- [ ] Verify backup completed

**Development Team:**
- [ ] Monitor application performance
- [ ] Review user feedback
- [ ] Check for bug reports
- [ ] Plan upcoming features

### Weekly Maintenance

**DevOps:**
- [ ] Review all logs for warnings
- [ ] Check container resource usage
- [ ] Test backup restoration
- [ ] Review security updates
- [ ] Update Docker images if needed

**Development Team:**
- [ ] Review analytics
- [ ] Plan feature updates
- [ ] Address user feedback
- [ ] Code review for new features

### Monthly Maintenance

**DevOps:**
- [ ] Update base Docker images
- [ ] Rebuild containers: `docker-compose up -d --build`
- [ ] Review and rotate secrets
- [ ] Performance tuning
- [ ] Security audit

**Development Team:**
- [ ] Deploy feature updates
- [ ] Database migrations (if needed)
- [ ] Performance optimization
- [ ] Security patches

### Update Deployment Process

**For Code Updates:**
```bash
# 1. DevOps pulls latest code
cd /home/flipstar/flipstar
git pull origin main  # Or receive updated files from dev team

# 2. Rebuild affected services
docker-compose up -d --build backend frontend

# 3. Run database migrations
docker-compose exec backend python manage.py migrate

# 4. Collect static files
docker-compose exec backend python manage.py collectstatic --noinput

# 5. Restart services
docker-compose restart backend frontend celery_worker celery_beat

# 6. Verify deployment
docker-compose ps
docker-compose logs -f
```

---

## Troubleshooting Guide

### Container Won't Start

**Symptoms:** `docker-compose ps` shows containers as "Exited" or "Restarting"

**Solutions:**
1. Check logs: `docker-compose logs [service_name]`
2. Check environment variables: `cat .env`
3. Verify Docker daemon running: `sudo systemctl status docker`
4. Check disk space: `df -h`
5. Restart Docker: `sudo systemctl restart docker`

### Database Connection Errors

**Symptoms:** Backend logs show "could not connect to server"

**Solutions:**
1. Check PostgreSQL container: `docker-compose ps postgres`
2. Check PostgreSQL logs: `docker-compose logs postgres`
3. Verify database credentials in `.env`
4. Test connection: `docker-compose exec backend python manage.py dbshell`
5. Restart database: `docker-compose restart postgres`

### Redis Connection Errors

**Symptoms:** Celery workers fail to connect

**Solutions:**
1. Check Redis container: `docker-compose ps redis`
2. Check Redis logs: `docker-compose logs redis`
3. Test Redis: `docker-compose exec redis redis-cli ping`
4. Restart Redis: `docker-compose restart redis`

### File Upload Failures

**Symptoms:** Users can't upload files

**Solutions:**
1. Verify AWS credentials in `.env`
2. Check S3 bucket permissions
3. Test S3 connectivity: `docker-compose exec backend python -c "import boto3; print(boto3.client('s3').list_buckets())"`
4. Check bucket CORS configuration
5. Verify bucket region matches `AWS_S3_REGION_NAME`

### CORS Errors

**Symptoms:** Browser shows CORS errors in console

**Solutions:**
1. Check `CORS_ALLOWED_ORIGINS` in `.env`
2. Verify backend settings.py CORS configuration
3. Check nginx CORS headers
4. Restart backend: `docker-compose restart backend`

### SSL Certificate Issues

**Symptoms:** HTTPS not working, certificate errors

**Solutions:**
1. Check certificate expiry: `sudo certbot certificates`
2. Renew certificate: `sudo certbot renew`
3. Reconfigure nginx: `sudo certbot --nginx -d your-domain.com`
4. Check nginx configuration: `sudo nginx -t`
5. Restart nginx: `sudo systemctl restart nginx`

### Out of Disk Space

**Symptoms:** Containers fail to start, write errors

**Solutions:**
1. Check disk space: `df -h`
2. Clean Docker images: `docker system prune -a`
3. Clean old backups
4. Expand disk if needed
5. Configure log rotation

### High Memory Usage

**Symptoms:** Server becomes slow, OOM errors

**Solutions:**
1. Check memory usage: `free -h`
2. Check container memory: `docker stats`
3. Reduce Celery worker count in docker-compose.yml
4. Add swap space
5. Upgrade server RAM

### WebSocket Connection Failures

**Symptoms:** Real-time features not working

**Solutions:**
1. Check Redis channel layer: `docker-compose logs backend | grep channel`
2. Verify nginx WebSocket proxy configuration
3. Check firewall allows WebSocket connections
4. Test WebSocket: `wscat -c ws://your-domain.com/ws/`
5. Restart backend and Redis

### Backup Failures

**Symptoms:** Backup script fails, no backup files

**Solutions:**
1. Check backup script permissions: `ls -la backup.sh`
2. Test backup manually: `./backup.sh`
3. Check S3 upload permissions
4. Verify cron job: `crontab -l`
5. Check disk space for backup storage

---

## Emergency Procedures

### Application Down

1. **Immediate Actions:**
   - Check container status: `docker-compose ps`
   - Check logs: `docker-compose logs`
   - Restart all services: `docker-compose restart`

2. **If Restart Fails:**
   - Stop all containers: `docker-compose down`
   - Start all containers: `docker-compose up -d`
   - Monitor logs: `docker-compose logs -f`

3. **If Still Down:**
   - Restore from backup
   - Contact development team
   - Escalate to management

### Data Loss

1. **Immediate Actions:**
   - Stop all containers: `docker-compose down`
   - Do not write any data
   - Contact development team

2. **Restore Procedure:**
   ```bash
   # Download latest backup from S3
   aws s3 cp s3://flipstar-media/backups/latest.sql.gz .
   
   # Decompress
   gunzip latest.sql.gz
   
   # Restore database
   docker-compose up -d postgres
   docker-compose exec -T postgres psql -U flipstar_user flipstar_db < latest.sql
   
   # Start all services
   docker-compose up -d
   ```

### Security Breach

1. **Immediate Actions:**
   - Change all passwords
   - Rotate AWS credentials
   - Rotate SECRET_KEY
   - Review access logs
   - Contact security team

2. **Post-Incident:**
   - Audit all configurations
   - Implement additional security measures
   - Document incident
   - Update security procedures

---

## Contact Information

### Development Team
- **Lead Developer:** [Name]
- **Email:** [email]
- **Phone:** [phone]
- **Hours:** [working hours]

### DevOps Team
- **DevOps Engineer:** [Name]
- **Email:** [email]
- **Phone:** [phone]
- **Hours:** [working hours]

### Emergency Contacts
- **On-Call DevOps:** [Name] - [phone]
- **On-Call Developer:** [Name] - [phone]

---

## Appendix

### A. Useful Commands

```bash
# Container Management
docker-compose ps                    # List containers
docker-compose logs [service]        # View logs
docker-compose restart [service]     # Restart service
docker-compose stop [service]        # Stop service
docker-compose start [service]       # Start service
docker-compose down                  # Stop all containers
docker-compose up -d                 # Start all containers

# Database Operations
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py createsuperuser
docker-compose exec backend python manage.py collectstatic
docker-compose exec backend python manage.py shell

# Redis Operations
docker-compose exec redis redis-cli ping
docker-compose exec redis redis-cli FLUSHALL

# Backup Operations
./backup.sh                          # Run backup
docker-compose exec postgres pg_dump -U flipstar_user flipstar_db > backup.sql

# System Operations
docker system prune -a               # Clean Docker
df -h                                # Check disk space
free -h                              # Check memory
docker stats                         # Container resource usage
```

### B. File Locations

```
flipstar/
├── docker-compose.yml              # Docker orchestration
├── .env                            # Environment variables
├── env.production.example          # Environment template
├── deploy.sh                       # Deployment script
├── setup.sh                        # Setup script
├── backup.sh                       # Backup script
├── backend/
│   ├── config/
│   │   ├── settings.py            # Django settings (UPDATE REQUIRED)
│   │   └── production_settings.py # Production settings
│   ├── Dockerfile                 # Backend container
│   └── Dockerfile.celery          # Celery container
├── frontend/
│   ├── config.js                  # Frontend config (UPDATE REQUIRED)
│   ├── nginx.conf                 # Nginx config
│   └── Dockerfile                 # Frontend container
└── mobile-app/
    └── src/
        └── config.js              # Mobile app config (UPDATE REQUIRED)
```

### C. Port Mappings

| Service | Container Port | Host Port | Access |
|---------|---------------|-----------|--------|
| Frontend (Nginx) | 80 | 80 | Public |
| Backend (Django) | 8000 | 8000 | Internal |
| PostgreSQL | 5432 | 5433 | Internal |
| Redis | 6379 | 6379 | Internal |

### D. Environment Variables Reference

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| SECRET_KEY | Django secret key | random-50-char-string | Yes |
| DEBUG | Debug mode | False | Yes |
| ALLOWED_HOSTS | Allowed domains | your-domain.com | Yes |
| DB_PASSWORD | Database password | secure-password | Yes |
| ADMIN_PASSWORD | Admin password | admin-password | Yes |
| AWS_ACCESS_KEY_ID | AWS access key | AKIA... | Yes |
| AWS_SECRET_ACCESS_KEY | AWS secret key | abc123... | Yes |
| AWS_STORAGE_BUCKET_NAME | S3 bucket name | flipstar-media | Yes |
| AWS_S3_REGION_NAME | S3 region | us-east-1 | Yes |
| CORS_ALLOWED_ORIGINS | CORS origins | https://your-domain.com | Yes |
| REDIS_HOST | Redis host | redis | No (default) |
| REDIS_PORT | Redis port | 6379 | No (default) |
| DB_HOST | Database host | postgres | No (default) |
| DB_PORT | Database port | 5432 | No (default) |

---

**End of Deployment Roadmap**

For questions or issues, refer to the Troubleshooting Guide or contact the Development/DevOps teams.
