.PHONY: help up down restart logs setup migrate makemigrations seed \
        test clean shell psql redis-cli mongo-shell dev fresh runserver \
        build env-setup docker-up docker-down docker-logs docker-test \
        backup restore status health

# Python executable
PY := ./venv/bin/python

# Environment setup
ENV_FILE := .env
ENV_SAMPLE := .env.sample

# Help
help:
	@echo "🚀 MyHours Backend DevOps Commands"
	@echo "=================================="
	@echo ""
	@echo "🐳 Docker DevOps:"
	@echo "  make up              - Start entire stack (databases + web + celery)"
	@echo "  make down            - Stop all services"
	@echo "  make restart         - Restart all services"
	@echo "  make build           - Build Docker images"
	@echo "  make logs            - View all service logs"
	@echo "  make status          - Show service status"
	@echo "  make health          - Check service health"
	@echo ""
	@echo "⚙️ Environment Setup:"
	@echo "  make env-setup       - Create .env from template"
	@echo "  make setup           - Full setup (env + build + migrate + seed)"
	@echo "  make fresh           - Clean everything and setup from scratch"
	@echo ""
	@echo "🧪 Testing & Development:"
	@echo "  make test            - Run all tests"
	@echo "  make docker-test     - Run tests in Docker"
	@echo "  make shell           - Django shell"
	@echo "  make migrate         - Run migrations"
	@echo "  make makemigrations  - Create migrations"
	@echo ""
	@echo "🗄️ Database Access:"
	@echo "  make psql            - PostgreSQL shell"
	@echo "  make redis-cli       - Redis CLI"
	@echo "  make mongo-shell     - MongoDB shell"
	@echo ""
	@echo "🔧 Utilities:"
	@echo "  make backup          - Backup databases"
	@echo "  make restore         - Restore from backup"
	@echo "  make clean           - Clean containers and volumes"
	@echo "  make superuser       - Create Django superuser"

# Environment Setup
env-setup:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "📋 Creating .env from template..."; \
		cp $(ENV_SAMPLE) $(ENV_FILE); \
		echo "✅ .env file created. Please edit it with your settings."; \
		echo "🔑 Don't forget to generate a new SECRET_KEY!"; \
	else \
		echo "ℹ️ .env file already exists"; \
	fi

# Docker DevOps Commands
up: env-setup
	@echo "🚀 Starting MyHours full stack..."
	docker-compose up -d
	@echo "⏳ Waiting for services to be ready..."
	@sleep 15
	@echo "✅ Stack is up! Services:"
	@echo "  🌐 Web:        http://localhost:8000"
	@echo "  📊 Admin:      http://localhost:8000/admin/"
	@echo "  📖 API Docs:   http://localhost:8000/api/schema/swagger/"
	@echo "  📈 Health:     http://localhost:8000/health/"

down:
	@echo "🛑 Stopping all services..."
	docker-compose down
	@echo "✅ All services stopped"

restart: down up

build:
	@echo "🔨 Building Docker images..."
	docker-compose build --no-cache
	@echo "✅ Build complete"

logs:
	docker-compose logs -f

status:
	@echo "📊 Service Status:"
	docker-compose ps

health:
	@echo "🏥 Health Check:"
	@docker-compose ps --filter "status=running" --quiet | xargs -I {} docker inspect {} --format '{{.Name}}: {{.State.Health.Status}}' 2>/dev/null || echo "Some containers don't have health checks"

# Testing
test:
	@echo "🧪 Running tests locally..."
	$(PY) manage.py test --keepdb

docker-test:
	@echo "🧪 Running tests in Docker..."
	docker-compose exec web python manage.py test --keepdb

# Database Operations
migrate:
	@echo "🔄 Running migrations..."
	docker-compose exec web python manage.py migrate

makemigrations:
	@echo "📝 Creating migrations..."
	docker-compose exec web python manage.py makemigrations

shell:
	@echo "🐍 Opening Django shell..."
	docker-compose exec web python manage.py shell

superuser:
	@echo "👤 Creating superuser..."
	docker-compose exec web python manage.py createsuperuser

seed:
	@echo "🌱 Seeding database..."
	docker-compose exec web python scripts/setup_database.py

# Database Access
psql:
	@echo "🐘 Connecting to PostgreSQL..."
	docker exec -it myhours_postgres psql -U myhours_user -d myhours_db

redis-cli:
	@echo "📦 Connecting to Redis..."
	docker exec -it myhours_redis redis-cli -a redis_password_123

mongo-shell:
	@echo "🍃 Connecting to MongoDB..."
	docker exec -it myhours_mongodb mongosh biometrics_db

# Backup & Restore
backup:
	@echo "💾 Creating backup..."
	mkdir -p backups
	docker exec myhours_postgres pg_dump -U myhours_user myhours_db > backups/postgres_$(shell date +%Y%m%d_%H%M%S).sql
	docker exec myhours_mongodb mongodump --db biometrics_db --out /tmp/mongo_backup
	docker cp myhours_mongodb:/tmp/mongo_backup backups/mongodb_$(shell date +%Y%m%d_%H%M%S)
	@echo "✅ Backup complete in ./backups/"

restore:
	@echo "📥 Restore functionality - implement with specific backup file"
	@echo "Usage: docker exec -i myhours_postgres psql -U myhours_user -d myhours_db < backups/your_backup.sql"

# Cleanup
clean:
	@echo "🧹 Cleaning up..."
	docker-compose down -v --remove-orphans
	docker system prune -f
	@echo "✅ Cleanup complete"

# Compound Commands
setup: env-setup build up
	@echo "⏳ Waiting for services to be fully ready..."
	@sleep 20
	@$(MAKE) migrate
	@$(MAKE) seed
	@echo "🎉 Full setup complete! MyHours is ready to use."

fresh: clean setup

# Development helpers (for local development without Docker)
local-runserver:
	$(PY) manage.py runserver 0.0.0.0:8000

local-migrate:
	$(PY) manage.py migrate

local-test:
	$(PY) manage.py test

collectstatic:
	docker-compose exec web python manage.py collectstatic --noinput

install:
	pip install -r requirements.txt

check:
	docker-compose exec web python manage.py check --deploy

# Production helpers
prod-migrate:
	docker-compose exec web python manage.py migrate --settings=myhours.settings_prod

prod-collectstatic:
	docker-compose exec web python manage.py collectstatic --noinput --settings=myhours.settings_prod

# Quick aliases
docker-up: up
docker-down: down
docker-logs: logs