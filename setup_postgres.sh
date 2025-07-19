#!/bin/bash

# Setup PostgreSQL for MyHours backend

echo "🔧 Setting up PostgreSQL configuration..."

# Export database URL for Django
export DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db"

# Alternatively, set individual variables
export DB_ENGINE="django.db.backends.postgresql"
export DB_NAME="myhours_db"
export DB_USER="myhours_user"
export DB_PASSWORD="secure_password_123"
export DB_HOST="localhost"
export DB_PORT="5432"

echo "✅ PostgreSQL environment variables set"
echo ""
echo "To make this permanent, add to your .env file:"
echo "DATABASE_URL=postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db"
echo ""
echo "Or add:"
echo "DB_ENGINE=django.db.backends.postgresql"
echo ""
echo "Then run:"
echo "python manage.py migrate"
echo "python manage.py migrate --run-syncdb"