# 🐳 Docker Setup for MyHours Backend

## Quick Start

### 1. Start the databases:
```bash
cd backend/myhours-backend
docker-compose up -d
```

### 2. Set up Django:
```bash
# Create .env file
cp .env.docker .env
# Edit .env with your settings

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start Django development server
python manage.py runserver
```

## Services

The docker-compose.yml includes:

- **PostgreSQL** (port 5432) - Main database
- **MongoDB** (port 27017) - Biometric data storage  
- **Redis** (port 6379) - Caching and sessions

## Useful Commands

### Start all services:
```bash
docker-compose up -d
```

### Stop all services:
```bash
docker-compose down
```

### View logs:
```bash
docker-compose logs -f
```

### Reset all data:
```bash
docker-compose down -v
docker-compose up -d
```

### Check service health:
```bash
docker-compose ps
```

## Environment Variables

Copy `.env.docker` to `.env` and customize:

- `SECRET_KEY` - Django secret key
- `DEBUG` - Development mode (True/False)
- `POSTGRES_*` - Database credentials
- `MONGO_*` - MongoDB settings
- `REDIS_URL` - Redis connection string

## Production Notes

For production:
1. Change all passwords in `.env`
2. Set `DEBUG=False`
3. Configure proper `ALLOWED_HOSTS`
4. Use environment-specific secrets
5. Consider using external managed databases