#!/bin/bash

# Setup automated log rotation and cleanup via crontab

PROJECT_PATH="/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend"

echo "⏰ Setting up automated cleanup schedule..."

# Create temporary crontab file
TEMP_CRON=$(mktemp)

# Get existing crontab (if any) and filter out our entries
crontab -l 2>/dev/null | grep -v "myhours-backend.*cleanup" > "$TEMP_CRON" || true

echo ""
echo "📋 Adding cleanup schedules:"

# Log rotation - every Sunday at 2 AM
echo "0 2 * * 0 cd $PROJECT_PATH && ./scripts/cleanup/setup_log_rotation.sh >> logs/rotation.log 2>&1" >> "$TEMP_CRON"
echo "   ✅ Log rotation: Sundays at 2:00 AM"

# Full cleanup - first day of every month at 3 AM  
echo "0 3 1 * * cd $PROJECT_PATH && ./scripts/cleanup/cleanup_old_files.sh >> logs/cleanup.log 2>&1" >> "$TEMP_CRON"
echo "   ✅ Full cleanup: Monthly on 1st at 3:00 AM"

# Install new crontab
crontab "$TEMP_CRON"

# Clean up temp file
rm "$TEMP_CRON"

echo ""
echo "📅 Current crontab schedule:"
crontab -l | grep -E "(cleanup|rotation)" || echo "   (no cleanup tasks found)"

echo ""
echo "✅ Automated cleanup schedule configured!"
echo ""
echo "📋 Manual commands:"
echo "   Log rotation only: ./scripts/cleanup/setup_log_rotation.sh"
echo "   Full cleanup:      ./scripts/cleanup/cleanup_old_files.sh"
echo "   Remove schedule:   crontab -l | grep -v 'myhours-backend.*cleanup' | crontab -"