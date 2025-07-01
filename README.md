
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

## 🧪 Test Data

### Employee Seeder

Create 10 diverse Israeli test employees with realistic work patterns:

```bash
# Create employees only
python manage.py seed_employees

# Create employees with work logs for last 3 weeks
python manage.py seed_employees --with-worklogs

# Reset and recreate all test data
python manage.py seed_employees --clear --with-worklogs
```

**Created Employee Types:**
- **Hourly (4 employees)**: ₪45-120/hour with different overtime patterns
- **Monthly (3 employees)**: ₪18,000-25,000/month with fixed salaries  
- **Project (3 employees)**: ₪8,000-45,000/project with various contract lengths

**Work Patterns:**
- `overtime_lover` - Frequent 10-12 hour days (Yosef)
- `part_time` - 4 days per week (Dana)
- `night_shifts` - 22:00-06:00 schedule (Itai)
- `sabbath_worker` - Weekend work included (Leah)
- `flexible_hours` - Irregular schedule (Noam)
- `business_trips` - Travel days and long client meetings (Elior)
- `long_sprints` - 2-month project cycles (Yael)
- `short_projects` - 1-2 week contracts (Gilad)
- `remote_work` - Fully remote (Maya)
- `student_hours` - 3 hours/day afternoon work (Omer)

**Work Log Features:**
- Generates 2-3 weeks of realistic work history
- Pattern-specific schedules and locations
- Overtime, holiday, and Shabbat work scenarios
- Idempotent - safe to run multiple times

**Salary Validation:**
- **Hourly**: Only `hourly_rate` field, `base_salary` = null
- **Monthly**: Only `base_salary` field, `hourly_rate` = null  
- **Project**: Either `base_salary` OR `hourly_rate`, not both

### Testing

All employees created with:
- **Email**: `{name}@test.com` 
- **Password**: `test123`
- **Names**: Realistic Hebrew names (Yosef Abramov, Dana Azulay, etc.)

## ⚙️ Feature Flags

### Project Payroll

Control project-based salary calculations with the `ENABLE_PROJECT_PAYROLL` feature flag:

```bash
# Disable project payroll (default)
ENABLE_PROJECT_PAYROLL=false

# Enable project payroll  
ENABLE_PROJECT_PAYROLL=true
```

**When disabled (`false`):**
- ❌ Project calculation type hidden from Django Admin
- ❌ API returns `400 Bad Request` for project salary creation
- ⚠️ Existing project salaries remain accessible (legacy mode)
- 🔄 Seeder converts project employees to hourly/monthly equivalents

**When enabled (`true`):**
- ✅ Full project payroll functionality available
- ✅ Admin interface shows project options
- ✅ API accepts project salary creation
- ✅ Seeder creates original project employees

**Use cases:**
- **Production**: Keep disabled until needed
- **Testing**: Enable to test project functionality
- **Client onboarding**: Enable when contractor joins

This allows hiding unused functionality without database changes or code removal.

### 📱 Frontend

React Native app located in ../myhours-app/
