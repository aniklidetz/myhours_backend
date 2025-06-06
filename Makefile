.PHONY: help up down restart logs setup migrate makemigrations seed \
        test clean shell psql redis-cli mongo-shell dev fresh runserver

# Python executable
PY := ./venv/bin/python

# Help
help:
	@echo "MyHours Backend Development Commands:"
	@echo "====================================="
	@echo "Docker Services:"
	@echo "  make up          - Start all Docker services (PostgreSQL, MongoDB, Redis)"
	@echo "  make down        - Stop all Docker services"
	@echo "  make restart     - Restart all services"  
	@echo "  make logs        - View Docker logs"
	@echo "  make clean       - Clean up containers and volumes"
	@echo ""
	@echo "Django Development:"
	@echo "  make runserver   - Start Django development server"
	@echo "  make migrate     - Run Django migrations"
	@echo "  make makemigrations - Create new migrations"
	@echo "  make shell       - Django shell"
	@echo "  make test        - Run tests"
	@echo "  make seed        - Load test data"
	@echo ""
	@echo "Database Access:"
	@echo "  make psql        - PostgreSQL shell"
	@echo "  make redis-cli   - Redis CLI"
	@echo "  make mongo-shell - MongoDB shell"
	@echo ""
	@echo "Quick Commands:"
	@echo "  make setup       - Full setup (containers + database + migrations)"
	@echo "  make dev         - Start services and Django server"
	@echo "  make fresh       - Clean everything and setup from scratch"

# Docker Services
up:
	docker-compose up -d
	@echo "✅ Services started. Waiting for databases to be ready..."
	@sleep 5
	@echo "📊 PostgreSQL: localhost:5432"
	@echo "📦 Redis: localhost:6379" 
	@echo "🍃 MongoDB: localhost:27017"

down:
	docker-compose down

restart: down up

logs:
	docker-compose logs -f

clean:
	docker-compose down -v
	@echo "✅ All containers and volumes removed"

# Django Development
runserver:
	$(PY) manage.py runserver 0.0.0.0:8000

migrate:
	$(PY) manage.py migrate

makemigrations:
	$(PY) manage.py makemigrations

shell:
	$(PY) manage.py shell

test:
	$(PY) manage.py test

seed:
	$(PY) scripts/setup_database.py

# Database Access
psql:
	docker exec -it myhours_postgres psql -U myhours_user -d myhours_db

redis-cli:
	docker exec -it myhours_redis redis-cli -a redis_password_123

mongo-shell:
	docker exec -it myhours_mongodb mongosh biometrics_db

# Compound Commands
setup: up
	@echo "⏳ Waiting for services to be ready..."
	@sleep 10
	@echo "🔄 Running migrations..."
	@$(MAKE) migrate
	@echo "🌱 Seeding database..."
	@$(MAKE) seed
	@echo "✅ Backend setup complete!"

dev: up runserver

fresh: clean setup

# Development helpers
superuser:
	$(PY) manage.py createsuperuser

collectstatic:
	$(PY) manage.py collectstatic --noinput

install:
	pip install -r requirements.txt

check:
	$(PY) manage.py check

# Production helpers
prod-migrate:
	$(PY) manage.py migrate --settings=myhours.settings_prod

prod-collectstatic:
	$(PY) manage.py collectstatic --noinput --settings=myhours.settings_prod