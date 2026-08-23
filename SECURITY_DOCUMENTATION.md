# Flipstar Platform Security Documentation

**Document Version:** 1.0  
**Date:** May 22, 2026  
**Platform:** Flipstar Social Media Application  
**Environment:** Production (UAT)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [API Documentation](#api-documentation)
   - [Authentication Methods](#authentication-methods)
   - [Public APIs](#public-apis)
   - [Admin/Internal APIs](#admininternal-apis)
3. [Mobile Application Security](#mobile-application-security)
4. [Backend Infrastructure Details](#backend-infrastructure-details)
5. [Encryption & Secure Communication Standards](#encryption--secure-communication-standards)
   - [Encryption In Transit](#encryption-in-transit)
   - [Encryption At Rest](#encryption-at-rest)
6. [Third-Party Integrations Security](#third-party-integrations-security)
7. [Compliance & Data Protection](#compliance--data-protection)

---

## Executive Summary

Flipstar is a gamified social media platform deployed on Ethio Telecom cloud infrastructure using Docker containers. The platform implements phone OTP-based authentication via Onevas SMS, SSL/TLS encryption, and integrates with third-party payment services (telebirr, Onevas) for subscription management.

**Key Security Features:**

- Phone OTP-based authentication via Onevas SMS (primary method)
- Token-based authentication (Django REST Framework - underlying mechanism)
- SSL/TLS 1.2 and 1.3 encryption
- PostgreSQL database with SSL connections
- Docker containerized deployment
- Nginx reverse proxy with Let's Encrypt certificates
- Environment variable-based secret management
- React Native mobile application with secure storage
- Gamified social media features with coin-based economy

---

## API Documentation

### Authentication Methods

<<<<<<< HEAD
**JWT Token Authentication:**

```
POST /api/auth/login/
{
  "username": "user@example.com",
  "password": "password"
}

Response:
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": 123,
    "username": "username",
    "email": "user@example.com"
  }
}
```

**Token Usage:**

```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

### Public APIs

**Content APIs:**

- `GET /api/posts/` - List posts with pagination
- `POST /api/posts/create/` - Create new post (authenticated)
- `GET /api/posts/{id}/` - Get post details
- `POST /api/posts/{id}/like/` - Like a post
- `POST /api/posts/{id}/comment/` - Comment on post

**User APIs:**

- `GET /api/users/profile/` - Get user profile
- `PUT /api/users/profile/` - Update profile
- `GET /api/users/{id}/posts/` - Get user posts

**Campaign APIs:**

- `GET /api/campaigns/` - List active campaigns
- `GET /api/campaigns/{id}/` - Campaign details
- `POST /api/campaigns/{id}/enter/` - Join campaign
- `GET /api/campaigns/{id}/leaderboard/` - Campaign leaderboard

### Admin/Internal APIs

**Content Moderation:**

- `POST /api/admin/posts/{id}/moderate/` - Moderate content
- `GET /api/admin/reports/` - Get reported content
- `POST /api/admin/users/{id}/suspend/` - Suspend user

**Coin Management:**

- `POST /api/admin/coins/adjust/` - Adjust user coin balance
- `GET /api/admin/transactions/` - View transaction history
- `POST /api/admin/coins/tax-calculation/` - Calculate taxes

**User Management:**

- `GET /api/admin/users/` - List all users
- `POST /api/admin/users/{id}/verify/` - Verify user KYC
- `PUT /api/admin/users/{id}/role/` - Update user role

## Backend Infrastructure Details

### Server Architecture

**Application Servers:**

- **Web Server:** Nginx (SSL termination, static file serving)
- **Application Server:** Django with Gunicorn/uWSGI
- **Database Server:** PostgreSQL (primary database)
- **Cache Server:** Redis (sessions, caching)

**Service Tiers:**

```
Load Balancer (Nginx)
├── Web Servers (Django)
│   ├── API Endpoints
│   ├── Business Logic
│   └── Authentication
├── Database Servers (PostgreSQL)
│   ├── Primary Database
│   ├── Read Replicas
│   └── Backup Servers
└── Cache Servers (Redis)
    ├── Session Storage
    ├── Application Cache
    └── Message Queue
```

**Note:** Specific IP addresses are not provided in this documentation for security reasons. IP addresses should be obtained from your cloud provider's console or infrastructure documentation.

## Encryption & Security Standards

### In Transit Encryption

**HTTPS/TLS:**

- **Protocol:** TLS 1.2 and 1.3
- **Cipher Suites:** Strong encryption (AES-256)
- **Certificates:** Valid SSL certificates from trusted CA
- **HSTS:** HTTP Strict Transport Security enabled

**API Communication:**

- **REST APIs:** HTTPS only
- **WebSocket:** WSS (Secure WebSocket)
- **File Uploads:** Encrypted transfer
- **Database Connections:** SSL/TLS enabled

### At Rest Encryption

**Database Encryption:**

- **PostgreSQL:** Transparent Data Encryption (TDE)
- **Sensitive Fields:** Column-level encryption
- **Backups:** Encrypted backup files
- **Connection Strings:** Encrypted configuration

**File Storage:**

- **Cloud Storage:** Server-side encryption (AES-256)
- **User Files:** Encrypted at rest
- **Thumbnails:** Encrypted storage
- **CDN:** Secure distribution

**Application Data:**

- **Environment Variables:** Encrypted secrets
- **Configuration Files:** Encrypted storage
- **Logs:** Sensitive data redaction
- **Cache:** Encrypted Redis data

### Security Measures

**Access Control:**

- **Authentication:** JWT tokens with expiration
- **Authorization:** Role-based access control (RBAC)
- **API Rate Limiting:** Prevent abuse
- **Input Validation:** Sanitize all inputs

**Data Protection:**

- **PII Protection:** Personal data encryption
- **GDPR Compliance:** Data handling policies
- **Audit Logging:** All actions logged
- **Data Retention:** Automatic cleanup policies

**Monitoring & Alerting:**

- **Security Events:** Real-time monitoring
- **Failed Logins:** Account lockout
- **Anomaly Detection:** Unusual activity alerts
- **Compliance Reports:** Regular security audits

## Security Best Practices

### Development Security

- Code reviews for security vulnerabilities
- Dependency scanning for known issues
- Secure coding practices training
- Regular penetration testing

### Operational Security

- Regular security updates and patches
- Backup encryption and testing
- Incident response procedures
- Security team training

### Compliance

- Data protection regulations compliance
- Industry security standards
- Third-party security certifications
- Regular compliance audits

---

# **Note:** This documentation is based on the current codebase and architecture. For production deployment, additional security measures and infrastructure details should be implemented based on your specific requirements and compliance needs.

#### Primary Authentication: Phone OTP (Onevas SMS)

**Method:** SMS-based OTP verification via Onevas service  
**Implementation:** Custom OTP service with Onevas integration  
**Status:** Production (Primary authentication method)

**Authentication Flow:**

1. **Send OTP**
   - Endpoint: `POST /api/auth/send-phone-otp/`
   - Request Body:
     ```json
     {
       "phone": "2519******"
     }
     ```
   - Response:
     ```json
     {
       "message": "OTP sent successfully",
       "phone": "2519******"
     }
     ```

2. **Verify OTP**
   - Endpoint: `POST /api/auth/verify-phone-otp/`
   - Request Body:
     ```json
     {
       "phone": "2519******",
       "code": "123456"
     }
     ```
   - Response:
     ```json
     {
       "message": "OTP verified successfully",
       "phone": "2519******"
     }
     ```

3. **Register with Phone**
   - Endpoint: `POST /api/auth/register-with-phone/`
   - Request Body:
     ```json
     {
       "phone": "2519******",
       "username": "string",
       "password": "123456"
     }
     ```
   - Response:
     ```json
     {
       "user": {
         "id": 1,
         "username": "string",
         "phone": "2519******"
       },
       "token": "abcdef1234567890"
     }
     ```

4. **Login with Phone**
   - Endpoint: `POST /api/auth/login-with-phone/`
   - Request Body:
     ```json
     {
       "phone": "2519******",
       "password": "123456"
     }
     ```
   - Response:
     ```json
     {
       "user": {
         "id": 1,
         "username": "string",
         "phone": "2519******"
       },
       "token": "abcdef1234567890"
     }
     ```

**OTP Security:**

- OTP Length: 6 digits
- OTP Expiration: 15 minutes
- Rate Limiting: Implemented
- Phone Number Format: Ethiopian format (251xxxxxxxxx)

#### Token-Based Authentication (Underlying Mechanism)

**Method:** Django REST Framework Token Authentication  
**Standard:** REST Framework Token Authentication (not JWT/OAuth2)  
**Implementation:** `rest_framework.authtoken.models.Token`  
**Status:** Underlying authentication mechanism (not user-facing)

**Token Usage:**

- Header: `Authorization: Token abcdef1234567890`
- Required for all authenticated endpoints
- Generated automatically upon successful registration/login

#### Upcoming Feature: telebirr Authentication

**Method:** telebirr Direct Debit mandate-based authentication  
**Implementation:** SOAP API integration with telebirr  
**Status:** Coming Soon (Not yet deployed)

**Planned Flow:**

- Users with active telebirr subscriptions will be able to login without OTP
- Endpoint: `POST /api/auth/login-with-phone/`
- Will validate phone number against active SMS subscriptions
- Will require 6-digit password

---

### Public APIs

**Note:** The following endpoints are the only ones that do not require an active subscription. All other platform features require an active subscription.

| Category           | Endpoints                                                                                                                                                                                     | Authentication |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| Authentication     | `/api/auth/send-phone-otp/`, `/api/auth/verify-phone-otp/`, `/api/auth/register-with-phone/`, `/api/auth/login-with-phone/`, `/api/auth/forgot-password/`, `/api/auth/forgot-password-phone/` | Public         |
| Subscription Tiers | `/api/subscriptions/tiers/`, `/api/subscriptions/tiers/active/`                                                                                                                               | Public         |
| Coin Packages      | `/api/coins/packages/`                                                                                                                                                                        | Public         |
| Gifts              | `/api/gifts/`                                                                                                                                                                                 | Public         |
| Legal Documents    | `/api/legal/`, `/api/legal/{type}/`                                                                                                                                                           | Public         |
| Wallet Config      | `/api/wallet/config/`                                                                                                                                                                         | Public         |
| Webhooks           | `/api/wallet/telebirr-callback/`, `/api/webhooks/telebirr-direct-debit/`, `/api/onevas/subscription/`, `/api/onevas/unsubscription/`, `/api/onevas/renewal/`, `/api/onevas/stop/`             | Public         |
| Health Check       | `/api/health/`, `/api/health/deep/`                                                                                                                                                           | Public         |
| Push Notifications | `/api/push/public-key/`                                                                                                                                                                       | Public         |

### Subscription Required APIs

All platform features require an active subscription, including:

| Category       | Endpoints                                                                                         |
| -------------- | ------------------------------------------------------------------------------------------------- |
| Content        | `/api/posts/`, `/api/reels/`, `/api/comments/`, `/api/saved/`, `/api/search/`, `/api/categories/` |
| Social         | `/api/follows/`, `/api/blocks/`, `/api/messages/`                                                 |
| Notifications  | `/api/notifications/`, `/api/push/subscribe/`, `/api/push/unsubscribe/`                           |
| Campaigns      | `/api/campaigns/` (all campaign-related endpoints)                                                |
| Subscriptions  | `/api/subscriptions/`, `/api/subscription/` (management endpoints)                                |
| Wallet & Coins | `/api/wallet/`, `/api/coins/` (all wallet and coin operations)                                    |
| Gamification   | `/api/gamification/` (spin wheel, login bonus, check-in, gifts)                                   |
| Boost          | `/api/boost/` (boost campaigns and management)                                                    |
| Direct Debit   | `/api/direct-debit/` (mandate management)                                                         |
| Charging       | `/api/charging/` (on-demand charging)                                                             |
| Explorer       | `/api/explorer/` (trending, hashtags)                                                             |
| Contest        | `/api/scores/`, `/api/leaderboard/`, `/api/eligibility/`                                          |
| Support        | `/api/support/`                                                                                   |
| Reports        | `/api/reports/`                                                                                   |
| Profile        | `/api/profile/`, `/api/profile-photo/`                                                            |
| Settings       | `/api/settings/public/` (Public)                                                                  |

---

### Admin APIs

All admin APIs require authentication and appropriate admin permissions.

| Category                | Endpoints                                                                 |
| ----------------------- | ------------------------------------------------------------------------- |
| User Management         | `/api/admin/dashboard/`, `/api/admin/users/`                              |
| Content Moderation      | `/api/admin/reels/`, `/api/admin/comments/`, `/api/admin/wipe-all-posts/` |
| Report Management       | `/api/admin/reports/`                                                     |
| Subscription Management | `/api/admin/subscriptions/`                                               |
| Coin Management         | `/api/admin/coins/adjust/`, `/api/admin/coins/transactions/`              |
| Platform Settings       | `/api/admin/settings/`, `/api/admin/api-keys/`                            |

---

## Mobile Application Security

### Application Overview

**Platform:** React Native (Expo)  
**Package Name:** com.flipstar.mobile  
**Version:** 1.0.0  
**Environment:** Development (UAT)

### Security Features

#### Secure Storage

**Implementation:** Expo Secure Store  
**Purpose:** Store authentication tokens and sensitive data locally

**Stored Data:**

- Authentication tokens
- User session data
- Sensitive configuration data

#### API Communication

**Base URL:** Configured via environment variables  
**Current Endpoint:** `https://api.uat.flipstar.et/api`  
**Protocol:** HTTPS (TLS 1.2/1.3)

**Authentication:**

- Token-based authentication via HTTP Authorization header
- Format: `Authorization: Token <token>`
- Token stored in Secure Store

#### Network Security

**SSL Pinning:** Not implemented  
**Certificate Validation:** Default OS-level validation

#### Data Protection

**Local Storage:**

- AsyncStorage for non-sensitive data
- Secure Store for sensitive data (tokens)

**Encryption:**

- Expo Secure Store uses platform-specific encryption (Keychain on iOS, Keystore on Android)

#### Third-Party Libraries

**Security-Related Libraries:**

- `expo-secure-store`: Secure storage for sensitive data
- `react-native-safe-area-context`: Safe area handling

#### Build Configuration

**iOS Configuration:**

- Bundle Identifier: `com.flipstar.mobile`
- App Transport Security: Enabled (default)
- Encryption: ITSAppUsesNonExemptEncryption: false

**Android Configuration:**

- Package: `com.flipstar.mobile`
- Network Security Config: Default (HTTPS required)

### Mobile App Security Controls

**Implemented:**

- Secure token storage using Expo Secure Store
- HTTPS-only API communication
- Platform-specific encryption for stored data
- Safe area handling for UI security

**Authentication Flow:**

1. User enters phone number
2. OTP sent via Onevas SMS
3. User verifies OTP
4. Token received from backend
5. Token stored in Secure Store
6. Token sent in Authorization header for all API requests

---

## Backend Infrastructure Details

### Deployment Architecture

**Platform:** Docker containerized deployment  
**Hosting Provider:** Ethio Telecom cloud infrastructure  
**Environment:** UAT (User Acceptance Testing)  
**Domain:** api.uat.flipstar.et

### Infrastructure Components

#### 1. Web Server & Reverse Proxy

**Component:** Nginx  
**Version:** Latest  
**Ports:** 80 (HTTP), 443 (HTTPS)  
**Configuration:** Nginx reverse proxy configuration

**SSL/TLS Configuration:**

- SSL Certificate: Let's Encrypt
- Certificate: Stored securely on server
- Private Key: Stored securely on server
- SSL Protocols: TLSv1.2, TLSv1.3
- Cipher Preference: Server-preferred ciphers
- HTTP to HTTPS Redirect: Enabled

**Proxy Configuration:**

- Backend API: `http://backend:8000` (Docker internal)
- Frontend: `http://frontend:80` (Docker internal)
- Max Upload Size: 100MB
- Proxy Headers: Host, X-Real-IP, X-Forwarded-Proto

#### 2. Application Backend

**Component:** Django REST Framework  
**Python Version:** 3.x  
**Container:** `flipstar_backend`  
**Internal Port:** 8000  
**Exposed Port:** 8000 (Docker network only)

**Key Features:**

- REST API endpoints
- Django Channels for WebSocket support
- Celery for async task processing
- Gunicorn WSGI server

**Dependencies:**

- Django
- Django REST Framework
- Django Channels
- Celery
- Redis
- PostgreSQL adapter
- boto3 (for S3/MinIO)

#### 3. Frontend Application

**Component:** React with Vite  
**Container:** `flipstar_frontend`  
**Internal Port:** 80  
**Exposed Port:** 8080 (Docker network only)

**Served by:** Nginx (static files)  
**Build Process:** Docker build with multi-stage optimization

#### 4. Database Server

**Component:** PostgreSQL  
**Version:** 15-alpine  
**Container:** `flipstar_postgres`  
**Internal Port:** 5432  
**Exposed Port:** 5433 (host mapping)

**Configuration:**

- Database Name: Configured via `DB_NAME` environment variable
- User: Configured via `DB_USER` environment variable
- Password: Configured via `DB_PASSWORD` environment variable
- SSL Mode: `require` (for production/Neon database)
- Connection Pooling: Django default
- Health Check: `pg_isready` command

**Data Persistence:**

- Docker Volume: `postgres_data`
- Mount Path: `/var/lib/postgresql/data`
- Backup Strategy: Custom backup script to S3

#### 5. Cache & Message Broker

**Component:** Redis  
**Version:** 7-alpine  
**Container:** `flipstar_redis`  
**Internal Port:** 6379  
**Exposed Port:** 6379 (host mapping)

**Configuration:**

- Persistence: AOF (Append Only File) enabled
- Data Volume: `redis_data`
- Health Check: `redis-cli ping`
- Uses: Celery broker, Django Channels channel layer, caching

#### 6. Object Storage

**Component:** MinIO (S3-compatible)  
**Version:** Latest  
**Container:** `flipstar_minio`  
**Internal Ports:** 9000 (API), 9001 (Console)  
**Exposed Ports:** 9000, 9001 (host mapping)

**Configuration:**

- Root User: Configured via `MINIO_ROOT_USER` environment variable
- Root Password: Configured via `MINIO_ROOT_PASSWORD` environment variable
- Data Volume: `minio_data`
- Console Address: `:9001`
- Health Check: HTTP `http://localhost:9000/minio/health/live`

**Alternative:** AWS S3 (configured via environment variables)

#### 7. Async Task Processing

**Component:** Celery  
**Worker Container:** `flipstar_celery_worker`  
**Beat Container:** `flipstar_celery_beat`

**Configuration:**

- Broker: Redis
- Result Backend: Redis
- Task Serialization: JSON
- Accept Content: JSON
- Timezone: UTC

**Scheduled Tasks:**

- Campaign scoring calculations
- Subscription renewals
- Payment processing
- Notification sending
- Data cleanup

#### 8. Docker Network

**Network Name:** `flipstar_network`  
**Driver:** Bridge  
**Isolation:** Container-to-container communication within network

---

### External API Communication

The Django backend container communicates with external services for critical platform functionality:

#### Onevas SMS Integration

**Direction:** Django Backend → Onevas API  
**Protocol:** HTTPS (POST requests)  
**Endpoint:** `https://onevas.et/api/partnerSms/send`  
**Purpose:** Send OTP codes for user authentication  
**Authentication:** Application key and product number via environment variables  
**Data Transmitted:** Phone number, OTP message text, product number

#### Onevas Charging Integration

**Direction:** Django Backend → Onevas API  
**Protocol:** HTTPS (POST requests)  
**Endpoint:** `https://onevas.et/api/v1/charging`  
**Purpose:** Charge user airtime balance for subscription purchases  
**Authentication:** Application key and product number via environment variables  
**Data Transmitted:** Phone number, product number

#### telebirr Direct Debit Integration

**Direction:** Django Backend → telebirr SOAP API  
**Protocol:** SOAP over HTTP/HTTPS  
**Endpoint:** Configured via `${TELEBIRR_SOAP_URL}` environment variable  
**Purpose:** Create and manage direct debit mandates for recurring payments  
**Authentication:** Third-party credentials, SP operator credentials via environment variables  
**Data Transmitted:** SOAP XML envelopes with mandate details, payment information

#### telebirr Webhook Callback

**Direction:** telebirr → Django Backend  
**Protocol:** HTTPS (POST requests)  
**Endpoint:** Configured via `${TELEBIRR_RESULT_URL}` environment variable  
**Purpose:** Notify system of mandate activation and payment status  
**Data Received:** SOAP XML with result codes, transaction details, mandate IDs

---

### Server IP Addresses

**Note:** The platform is deployed on Ethiopia Telecom infrastructure. Specific IP addresses should be obtained from the hosting provider's management console or network administrator.

**Network Configuration:**

- **Domain:** api.uat.flipstar.et
- **Internal Network:** Docker bridge network (172.17.0.0/16 default)
- **Container Communication:** Internal DNS via Docker
- **External Access:** Via Nginx reverse proxy on host ports 80/443

**Container Internal IPs (Docker-managed):**

- Backend: Assigned dynamically by Docker
- Frontend: Assigned dynamically by Docker
- PostgreSQL: Assigned dynamically by Docker
- Redis: Assigned dynamically by Docker
- MinIO: Assigned dynamically by Docker
- Nginx: Assigned dynamically by Docker

**For actual server IP addresses, please contact:**

- Ethiopia Telecom Network Administration
- System Administrator
- Cloud Infrastructure Provider

### Environment Variables

**Configuration Method:** System environment variables

The system uses environment variables for all configuration including:

- Django settings (SECRET_KEY, DEBUG, ALLOWED_HOSTS)
- Database credentials
- Redis configuration
- S3/MinIO storage credentials
- CORS settings
- telebirr integration credentials
- Onevas SMS credentials
- Web push (VAPID) keys

All sensitive values are configured via environment variables and are not committed to version control.

### Backup Strategy

**Database Backup:**

- Script: Automated backup script
- Target: S3/MinIO storage
- Format: SQL dump compressed with gzip
- Frequency: Manual (can be automated via cron)
- Retention: Configurable

**Media Backup:**

- Stored in S3/MinIO with versioning
- Automatic replication (if using AWS S3)

**Configuration Backup:**

- Environment variables backed up separately
- Docker volumes backed up via volume snapshots

---

## Encryption & Secure Communication Standards

### Encryption In Transit

#### 1. SSL/TLS Configuration

**Protocol Versions:**

- TLS 1.2 (supported)
- TLS 1.3 (supported and preferred)
- SSL 3.0, TLS 1.0, TLS 1.1 (disabled)

**Certificate Authority:** Let's Encrypt  
**Certificate Type:** DV (Domain Validation)  
**Auto-Renewal:** Enabled via certbot

**Certificate Details:**

- Domain: api.uat.flipstar.et
- Certificate Path: `/etc/letsencrypt/live/api.uat.flipstar.et/fullchain.pem`
- Private Key Path: `/etc/letsencrypt/live/api.uat.flipstar.et/privkey.pem`
- Validity: 90 days (auto-renewed)

**Cipher Configuration:**

- Cipher Preference: Server-preferred
- Strong Ciphers: Enabled
- Weak Ciphers: Disabled
- Forward Secrecy: Supported (via ECDHE key exchange)

**HTTP Security Headers:**

- Strict-Transport-Security (HSTS): Enabled (31536000 seconds)
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- X-XSS-Protection: 1; mode=block

#### 2. Database Connection Encryption

**PostgreSQL SSL Configuration:**

- SSL Mode: `require` (production)
- SSL Certificate Verification: Enabled
- Connection String: `sslmode=require`
- Encryption Protocol: TLS 1.2+

**Implementation:**

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'OPTIONS': {
            'sslmode': 'require',
        },
    }
}
```

#### 3. API Communication Security

**Authentication Token Transmission:**

- Method: HTTP Authorization header
- Format: `Authorization: Token <token>`
- Encryption: TLS 1.2/1.3
- Token Storage: Client-side (mobile app) / HttpOnly cookies (web)

**WebSocket Security:**

- Protocol: WSS (WebSocket Secure)
- Encryption: TLS 1.2/1.3
- Authentication: Token-based via query parameter or header

#### 4. Third-Party API Security

**Telebirr SOAP API:**

- Protocol: HTTP (internal network)
- SSL Verification: Disabled (internal/test environment)
- Authentication: Third-party credentials in SOAP headers
- Encryption: Should be enabled for production

**Onevas SMS API:**

- Protocol: HTTPS
- Authentication: Application key and product number
- Encryption: TLS 1.2+

**AWS S3/MinIO:**

- Protocol: HTTPS
- Authentication: Access key ID and secret access key
- Encryption: TLS 1.2+
- Signature Version: AWS Signature Version 4

#### 5. Docker Network Security

**Internal Communication:**

- Network: Docker bridge network
- Encryption: Not encrypted (trusted internal network)
- Isolation: Container-to-container only
- External Access: Via Nginx reverse proxy only

### Encryption At Rest

#### 1. Database Encryption

**PostgreSQL Encryption:**

- Current Status: Not configured (relies on disk encryption)
- Backup Encryption: Compressed with gzip (not encrypted)

**Sensitive Data Fields:**

- User passwords: Hashed (PBKDF2 with SHA256)
- API keys: Stored in environment variables
- Third-party credentials: Stored in environment variables
- Phone numbers: Stored in plaintext

#### 2. File Storage Encryption

**S3/MinIO Configuration:**

- Server-Side Encryption: Not configured by default
- Client-Side Encryption: Not implemented
- Versioning: Available (if using AWS S3)

**Media Files:**

- User uploads: Stored in S3/MinIO
- Encryption: Depends on storage provider configuration
- Access Control: Public read access via signed URLs

#### 3. Application Secrets

**Secret Management:**

- Method: Environment variables
- Storage: Docker container environment
- Access: Container runtime only
- Rotation: Manual (requires container restart)

**Secrets Stored:**

- Django SECRET_KEY
- Database passwords
- API keys (AWS S3, Telebirr, Onevas)
- Third-party credentials

#### 4. Backup Encryption

**Current Status:**

- Database backups: Compressed with gzip (not encrypted)
- Media files: Stored in S3/MinIO (encryption depends on provider)

#### 5. Token Storage

**Authentication Tokens:**

- Storage: Database (PostgreSQL)
- Format: Plain text (Django Token model)
- Hashing: Not hashed (Django default behavior)
- Expiration: No expiration (Django default)

### Encryption Standards Summary

| Data Type        | In Transit  | At Rest               | Standard       |
| ---------------- | ----------- | --------------------- | -------------- |
| User Traffic     | TLS 1.2/1.3 | N/A                   | HTTPS          |
| Database Traffic | TLS 1.2+    | Disk encryption       | PostgreSQL SSL |
| API Traffic      | TLS 1.2/1.3 | N/A                   | HTTPS          |
| File Storage     | TLS 1.2+    | Optional              | S3/MinIO       |
| Secrets          | N/A         | Environment variables | Docker secrets |
| Backups          | TLS 1.2+    | Gzip (no encryption)  | Custom         |
| Tokens           | TLS 1.2/1.3 | Plain text            | Django Token   |

---

## Third-Party Integrations Security

### telebirr Integration

**Purpose:** Mobile money payment processing  
**Protocol:** SOAP over HTTP  
**Authentication:** Third-party credentials

**Security Considerations:**

- Credentials stored in environment variables
- SOAP requests contain sensitive payment information
- SSL verification disabled (test environment)
- Webhook endpoint for callbacks

### Onevas SMS Integration

**Purpose:** SMS OTP delivery (ONLY)  
**Protocol:** HTTPS  
**Authentication:** Application key and product number

**Security Considerations:**

- Credentials stored in environment variables
- OTP codes sent via SMS (plaintext)
- OTP expiration: 5 minutes
- Rate limiting on OTP generation
- **IMPORTANT: Ethio Telecom SIM cards are ONLY accessible for SMS OTP verification. All charging functionality has been disabled to ensure phone numbers are used solely for authentication purposes.**

### AWS S3/MinIO Integration

**Purpose:** Object storage for media files  
**Protocol:** HTTPS (S3 API)  
**Authentication:** Access key ID and secret access key

**Security Considerations:**

- Credentials stored in environment variables
- Bucket access policies
- Public read access for media files
- No server-side encryption by default

### Let's Encrypt Integration

**Purpose:** SSL/TLS certificates  
**Protocol:** ACME  
**Authentication:** Domain validation

**Security Considerations:**

- Automated certificate renewal
- 90-day certificate validity
- Domain validation only (DV certificates)

---

## Compliance & Data Protection

### GDPR Compliance

**Implemented Features:**

- User data download endpoint (`/api/auth/download-data/`)
- Account deletion endpoint (`/api/auth/delete-account/`)
- Privacy settings for user profiles
- Legal document acceptance tracking

**Data Subjects Rights:**

- Right to access: Implemented
- Right to rectification: Partially implemented
- Right to erasure: Implemented
- Right to data portability: Implemented
- Right to object: Not implemented

### Data Residency

**Current Status:**

- Hosting: Ethio Telecom cloud infrastructure (Ethiopia)
- Database: PostgreSQL (Ethiopia)
- Storage: MinIO (Ethiopia) or AWS S3 (region configurable)

**Considerations:**

- Data sovereignty requirements
- Cross-border data transfer restrictions
- Local data protection laws

### Security Audits

**Current Status:**

- Logging implemented
- No formal incident response plan

---

## Appendix

### A. Security Configuration Files

**Nginx Configuration:** Reverse proxy configuration  
**Django Settings:** Application configuration  
**Production Settings:** Production environment configuration  
**Docker Compose:** Container orchestration configuration  
**Environment Variables:** System environment variables (not in version control)

### B. Security Contacts

**Development Team:** [Contact Information]  
**System Administrator:** [Contact Information]  
**Security Team:** [Contact Information]  
**Ethiopia Telecom Support:** [Contact Information]

### C. Security Resources

**Django Security:** https://docs.djangoproject.com/en/stable/topics/security/  
**OWASP Top 10:** https://owasp.org/www-project-top-ten/  
**NIST Cybersecurity Framework:** https://www.nist.gov/cyberframework  
**GDPR Guidelines:** https://gdpr.eu/

### D. Change Log

| Version | Date         | Changes                        | Author        |
| ------- | ------------ | ------------------------------ | ------------- |
| 1.0     | May 22, 2026 | Initial security documentation | Security Team |

---

**Document Classification:** Confidential  
**Distribution:** Authorized personnel only  
**Next Review Date:** August 22, 2026 (90 days)

> > > > > > > 5a9d93d435d5235ce3ff71a3385efd56876254de
