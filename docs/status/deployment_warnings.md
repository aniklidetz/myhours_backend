# Deployment Warnings Documentation

## Current Status
As of August 11, 2025, the application passes all critical checks but has some non-critical warnings related to API documentation and production security settings.

## Non-Critical Warnings

### 1. DRF Spectacular (API Documentation)
**Count:** 71 warnings  
**Impact:** None on functionality, only affects auto-generated API documentation  
**Cause:** Custom authentication classes and API views without explicit serializers

#### Affected Components:
- `HybridAuthentication` class needs OpenAPI extension
- `DeviceTokenAuthentication` class needs OpenAPI extension  
- Various API views need explicit serializer classes for documentation

#### Resolution (Optional):
```python
# Add to users/authentication.py
from drf_spectacular.extensions import OpenApiAuthenticationExtension

class HybridAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'users.authentication.HybridAuthentication'
    name = 'HybridAuth'
    
    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
        }
```

### 2. Security Warnings (Production Only)

#### SECRET_KEY Warning
**Current:** Using development SECRET_KEY  
**Production Fix:** Generate a secure key with:
```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

#### HSTS Preload Warning
**Current:** `SECURE_HSTS_PRELOAD = False`  
**Production Fix:** Set to `True` in production settings after ensuring HTTPS is properly configured

## Summary
- **73 total issues** identified
- **0 critical issues**
- **All warnings are either:**
  - API documentation related (not affecting functionality)
  - Production security settings (not needed for development)

## Verification Commands
```bash
# Check deployment readiness
python manage.py check --deploy

# Check without deployment-specific warnings
python manage.py check

# Run tests to verify functionality
pytest --tb=short -q
```

## Production Deployment Checklist
When deploying to production, address:
1. [ ] Generate secure SECRET_KEY
2. [ ] Enable SECURE_HSTS_PRELOAD
3. [ ] Configure proper ALLOWED_HOSTS
4. [ ] Set DEBUG = False
5. [ ] Configure production database
6. [ ] Set up proper logging
7. [ ] Configure CORS properly
8. [ ] Set up SSL/TLS certificates