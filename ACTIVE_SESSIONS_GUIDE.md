# Active Work Sessions Management Guide

This guide provides comprehensive methods to search for and manage active work sessions in the MyHours application database, particularly for admin users.

## Overview

Active work sessions are WorkLog entries that have a `check_in` time but no `check_out` time (check_out is NULL). These represent employees who are currently "clocked in" and working.

## Key Files and Models

### Models
- **WorkLog** (`worktime/models.py`): Stores work time entries
- **Employee** (`users/models.py`): Employee profiles with roles
- **User** (`django.contrib.auth.models.User`): Django user accounts

### Key Methods in WorkLog Model
- `is_current_session()`: Returns True if check_out is None
- `get_total_hours()`: Calculates duration from check_in to now (or check_out)
- `get_status()`: Returns "In Progress", "Approved", or "Pending Approval"

## Admin User Identification

Based on the codebase, admin users may have these emails:
- `admin@myhours.com` (primary admin from create_superuser.py)
- `admin2@example.com` (secondary admin from create_test_users.py)
- Any user with `role='admin'` in the Employee model

## Methods to Search for Active Sessions

### 1. Django Management Commands

#### List Active Sessions
```bash
# List all active sessions
python manage.py list_active_sessions

# List only admin sessions with details
python manage.py list_active_sessions --admin-only --detailed

# Get detailed view of all sessions
python manage.py list_active_sessions --detailed
```

#### Close Active Sessions
```bash
# Close all active sessions
python manage.py close_active_sessions --all

# Close sessions for specific employee
python manage.py close_active_sessions --employee-email admin@myhours.com

# Preview what would be closed (dry run)
python manage.py close_active_sessions --dry-run

# Close sessions for specific employee ID
python manage.py close_active_sessions --employee-id 1
```

### 2. Quick Check Scripts

#### Run Quick Session Check
```bash
python quick_session_check.py
```
This script provides a quick overview of all active sessions with admin detection.

#### Run Comprehensive Search
```bash
python search_admin_session.py
```
This script specifically searches for admin users and their active sessions.

### 3. Django Shell Commands

```bash
python manage.py shell
```

Then run these Python commands:

```python
from worktime.models import WorkLog
from users.models import Employee
from django.contrib.auth.models import User
from django.utils import timezone

# Find all active sessions
active_sessions = WorkLog.objects.filter(check_out__isnull=True)
print(f"Active sessions: {active_sessions.count()}")

# Find admin sessions
admin_sessions = WorkLog.objects.filter(
    check_out__isnull=True,
    employee__role='admin'
)
for session in admin_sessions:
    print(f"Admin: {session.employee.get_full_name()}")
    print(f"Started: {session.check_in}")
    print(f"Duration: {session.get_total_hours()} hours")

# Close a specific session
session = WorkLog.objects.get(id=SESSION_ID)  # Replace SESSION_ID
session.check_out = timezone.now()
session.save()

# Close all admin sessions
for session in admin_sessions:
    session.check_out = timezone.now()
    session.save()
```

### 4. API Endpoints

If the Django server is running:

#### Get Active Sessions
```bash
GET /api/worktime/worklogs/current_sessions/
```

#### Quick Checkout
```bash
POST /api/worktime/worklogs/quick_checkout/
Content-Type: application/json

{
    "employee_id": 1
}
```

### 5. Django Admin Interface

1. Navigate to: `http://localhost:8000/admin/`
2. Go to: `Worktime > Work logs`
3. Filter by: `check_out` is null
4. Edit sessions and add `check_out` time

### 6. Direct Database Queries

Use the SQL queries in `sql_queries.sql`:

```sql
-- Find all active sessions
SELECT 
    wl.id,
    e.first_name,
    e.last_name,
    e.email,
    e.role,
    wl.check_in,
    EXTRACT(EPOCH FROM (NOW() - wl.check_in))/3600 as duration_hours
FROM worktime_worklog wl
JOIN users_employee e ON wl.employee_id = e.id
WHERE wl.check_out IS NULL
ORDER BY wl.check_in DESC;

-- Close all active sessions (USE WITH CAUTION!)
UPDATE worktime_worklog SET check_out = NOW() WHERE check_out IS NULL;
```

## Common Admin Scenarios

### Scenario 1: Admin Forgot to Clock Out
```bash
# Find admin sessions
python manage.py list_active_sessions --admin-only --detailed

# Close specific admin session
python manage.py close_active_sessions --employee-email admin@myhours.com
```

### Scenario 2: Multiple Long-Running Sessions
```bash
# Check for long sessions (>12 hours)
python quick_session_check.py

# Close all sessions
python manage.py close_active_sessions --all
```

### Scenario 3: Database Cleanup
```bash
# Preview all active sessions
python manage.py close_active_sessions --dry-run

# Close after review
python manage.py close_active_sessions --all
```

## Files Created for Session Management

1. **Management Commands:**
   - `worktime/management/commands/list_active_sessions.py`
   - `worktime/management/commands/close_active_sessions.py`

2. **Utility Scripts:**
   - `search_admin_session.py` - Comprehensive admin session search
   - `quick_session_check.py` - Quick overview of all active sessions

3. **Database Resources:**
   - `sql_queries.sql` - Direct SQL queries for session management

4. **Documentation:**
   - `ACTIVE_SESSIONS_GUIDE.md` - This comprehensive guide

## Best Practices

1. **Always use dry-run first** to preview what will be closed
2. **Check session duration** before closing (avoid closing recent sessions)
3. **Verify admin user identity** before closing admin sessions
4. **Keep logs** of session closures for audit purposes
5. **Use management commands** instead of direct SQL when possible

## Troubleshooting

### No Active Sessions Found
- Check if employees are actually using the system
- Verify database connection
- Check if sessions were already closed

### Cannot Close Sessions
- Ensure Django environment is properly set up
- Check database permissions
- Verify model relationships are intact

### Long-Running Sessions
- Sessions over 12 hours may indicate forgotten checkouts
- Use the warning system in the scripts to identify these
- Consider implementing automatic checkout policies

## Security Notes

- Only admin users should have access to close other users' sessions
- Always verify the identity of the admin user before closing sessions
- Keep audit logs of session modifications
- Use authentication when accessing management commands in production