#!/bin/bash

# Database backup script

echo "🗃️ Creating database backup..."

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/${TIMESTAMP}_database_backup"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# PostgreSQL backup
echo "Backing up PostgreSQL..."
PGPASSWORD=secure_password_123 pg_dump -h localhost -p 5432 -U myhours_user -d myhours_db \
  --verbose --format=custom --file="$BACKUP_DIR/postgresql_$TIMESTAMP.dump"

# MongoDB backup
echo "Backing up MongoDB..."
if command -v mongodump &> /dev/null; then
    mongodump --host localhost:27017 --db biometrics_db --out "$BACKUP_DIR/mongodb_backup/"
    cd "$BACKUP_DIR" && tar -czf "mongodb_backup_$TIMESTAMP.tar.gz" mongodb_backup/
    rm -rf mongodb_backup/
    cd - > /dev/null
else
    echo "⚠️ mongodump not found, skipping MongoDB backup"
fi

# Create backup info
cat > "$BACKUP_DIR/backup_info.txt" << EOF
Backup created: $(date)
PostgreSQL: ✅ Completed
MongoDB: $(command -v mongodump &> /dev/null && echo "✅ Completed" || echo "❌ Skipped (mongodump not found)")
Backup directory: $BACKUP_DIR
EOF

echo "✅ Database backup completed: $BACKUP_DIR"