#!/bin/bash

# Log rotation setup script for MyHours backend

echo "🗂️ Setting up log rotation for MyHours backend..."

# Create logs archive directory
mkdir -p logs/archive

echo "📋 Current log files status:"
find logs -maxdepth 1 -type f \( -name '*.log' -o -regex '.*/.*\.log\.[0-9]+' \) -ls

echo ""
echo "📊 Total log size before cleanup:"
du -sh logs/

# Archive old logs
echo ""
echo "🗃️ Archiving old log files..."

# Archive biometric logs (keep only current)
if [ -f "logs/biometric.log.1" ]; then
    gzip -c logs/biometric.log.1 > "logs/archive/biometric_$(date +%Y%m%d_%H%M%S).log.gz"
    rm logs/biometric.log.1
    echo "   ✅ Archived biometric.log.1"
fi

if [ -f "logs/biometric.log.2" ]; then
    gzip -c logs/biometric.log.2 > "logs/archive/biometric_old2_$(date +%Y%m%d_%H%M%S).log.gz"
    rm logs/biometric.log.2
    echo "   ✅ Archived biometric.log.2"
fi

if [ -f "logs/biometric.log.3" ]; then
    gzip -c logs/biometric.log.3 > "logs/archive/biometric_old3_$(date +%Y%m%d_%H%M%S).log.gz"
    rm logs/biometric.log.3
    echo "   ✅ Archived biometric.log.3"
fi

# Compress current large logs if they're over 1MB
if [ -f "logs/django.log" ]; then
    size=$(stat -f%z logs/django.log 2>/dev/null || stat -c%s logs/django.log 2>/dev/null)
    if [ "$size" -gt 1048576 ]; then  # 1MB
        echo "   📦 Compressing large django.log ($((size / 1048576))MB)..."
        gzip -c logs/django.log > "logs/archive/django_$(date +%Y%m%d_%H%M%S).log.gz"
        # Keep only last 1000 lines in current log
        tail -1000 logs/django.log > logs/django.log.tmp
        mv logs/django.log.tmp logs/django.log
        echo "   ✅ Compressed django.log"
    fi
fi

if [ -f "logs/biometric.log" ]; then
    size=$(stat -f%z logs/biometric.log 2>/dev/null || stat -c%s logs/biometric.log 2>/dev/null)
    if [ "$size" -gt 1048576 ]; then  # 1MB
        echo "   📦 Compressing large biometric.log ($((size / 1048576))MB)..."
        gzip -c logs/biometric.log > "logs/archive/biometric_current_$(date +%Y%m%d_%H%M%S).log.gz"
        # Keep only last 1000 lines in current log
        tail -1000 logs/biometric.log > logs/biometric.log.tmp
        mv logs/biometric.log.tmp logs/biometric.log
        echo "   ✅ Compressed biometric.log"
    fi
fi

echo ""
echo "📊 Total log size after cleanup:"
du -sh logs/

echo ""
echo "🗃️ Archived files:"
ls -lah logs/archive/ 2>/dev/null || echo "   (no archived files yet)"

echo ""
echo "✅ Log rotation setup completed!"
echo "📋 To run this regularly, add to crontab:"
echo "   0 2 * * 0 /path/to/your/project/scripts/cleanup/setup_log_rotation.sh"