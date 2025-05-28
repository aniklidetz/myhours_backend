
# MyHours - Employee Time Tracking System

## 🚀 Quick Setup

### 1. Clone and Setup Environment
```
git clone <your-repo-url>
cd myhours-backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```
### 2. Install Dependencies
```install -r requirements.txt```
### 3. Configure Environment
```.env.example .env # Edit .env with your configuration```
### 4. Generate SECRET_KEY
```python manage.py shell -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" # Copy the output to SECRET_KEY in .env```
### 5. Database Setup
```
python manage.py migrate
python manage.py createsuperuser```
### 6. Run Development Server
```bash python manage.py runserver```

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
