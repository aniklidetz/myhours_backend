
# 🚀 MyHours - Employee Time Tracking System

Complete biometric-enabled time tracking system with Docker DevOps deployment.

## ⚡ One-Command Setup

```bash
make setup
```

That's it! This single command will:
- Create environment configuration
- Build all Docker services  
- Start PostgreSQL, MongoDB, Redis, Django, and Celery
- Run database migrations
- Seed test data
- Show you all service URLs

## 🌐 Access Your Application

After `make setup` completes:

- **🌐 Web App**: http://localhost:8000
- **👑 Admin Panel**: http://localhost:8000/admin/ (`admin` / `admin123`)
- **📚 API Docs**: http://localhost:8000/api/schema/swagger/
- **💓 Health Check**: http://localhost:8000/health/

## 🐳 DevOps Commands

```bash
make up              # Start all services
make down            # Stop all services  
make logs            # View live logs
make status          # Service status
make health          # Health check
make clean           # Reset everything
make backup          # Backup databases
```

## 🏗️ Manual Setup (Alternative)

If you prefer manual setup:

```bash
# 1. Environment
make env-setup
# Edit .env file with your settings

# 2. Build & Start
make build
make up

# 3. Database
make migrate
make superuser
```

### 🏗️ Architecture

users: Employee management  
worktime: Time tracking with geolocation  
payroll: Israeli labor law compliant calculations  
biometrics: Face recognition authentication  
integrations: Holiday calendar services  

### 🛡️ Security Features

Environment-based configuration  
Secure password storage  
CORS enabled for React Native  
Input validation and sanitization  

### 📱 Frontend

React Native app located in ../myhours-app/
