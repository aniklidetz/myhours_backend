#!/bin/bash
set -e

echo "Checking for initial backup to restore..."

# Check if database is already initialized (has tables)
TABLES_COUNT=$(psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "0")

if [ "$TABLES_COUNT" -eq "0" ]; then
    echo "Database is empty, looking for backup to restore..."
    
    # Find the latest backup file
    LATEST_BACKUP=$(ls -t /docker-entrypoint-initdb.d/postgres_*.sql 2>/dev/null | head -1)
    
    if [ -f "$LATEST_BACKUP" ]; then
        echo "Found backup: $LATEST_BACKUP"
        echo "Restoring database from backup..."
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$LATEST_BACKUP"
        echo "Backup restored successfully!"
    else
        echo "No backup file found in /docker-entrypoint-initdb.d/"
        echo "Database will start empty."
    fi
else
    echo "Database already has $TABLES_COUNT tables, skipping restore."
fi