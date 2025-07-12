#!/bin/bash

# Restore script for MyHours database
# Usage: ./restore_backup.sh [backup_date]
# Example: ./restore_backup.sh 20250711_190824

BACKUP_DATE=$1

if [ -z "$BACKUP_DATE" ]; then
    echo "❌ Please provide backup date"
    echo "Usage: ./restore_backup.sh YYYYMMDD_HHMMSS"
    echo "Available backups:"
    ls -la backups/postgres_*.sql | awk -F'postgres_' '{print $2}' | sed 's/.sql//'
    exit 1
fi

POSTGRES_BACKUP="backups/postgres_${BACKUP_DATE}.sql"
MONGO_BACKUP="backups/mongodb_${BACKUP_DATE}"

if [ ! -f "$POSTGRES_BACKUP" ]; then
    echo "❌ PostgreSQL backup not found: $POSTGRES_BACKUP"
    exit 1
fi

if [ ! -d "$MONGO_BACKUP" ]; then
    echo "❌ MongoDB backup not found: $MONGO_BACKUP"
    exit 1
fi

echo "🔄 Starting restore from backup: $BACKUP_DATE"

# Check if containers are running
if ! docker-compose ps | grep -q "myhours_postgres.*Up"; then
    echo "❌ PostgreSQL container is not running. Please run 'make up' first"
    exit 1
fi

# Restore PostgreSQL
echo "📊 Restoring PostgreSQL..."
docker exec -i myhours_postgres psql -U myhours_user -d myhours_db < "$POSTGRES_BACKUP"
if [ $? -eq 0 ]; then
    echo "✅ PostgreSQL restored successfully"
else
    echo "❌ PostgreSQL restore failed"
    exit 1
fi

# Restore MongoDB
echo "🍃 Restoring MongoDB..."
docker cp "$MONGO_BACKUP" myhours_mongodb:/tmp/
docker exec myhours_mongodb mongorestore --drop --db biometrics_db /tmp/mongodb_${BACKUP_DATE}/biometrics_db
if [ $? -eq 0 ]; then
    echo "✅ MongoDB restored successfully"
else
    echo "❌ MongoDB restore failed"
    exit 1
fi

echo "✅ All databases restored successfully from backup: $BACKUP_DATE"
echo ""
echo "You can now login with:"
echo "  Admin: admin / admin123"
echo "  Test users: password test123"