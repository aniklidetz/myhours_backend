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
	@echo "MyHours Backend DevOps Commands"
	@echo "=================================="
	@echo ""
	@echo "Demo Commands:"
	@echo "  make demo-up         - Start demo environment (production-like)"
	@echo "  make demo-down       - Stop demo environment"
	@echo "  make demo-setup      - Setup demo data and admin user"
	@echo "  make demo-logs       - View demo logs"
	@echo "  make demo-clean      - Clean demo environment completely"
	@echo ""
	@echo "Docker DevOps:"
	@echo "  make up              - Start entire stack (databases + web + celery)"
	@echo "  make down            - Stop all services"
	@echo "  make restart         - Restart all services"
	@echo "  make build           - Build Docker images"
	@echo "  make logs            - View all service logs"
	@echo "  make status          - Show service status"
	@echo "  make health          - Check service health"
	@echo ""
	@echo "Environment Setup:"
	@echo "  make env-setup       - Create .env from template"
	@echo "  make setup           - Full setup (env + build + migrate + seed)"
	@echo "  make fresh           - Clean everything and setup from scratch"
	@echo ""
	@echo "Testing & Development:"
	@echo "  make test            - Run all tests"
	@echo "  make docker-test     - Run tests in Docker"
	@echo "  make shell           - Django shell"
	@echo "  make migrate         - Run migrations"
	@echo "  make makemigrations  - Create migrations"
	@echo ""
	@echo "Database Access:"
	@echo "  make psql            - PostgreSQL shell"
	@echo "  make redis-cli       - Redis CLI"
	@echo "  make mongo-shell     - MongoDB shell"
	@echo ""
	@echo "Utilities:"
	@echo "  make backup          - Backup databases"
	@echo "  make restore         - Restore from backup"
	@echo "  make clean           - Clean containers and volumes"
	@echo "  make superuser       - Create Django superuser"

# Environment Setup
env-setup:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "Creating .env from template..."; \
		cp $(ENV_SAMPLE) $(ENV_FILE); \
		echo ".env file created. Please edit it with your settings."; \
		echo "Don't forget to generate a new SECRET_KEY!"; \
	else \
		echo "ℹ.env file already exists"; \
	fi

# Docker DevOps Commands
up: env-setup
	@echo "Starting MyHours full stack..."
	docker-compose --env-file .env up -d
	@echo "Waiting for services to be ready..."
	@sleep 15
	@echo "Stack is up! Services:"
	@echo "  Web:        http://localhost:8000"
	@echo "  Admin:      http://localhost:8000/admin/"
	@echo "  API Docs:   http://localhost:8000/api/schema/swagger/"
	@echo "  Health:     http://localhost:8000/health/"

down:
	@echo "Stopping all services..."
	docker-compose --env-file .env down
	@echo "All services stopped"

restart: down up

build:
	@echo "Building Docker images..."
	docker-compose --env-file .env build --no-cache
	@echo "Build complete"

logs:
	docker-compose --env-file .env logs -f

status:
	@echo "Service Status:"
	docker-compose --env-file .env ps

health:
	@echo "Health Check:"
	@docker-compose ps --filter "status=running" --quiet | xargs -I {} docker inspect {} --format '{{.Name}}: {{.State.Health.Status}}' 2>/dev/null || echo "Some containers don't have health checks"

# Testing
test:
	@echo "Running tests locally..."
	$(PY) manage.py test --keepdb

docker-test:
	@echo "Running tests in Docker..."
	docker-compose --env-file .env exec web python manage.py test --keepdb

# Database Operations
migrate:
	@echo "Running migrations..."
	docker-compose --env-file .env exec web python manage.py migrate

makemigrations:
	@echo "Creating migrations..."
	docker-compose --env-file .env exec web python manage.py makemigrations

shell:
	@echo "Opening Django shell..."
	docker-compose --env-file .env exec web python manage.py shell

superuser:
	@echo "Creating superuser..."
	docker-compose --env-file .env exec web python manage.py createsuperuser

seed:
	@echo "Seeding database..."
	docker-compose --env-file .env exec web python scripts/setup_database.py

# Database Access
psql:
	@echo "Connecting to PostgreSQL..."
	docker exec -it myhours_postgres psql -U myhours_user -d myhours_db

redis-cli:
	@echo "Connecting to Redis..."
	docker exec -it myhours_redis redis-cli -a redis_password_123

mongo-shell:
	@echo "Connecting to MongoDB..."
	docker exec -it myhours_mongodb mongosh biometrics_db

# Backup & Restore
backup:
	@echo "Creating backup..."
	mkdir -p backups
	docker exec myhours_postgres pg_dump -U myhours_user myhours_db > backups/postgres_$(shell date +%Y%m%d_%H%M%S).sql
	docker exec myhours_mongodb mongodump --db biometrics_db --out /tmp/mongo_backup
	docker cp myhours_mongodb:/tmp/mongo_backup backups/mongodb_$(shell date +%Y%m%d_%H%M%S)
	docker-compose exec web python backup_data.py
	@echo "Backup complete in ./backups/"

quick-backup:
	@echo "Quick data backup..."
	docker-compose exec web python backup_data.py

restore:
	@echo "Restore functionality - implement with specific backup file"
	@echo "Usage: docker exec -i myhours_postgres psql -U myhours_user -d myhours_db < backups/your_backup.sql"

update-init-backup:
	@echo "Updating initialization backup..."
	@mkdir -p docker-entrypoint-initdb.d
	@rm -f docker-entrypoint-initdb.d/postgres_*.sql
	@if [ -f "backups/$$(ls -t backups/postgres_*.sql | head -1 | xargs basename)" ]; then \
		cp "backups/$$(ls -t backups/postgres_*.sql | head -1 | xargs basename)" docker-entrypoint-initdb.d/; \
		echo "Copied $$(ls -t backups/postgres_*.sql | head -1 | xargs basename) to init directory"; \
	else \
		echo "No backup found in backups/ directory"; \
	fi

# Cleanup
clean:
	@echo "Cleaning up..."
	docker-compose --env-file .env down -v --remove-orphans
	docker system prune -f
	@echo "Cleanup complete"

# Compound Commands
setup: env-setup build up
	@echo "Waiting for services to be fully ready..."
	@sleep 20
	@$(MAKE) migrate
	@$(MAKE) seed
	@echo "Full setup complete! MyHours is ready to use."

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

# Demo Commands
demo-up:
	@echo "Starting MyHours Demo Environment..."
	docker-compose -f docker-compose.demo.yml up --build -d
	@echo "Waiting for services to be ready..."
	@sleep 20
	@echo "Demo environment started!"
	@echo "  Web:        http://localhost"
	@echo "  API:        http://localhost/api/v1/"
	@echo "  Admin:      http://localhost/admin/"

demo-down:
	@echo "Stopping demo environment..."
	docker-compose -f docker-compose.demo.yml down

demo-logs:
	docker-compose -f docker-compose.demo.yml logs -f

demo-clean:
	@echo "Cleaning demo environment..."
	docker-compose -f docker-compose.demo.yml down -v
	docker system prune -f

demo-setup:
	@echo "Setting up demo data..."
	docker-compose -f docker-compose.demo.yml exec web python manage.py migrate
	docker-compose -f docker-compose.demo.yml exec web python manage.py collectstatic --noinput
	@echo "Creating admin user..."
	docker-compose -f docker-compose.demo.yml exec web python manage.py shell -c "\
from django.contrib.auth.models import User; \
from users.models import Employee; \
if not User.objects.filter(username='admin').exists(): \
    admin = User.objects.create_superuser('admin', 'admin@example.com', 'admin123'); \
    Employee.objects.create(user=admin, first_name='Demo', last_name='Admin', email='admin@example.com', role='admin', is_superuser=True) \
else: \
    print('Admin user already exists') \
"
	@echo "Demo setup complete!"
	@echo "Admin login: admin / admin123"

demo-health:
	@echo "🏥 Checking demo health..."
	curl -f http://localhost/api/health/ || echo "Demo API not responding"

# Quick aliases
docker-up: up
docker-down: down
docker-logs: logs