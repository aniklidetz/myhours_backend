#!/usr/bin/env python3
"""
Service Status Checker for MyHours
Checks PostgreSQL, MongoDB, Redis, and Django services
"""

import os
import sys
import subprocess
import socket
import time
import redis
import psycopg2
from pymongo import MongoClient
from decouple import config

def check_port(host, port, timeout=5):
    """Check if a port is open"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def check_postgresql():
    """Check PostgreSQL connection"""
    try:
        conn = psycopg2.connect(
            host=config('DB_HOST', default='localhost'),
            port=config('DB_PORT', default=5432, cast=int),
            database=config('DB_NAME', default='myhours_db'),
            user=config('DB_USER', default='myhours_user'),
            password=config('DB_PASSWORD', default='secure_password_123')
        )
        conn.close()
        print("✅ PostgreSQL: Connected")
        return True
    except Exception as e:
        print(f"❌ PostgreSQL: Failed - {e}")
        return False

def check_mongodb():
    """Check MongoDB connection"""
    try:
        client = MongoClient(config('MONGO_CONNECTION_STRING', default='mongodb://localhost:27017/'), serverSelectionTimeoutMS=3000)
        client.server_info()
        print("✅ MongoDB: Connected")
        return True
    except Exception as e:
        print(f"❌ MongoDB: Failed - {e}")
        return False

def check_redis():
    """Check Redis connection"""
    try:
        # Without password
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        print("✅ Redis: Connected (no auth)")
        return True
    except:
        try:
            # With password from environment
            redis_url = config('REDIS_URL', default='redis://localhost:6379/1')
            r = redis.from_url(redis_url, decode_responses=True)
            r.ping()
            print("✅ Redis: Connected (with auth)")
            return True
        except Exception as e:
            print(f"❌ Redis: Failed - {e}")
            return False

def check_docker_services():
    """Check Docker services status"""
    try:
        result = subprocess.run(['docker', 'ps', '--format', 'table {{.Names}}\t{{.Status}}'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("\n🐳 Docker Services:")
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'myhours' in line:
                    print(f"   {line}")
        else:
            print("❌ Docker not available or no containers running")
    except:
        print("❌ Docker command failed")

def main():
    print("🔍 MyHours Services Status Check")
    print("=" * 40)
    
    # Check ports first
    print("\n📡 Port Connectivity:")
    ports = {
        'PostgreSQL (5432)': check_port('localhost', 5432),
        'MongoDB (27017)': check_port('localhost', 27017),
        'Redis (6379)': check_port('localhost', 6379),
        'Django (8000)': check_port('localhost', 8000)
    }
    
    for service, status in ports.items():
        status_icon = "✅" if status else "❌"
        print(f"   {status_icon} {service}")
    
    # Check actual connections
    print("\n🔗 Service Connections:")
    pg_ok = check_postgresql()
    mongo_ok = check_mongodb()
    redis_ok = check_redis()
    
    # Check Docker
    check_docker_services()
    
    # Summary
    print("\n📊 Summary:")
    all_ok = pg_ok and mongo_ok and redis_ok
    if all_ok:
        print("✅ All services are operational!")
    else:
        print("⚠️  Some services need attention:")
        if not pg_ok:
            print("   - Start PostgreSQL")
        if not mongo_ok:
            print("   - Start MongoDB")
        if not redis_ok:
            print("   - Start Redis")
    
    # Recommendations
    print("\n💡 Quick Fix:")
    print("   cd /Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend")
    print("   docker-compose up -d")
    
    return all_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)