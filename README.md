# Flipstar - Social Media Application

A full-stack social media application with real-time messaging, deployed on Ethiopia Telecom server using Docker containers.


## Features

### Core Features
- **User Authentication** - Registration, login, profile management
- **Feed System** - Create and view posts with images and videos
- **Reels** - Short-form video content
- **Campaigns** - Daily, weekly, monthly, and grand campaigns with voting
- **Gamification** - Coins, gifts, daily streaks, leaderboards
- **Messaging** - Real-time chat with delivery tracking
- **Notifications** - Real-time notifications for interactions
- **Gift System** - Send virtual gifts with purchased coins

### Messaging Features (Enhanced)
- **Real-time WebSocket** - Django Channels for instant messaging
- **Message Delivery Lifecycle** - Sending → Sent → Delivered → Read
- **Presence Tracking** - Online/offline status with Redis
- **Typing Indicators** - Real-time typing status with 3-second TTL
- **Optimistic UI** - Instant message display with async sync
- **UUID-based Messages** - Prevent duplicates on retry
- **Async Media Processing** - Celery workers for image/video optimization

## Technology Stack

### Backend
- **Framework**: Django 4.2.16
- **API**: Django REST Framework 3.15.2
- **Real-time**: Django Channels 4.0.0
- **Task Queue**: Celery 5.3.4
- **Database**: PostgreSQL 15
- **Cache/Queue**: Redis 7
- **Storage**: AWS S3 (with Cloudinary fallback)

### Frontend (Web)
- **Framework**: React 18
- **Build Tool**: Vite 4.3.9
- **Server**: Nginx
- **Icons**: Lucide React

### Frontend (Mobile)
- **Framework**: React Native
- **Navigation**: React Navigation
- **State**: React Context

### Infrastructure
- **Containerization**: Docker & Docker Compose
- **Deployment**: Ethiopia Telecom Server
- **CI/CD**: Shell scripts for deployment

## Project Structure

```
flipstar/
├── backend/                 # Django backend
│   ├── api/                # Django app
│   │   ├── consumers.py    # WebSocket consumers
│   │   ├── models_messaging.py  # Messaging models
│   │   ├── services/       # Business logic
│   │   │   └── presence_service.py  # Presence tracking
│   │   ├── tasks.py        # Celery tasks
│   │   └── celery.py       # Celery configuration
│   ├── config/             # Django settings
│   │   ├── settings.py     # Main settings
│   │   ├── asgi.py         # ASGI config for Channels
│   │   └── routing.py      # WebSocket routing
│   ├── Dockerfile          # Backend container
│   ├── Dockerfile.celery   # Celery worker container
│   └── requirements.txt    # Python dependencies
├── frontend/               # React web frontend
│   ├── src/                # React components
│   ├── Dockerfile          # Frontend container
│   ├── nginx.conf          # Nginx configuration
│   └── package.json        # Node dependencies
├── mobile-app/             # React Native mobile app
│   └── src/                # React Native screens
├── docker-compose.yml      # Multi-container orchestration
├── deploy.sh               # Deployment script
├── setup.sh                # Initial setup script
├── backup.sh               # Database backup script
├── env.production.example # Environment variables template
└── DEPLOYMENT.md           # Deployment guide
```

## Quick Start

### Local Development

1. **Clone the repository**
```bash
git clone <repository-url>
cd flipstar
```

2. **Configure environment variables**
```bash
cp env.production.example .env
# Edit .env with your configuration
```

3. **Start services with Docker Compose**
```bash
docker-compose up -d
```

4. **Run database migrations**
```bash
docker-compose exec backend python manage.py migrate
```

5. **Create superuser**
```bash
docker-compose exec backend python manage.py createsuperuser
```

6. **Access the application**
- Frontend: http://localhost
- Backend API: http://localhost:8000
- Admin Panel: http://localhost:8000/admin

### Ethiopia Telecom Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions.

## API Endpoints

### Authentication
- `POST /api/auth/register/` - User registration
- `POST /api/auth/login/` - User login
- `POST /api/auth/logout/` - User logout

### Messaging (WebSocket)
- `ws://host/ws/chat/<conversation_id>/` - Real-time chat
- `ws://host/ws/presence/` - Presence tracking

### Messaging (REST)
- `GET /api/messages/conversations/` - List conversations
- `POST /api/messages/conversations/` - Create conversation
- `GET /api/messages/conversations/<id>/messages/` - List messages
- `POST /api/messages/conversations/<id>/messages/` - Send message
- `POST /api/messages/conversations/<id>/read/` - Mark as read

### Posts
- `GET /api/posts/` - List posts
- `POST /api/posts/` - Create post
- `GET /api/posts/<id>/` - Get post details
- `POST /api/posts/<id>/like/` - Like post
- `POST /api/posts/<id>/comment/` - Comment on post

### Campaigns
- `GET /api/campaigns/` - List campaigns
- `GET /api/campaigns/<id>/` - Campaign details
- `POST /api/campaigns/<id>/vote/` - Vote for campaign

### Gamification
- `GET /api/gamification/status/` - User gamification status
- `POST /api/gifts/send/` - Send gift
- `GET /api/gamification/gifts/history/` - Gift history

## WebSocket Events

### Chat Events
- `message` - New message
- `typing_indicator` - User typing status
- `user_joined` - User joined conversation
- `user_left` - User left conversation
- `message_status_update` - Message delivery status update

### Presence Events
- `user_online` - User came online
- `user_offline` - User went offline

## Environment Variables

### Required
```env
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=your-domain.com
DB_PASSWORD=your-database-password
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_STORAGE_BUCKET_NAME=your-s3-bucket-name
```

### Optional
```env
CLOUDINARY_CLOUD_NAME=your-cloudinary-name
CLOUDINARY_API_KEY=your-cloudinary-key
CLOUDINARY_API_SECRET=your-cloudinary-secret
```

## Database Schema

### Key Models

**User**
- Extended Django User model with profile
- Fields: bio, profile_photo, allow_messages, is_private

**Conversation**
- participants (ManyToMany)
- created_at
- last_message_at

**Message**
- uuid (UUID)
- conversation (ForeignKey)
- sender (ForeignKey)
- text (TextField)
- media (FileField)
- delivery_status (Enum: sending, sent, delivered, read)
- delivered_at (DateTime)
- read_at (DateTime)

**Campaign**
- title
- description
- campaign_type (daily, weekly, monthly, grand)
- start_date
- end_date
- voting_enabled

## Development

### Running Tests
```bash
docker-compose exec backend python manage.py test
```

### Creating Migrations
```bash
docker-compose exec backend python manage.py makemigrations
docker-compose exec backend python manage.py migrate
```

### Accessing Django Shell
```bash
docker-compose exec backend python manage.py shell
```

## Performance

### Optimization Techniques
- Redis caching for frequently accessed data
- Database indexes on foreign keys and frequently queried fields
- Async task processing with Celery
- Media optimization with FFmpeg and Sharp
- CDN integration for static assets
- WebSocket for real-time updates (no polling)

### Monitoring
- Container health checks
- Database connection pooling
- Redis memory monitoring
- Celery task queue depth
- API response times

## Security

### Implemented
- Token-based authentication
- CORS configuration
- SQL injection prevention (Django ORM)
- XSS protection (Django templates)
- CSRF protection
- Environment variable secrets
- S3 bucket policies

### Recommendations
- Enable HTTPS in production
- Use secrets management service
- Implement rate limiting
- Add input validation
- Regular security audits

## Contributing

1. Fork the repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Create Pull Request

## License

Proprietary - All rights reserved

## Support

For deployment issues, see [DEPLOYMENT.md](DEPLOYMENT.md).

For feature requests or bug reports, contact the development team.
