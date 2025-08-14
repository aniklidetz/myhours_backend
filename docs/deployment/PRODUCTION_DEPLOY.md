# Production Deployment Guide

## Security Configuration

### 1. Generate Secure SECRET_KEY

```bash
# Generate 64-character secure key
python -c "import secrets, string; alphabet = string.ascii_letters + string.digits + string.punctuation; print(''.join(secrets.choice(alphabet) for _ in range(64)))"
```

### 2. Environment Variables

Set these in your production environment:

```bash
# CRITICAL: Never commit these to repository
export DJANGO_SECRET_KEY="your-64-character-secure-key-here"
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
export REDIS_URL="redis://host:6379/0"
export DEBUG="False"
export ALLOWED_HOSTS="yourdomain.com,www.yourdomain.com"

# Email settings (optional)
export EMAIL_HOST="smtp.gmail.com"
export EMAIL_HOST_USER="your-email@gmail.com" 
export EMAIL_HOST_PASSWORD="your-app-password"
```

### 3. Deploy with Production Settings

```bash
# Use production settings
export DJANGO_SETTINGS_MODULE="myhours.settings_prod"

# Run security checks
python manage.py check --deploy

# Collect static files
python manage.py collectstatic --noinput

# Run migrations
python manage.py migrate

# Start production server
gunicorn myhours.wsgi:application
```

## HTTPS/HSTS Configuration

The `settings_prod.py` includes:

- `SECURE_SSL_REDIRECT = True` - Forces HTTPS
- `SECURE_HSTS_SECONDS = 31536000` - 1 year HSTS
- `SECURE_HSTS_INCLUDE_SUBDOMAINS = True` - Covers subdomains  
- `SECURE_HSTS_PRELOAD = True` - Enables browser preload

**⚠️ IMPORTANT**: Only enable HSTS when your entire site (including subdomains) is HTTPS-ready. Once enabled, browsers will refuse HTTP connections.

### Behind Proxy/Load Balancer

If using nginx, AWS ALB, etc., uncomment this line in `settings_prod.py`:

```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

## GitHub Actions Secrets

In your repository settings → Secrets, add:

- `DJANGO_SECRET_KEY` - Your 64-character key
- `DATABASE_URL` - Production database connection
- `REDIS_URL` - Redis connection string
- Email settings (if using email features)

## File Structure

```
myhours/
├── settings.py          # Development (current)
├── settings_ci.py       # CI/CD testing  
└── settings_prod.py     # Production (new)
```

## Verification

Test your production config:

```bash
DJANGO_SETTINGS_MODULE=myhours.settings_prod python manage.py check --deploy
```

Should show only minor warnings, no errors about SECRET_KEY or HSTS.