#!/bin/bash # Redis High Availability Startup Script
# Launches Redis master, slaves, and Sentinel cluster set -e SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")" echo "Starting Redis High Availability Cluster"
echo "============================================" # Check if required files exist
if [ ! -f "$PROJECT_DIR/docker-compose.yml" ]; then echo "docker-compose.yml not found in $PROJECT_DIR" exit 1
fi if [ ! -f "$PROJECT_DIR/docker-compose.redis-sentinel.yml" ]; then echo "docker-compose.redis-sentinel.yml not found" exit 1
fi if [ ! -f "$PROJECT_DIR/redis-config/sentinel.conf" ]; then echo "redis-config/sentinel.conf not found" exit 1
fi # Check if .env file exists
if [ ! -f "$PROJECT_DIR/.env" ]; then echo ".env file not found. Creating from template..." if [ -f "$PROJECT_DIR/.env.redis-ha" ]; then cp "$PROJECT_DIR/.env.redis-ha" "$PROJECT_DIR/.env" echo "Created .env from .env.redis-ha template" echo "Please edit .env file and set REDIS_PASSWORD before continuing" read -p "Press Enter when you've configured .env file..." else echo "No .env template found" exit 1 fi
fi # Load environment variables
if [ -f "$PROJECT_DIR/.env" ]; then echo " Loading environment variables from .env" export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi # Check if Redis password is set
if [ -z "$REDIS_PASSWORD" ]; then echo "REDIS_PASSWORD not set in .env file" echo "Please set a secure password for Redis authentication" exit 1
fi echo "Configuration:"
echo " Redis Password: ${REDIS_PASSWORD:0:3}***"
echo " Sentinel Service: ${REDIS_SENTINEL_SERVICE:-myhours-master}"
echo " Sentinel Hosts: ${REDIS_SENTINEL_HOSTS:-redis-sentinel-1:26379,redis-sentinel-2:26379,redis-sentinel-3:26379}" # Stop any existing containers
echo " Stopping existing containers..."
cd "$PROJECT_DIR"
docker-compose -f docker-compose.yml -f docker-compose.redis-sentinel.yml down --remove-orphans # Start Redis HA cluster
echo "Starting Redis HA cluster..."
docker-compose -f docker-compose.yml -f docker-compose.redis-sentinel.yml up -d # Wait for services to start
echo " Waiting for services to start..."
sleep 10 # Check service status
echo "Checking service status..."
docker-compose -f docker-compose.yml -f docker-compose.redis-sentinel.yml ps # Test Redis master connection
echo " Testing Redis master connection..."
if docker exec myhours_redis_master redis-cli -a "$REDIS_PASSWORD" ping > /dev/null 2>&1; then echo "Redis master is responding"
else echo "Redis master is not responding" exit 1
fi # Test Sentinel connections
echo " Testing Redis Sentinel connections..."
SENTINEL_HEALTHY=0
for i in {1..3}; do if docker exec "myhours_redis_sentinel_$i" redis-cli -p 26379 ping > /dev/null 2>&1; then echo "Sentinel $i is responding" ((SENTINEL_HEALTHY++)) else echo "Sentinel $i is not responding" fi
done if [ $SENTINEL_HEALTHY -ge 2 ]; then echo "Sufficient Sentinels are healthy ($SENTINEL_HEALTHY/3)"
else echo "Not enough Sentinels are healthy ($SENTINEL_HEALTHY/3)" echo "High availability may be compromised"
fi # Check master discovery through Sentinel
echo "Testing master discovery through Sentinel..."
MASTER_INFO=$(docker exec myhours_redis_sentinel_1 redis-cli -p 26379 sentinel masters | head -20)
if echo "$MASTER_INFO" | grep -q "myhours-master"; then echo "Sentinel can discover master" MASTER_HOST=$(echo "$MASTER_INFO" | grep -A 1 "ip" | tail -1) MASTER_PORT=$(echo "$MASTER_INFO" | grep -A 1 "port" | tail -1) echo "📍 Current master: $MASTER_HOST:$MASTER_PORT"
else echo "Sentinel cannot discover master"
fi echo ""
echo "Redis High Availability cluster is ready!"
echo ""
echo " Next steps:"
echo "1. Set USE_REDIS_SENTINEL=true in your .env file"
echo "2. Run the test script: python scripts/test_redis_ha.py"
echo "3. Test your Django application with Redis HA"
echo ""
echo " Useful commands:"
echo " View logs: docker-compose -f docker-compose.yml -f docker-compose.redis-sentinel.yml logs -f"
echo " Stop cluster: docker-compose -f docker-compose.yml -f docker-compose.redis-sentinel.yml down"
echo " Master status: docker exec myhours_redis_master redis-cli -a '$REDIS_PASSWORD' info replication"
echo " Sentinel status: docker exec myhours_redis_sentinel_1 redis-cli -p 26379 sentinel masters"