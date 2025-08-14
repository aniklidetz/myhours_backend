# 📧 Employee Invitation System

## Overview

The MyHours application now features a secure invitation system for onboarding new employees. Instead of manually creating user accounts, administrators can send email invitations that allow employees to self-register.

## 🔄 Invitation Flow

### 1. **Admin Creates Employee** (without user account)
```bash
POST /api/v1/users/employees/
{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "employment_type": "hourly",
  "hourly_rate": 50.00,
  "role": "employee"
}
```

### 2. **Admin Sends Invitation**
```bash
POST /api/v1/users/employees/{employee_id}/send_invitation/
{
  "base_url": "http://localhost:8100"  # Frontend URL
}
```

Response:
```json
{
  "id": 1,
  "employee": 5,
  "employee_name": "John Doe",
  "employee_email": "john.doe@example.com",
  "token": "secure_random_token_here",
  "expires_at": "2025-01-08T12:00:00Z",
  "email_sent": true
}
```

### 3. **Employee Receives Email**
```
Subject: Welcome to MyHours - Complete Your Registration

Hi John,

You've been invited to join the MyHours time tracking system.

Click here to set up your account:
http://localhost:8100/invite?token=secure_random_token_here

This link expires in 48 hours.

Best regards,
MyHours Team
```

### 4. **Employee Validates Invitation**
```bash
GET /api/v1/users/invitation/validate/?token=secure_random_token_here
```

Response:
```json
{
  "valid": true,
  "employee": {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com"
  },
  "expires_at": "2025-01-08T12:00:00Z"
}
```

### 5. **Employee Accepts Invitation**
```bash
POST /api/v1/users/invitation/accept/
{
  "token": "secure_random_token_here",
  "username": "johndoe",
  "password": "SecurePassword123!",
  "confirm_password": "SecurePassword123!"
}
```

Response:
```json
{
  "user": {
    "id": 10,
    "username": "johndoe",
    "email": "john.doe@example.com",
    "first_name": "John",
    "last_name": "Doe"
  },
  "employee_id": 5,
  "token": "auth_token_here",
  "message": "Account created successfully. Please register your biometric data."
}
```

### 6. **Employee Registers Biometrics**
After accepting the invitation, the employee is automatically logged in and directed to register their biometric data (face).

## 🛠️ Technical Implementation

### Database Models

**Employee Model** (updated):
- `user` field is now nullable (NULL until invitation accepted)
- Added properties: `is_registered`, `has_biometric`
- No automatic user creation in `save()` method

**EmployeeInvitation Model** (new):
```python
- employee (OneToOne)
- token (unique, secure)
- invited_by (User)
- created_at
- expires_at
- accepted_at
- email_sent
- email_sent_at
```

### API Endpoints

1. **Send Invitation**: `POST /api/v1/users/employees/{id}/send_invitation/`
2. **Validate Token**: `GET /api/v1/users/invitation/validate/?token={token}`
3. **Accept Invitation**: `POST /api/v1/users/invitation/accept/`

### Security Features

- ✅ Secure random tokens (64 characters)
- ✅ Token expiration (48 hours by default)
- ✅ One-time use tokens
- ✅ Rate limiting on invitation endpoints
- ✅ Admin-only invitation sending

## 📱 Frontend Integration

### Required Screens

1. **Employee List** - Show invitation status
2. **Send Invitation** - Button on employee details
3. **Accept Invitation** - New screen for token validation
4. **Registration Form** - Username/password setup
5. **Biometric Registration** - Redirect after account creation

### URL Routing

```javascript
// Add to your React Native router
'/invite' - Invitation acceptance flow
'/register-biometric' - Biometric registration after account creation
```

## 🔧 Testing the Flow

### Via Django Admin

1. Login to admin: http://localhost:8000/admin/
2. Create new Employee (without user)
3. Go to Employee Invitations
4. Check the generated token
5. Use the token in API calls

### Via API (Postman/curl)

```bash
# 1. Create employee
curl -X POST http://localhost:8000/api/v1/users/employees/ \
  -H "Authorization: Token admin_token" \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Test","last_name":"User","email":"test@example.com"}'

# 2. Send invitation
curl -X POST http://localhost:8000/api/v1/users/employees/{id}/send_invitation/ \
  -H "Authorization: Token admin_token"

# 3. Check invitation URL in logs
# 4. Use token to validate and accept
```

## 📝 Email Configuration (TODO)

Currently, emails are logged instead of sent. To enable real email:

1. Configure email backend in settings.py
2. Add email templates
3. Update `send_invitation` method to use `send_mail()`

Example settings:
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
```

## 🎯 Benefits

1. **Security**: No manual password creation by admin
2. **User Experience**: Employees choose their own credentials
3. **Scalability**: Automated onboarding process
4. **Audit Trail**: Track who invited whom and when
5. **Flexibility**: Resend invitations if needed