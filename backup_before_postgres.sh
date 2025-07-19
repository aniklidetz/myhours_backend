#!/bin/bash

# Backup script before PostgreSQL migration
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/before_postgres_${DATE}"

echo "🔵 Creating backup before PostgreSQL migration..."
mkdir -p $BACKUP_DIR

# 1. Backup MongoDB
echo "📦 Backing up MongoDB..."
docker exec myhours-backend-mongodb-1 mongodump --uri "mongodb://mongo_admin:mongo_password_123@localhost:27017" --out /dump
docker cp myhours-backend-mongodb-1:/dump $BACKUP_DIR/mongodb_backup
echo "✅ MongoDB backed up"

# 2. Backup SQLite (if exists in container)
echo "📦 Backing up SQLite..."
docker cp myhours-backend-backend-1:/app/db.sqlite3 $BACKUP_DIR/db.sqlite3 2>/dev/null || echo "⚠️  No SQLite file found (ok if using PostgreSQL)"

# 3. Backup PostgreSQL (if running)
echo "📦 Backing up PostgreSQL..."
docker exec myhours-backend-db-1 pg_dump -U myhours_user myhours_db > $BACKUP_DIR/postgres_backup.sql 2>/dev/null || echo "⚠️  PostgreSQL backup failed (ok if not running)"

echo ""
echo "✅ Backup completed in: $BACKUP_DIR"
echo ""
echo "Next steps:"
echo "1. Stop containers: docker-compose down"
echo "2. Update docker-compose.yml to ensure PostgreSQL is used"
echo "3. Restart: docker-compose up -d"
echo "4. Run migrations: docker exec myhours-backend-backend-1 python manage.py migrate"