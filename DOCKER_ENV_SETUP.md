# Docker Environment Setup Guide

## Issue: MongoDB Connection in Docker

When running the application with Docker Compose, the Django service was trying to connect to MongoDB on `localhost:27017`, which fails because in Docker each service runs in its own container and must use service names for inter-container communication.

## Solution

### 1. Environment Variable Priority

The application reads configuration in this order:
1. Environment variables set in `docker-compose.yml`
2. `.env` file values
3. Default values in `settings.py`

### 2. Correct Configuration for Docker

When running with Docker Compose, ensure all service connections use container names:

- **PostgreSQL**: `postgres` (not `localhost`)
- **Redis**: `redis` (not `localhost`) 
- **MongoDB**: `mongodb` (not `localhost`)

### 3. Configuration Options

#### Option A: Use docker-compose environment variables (Recommended)
The `docker-compose.yml` already sets the correct environment variables. These will override `.env` file values.

#### Option B: Use .env.docker file
```bash
# Before starting Docker Compose
cp .env.docker .env
```

#### Option C: Override at runtime
```bash
# Set environment variables when running docker-compose
MONGO_HOST=mongodb MONGO_CONNECTION_STRING=mongodb://mongodb:27017/ docker-compose up
```

### 4. Verification

After updating the configuration and restarting the containers:

```bash
# Restart the containers
docker-compose down
docker-compose up -d

# Check health endpoint
curl http://localhost:8000/health/

# Check logs for MongoDB connection
docker-compose logs web | grep -i mongo
```

### 5. Common Issues

1. **Cached Python bytecode**: If changes don't take effect, remove `__pycache__` directories
2. **Container not restarted**: Always restart containers after environment changes
3. **Wrong .env file**: Ensure you're using the Docker-specific configuration when running in containers

### 6. Development vs Docker

For local development (without Docker):
- Use `localhost` for all services
- Services must be installed and running locally

For Docker development:
- Use container service names (`mongodb`, `postgres`, `redis`)
- All services are managed by Docker Compose