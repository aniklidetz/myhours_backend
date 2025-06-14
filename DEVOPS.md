# 🚀 MyHours DevOps Guide

Complete Docker-based deployment solution for MyHours backend.

## Quick Start (One Command Deployment)

```bash
make setup
```

This single command will:
- Create `.env` from template
- Build Docker images
- Start all services (web, databases, celery)
- Run migrations
- Seed database
- Display service URLs

## 📋 Prerequisites

- Docker & Docker Compose
- Make utility
- Git

## 🛠️ Available Commands

### Core DevOps
```bash
make up              # Start entire stack
make down            # Stop all services
make restart         # Restart all services
make status          # Show service status
make logs            # View live logs
make health          # Check service health
```

### Environment Setup
```bash
make env-setup       # Create .env from template
make setup           # Full setup (recommended for first time)
make fresh           # Clean everything and setup from scratch
```

### Development
```bash
make test            # Run tests locally
make docker-test     # Run tests in Docker
make shell           # Django shell
make migrate         # Run migrations
make superuser       # Create Django admin user
```

### Database Access
```bash
make psql            # PostgreSQL shell
make redis-cli       # Redis CLI
make mongo-shell     # MongoDB shell
```

### Utilities
```bash
make backup          # Backup all databases
make clean           # Clean containers and volumes
make build           # Rebuild Docker images
```

## 🌐 Service URLs

After running `make up`:

- **Web Application**: http://localhost:8000
- **Django Admin**: http://localhost:8000/admin/
- **API Documentation**: http://localhost:8000/api/schema/swagger/
- **Health Check**: http://localhost:8000/health/

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   React Native  │    │     Nginx       │    │     Django      │
│    Frontend     │────│   (Production)  │────│   Web Service   │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                              ┌─────────────────────────┼─────────────────────────┐
                              │                         │                         │
                    ┌─────────▼──────────┐    ┌─────────▼──────────┐    ┌─────────▼──────────┐
                    │    PostgreSQL      │    │      Redis         │    │     MongoDB        │
                    │   (Main Database)  │    │   (Cache/Queue)    │    │   (Biometrics)     │
                    │                    │    │                    │    │                    │
                    └────────────────────┘    └────────────────────┘    └────────────────────┘
                                                        │
                                              ┌─────────▼──────────┐
                                              │      Celery        │
                                              │     Worker         │
                                              │                    │
                                              └────────────────────┘
```

## 📝 Environment Configuration

1. **Copy environment template**:
   ```bash
   make env-setup
   ```

2. **Edit `.env` file** with your settings:
   ```bash
   nano .env
   ```

3. **Generate new SECRET_KEY**:
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

## 🔧 Configuration Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Main services configuration |
| `docker-compose.override.yml` | Development overrides (auto-loaded) |
| `docker-compose.prod.yml` | Production configuration |
| `Dockerfile` | Django application container |
| `.env.sample` | Environment template |
| `nginx.conf` | Nginx configuration for production |
| `Makefile` | DevOps command shortcuts |

## 🚢 Production Deployment

```bash
# Use production configuration
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Or with make command
make up COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
```

## 🏥 Health Monitoring

### Health Check Endpoints
- **Simple**: `GET /api/health/` - Basic status
- **Detailed**: `GET /health/` - All services status

### Service Status
```bash
make health     # Check all service health
make status     # Show container status
```

## 💾 Backup & Restore

### Create Backup
```bash
make backup
```
This creates backups in `./backups/` directory:
- PostgreSQL dump
- MongoDB dump

### Restore from Backup
```bash
# PostgreSQL
docker exec -i myhours_postgres psql -U myhours_user -d myhours_db < backups/postgres_YYYYMMDD_HHMMSS.sql

# MongoDB
docker exec -i myhours_mongodb mongorestore --db biometrics_db /path/to/backup
```

## 🧪 Testing

### Run Tests
```bash
make test           # Run tests locally
make docker-test    # Run tests in Docker container
```

### Test Coverage
```bash
docker-compose exec web coverage run --source='.' manage.py test
docker-compose exec web coverage report
```

## 🔍 Troubleshooting

### View Logs
```bash
make logs                           # All services
docker-compose logs web             # Web service only
docker-compose logs postgres        # Database only
```

### Check Service Health
```bash
make health
curl http://localhost:8000/health/
```

### Reset Everything
```bash
make fresh    # Clean and rebuild everything
```

### Common Issues

1. **Port already in use**:
   ```bash
   make down
   docker-compose ps
   ```

2. **Database connection issues**:
   ```bash
   make psql    # Test PostgreSQL connection
   ```

3. **Permission issues**:
   ```bash
   make clean   # Clean volumes
   make setup   # Rebuild
   ```

## 🔒 Security Notes

- Change default passwords in `.env`
- Generate new `SECRET_KEY` for production
- Set `DEBUG=False` in production
- Configure proper `ALLOWED_HOSTS`
- Use HTTPS in production (not included in this setup)

## 📊 Monitoring & Metrics

Health check endpoint provides:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-01T12:00:00Z",
  "services": {
    "django": {"status": "healthy"},
    "postgresql": {"status": "healthy"},
    "redis": {"status": "healthy"},
    "mongodb": {"status": "healthy"}
  }
}
```

---

**For more help**: `make help`