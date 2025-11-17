# Database Index Implementation Guide

This guide provides ready-to-use code for adding missing indexes to the MyHours project.

## File Locations to Update

- `/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend/users/token_models.py`
- `/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend/users/models.py`
- `/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend/biometrics/models.py`
- `/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend/payroll/models.py`

---

## PHASE 1: CRITICAL (Implement First)

### 1. BiometricSession (users/token_models.py)

**Current Status:** No indexes

**Add this to the Meta class:**

```python
class BiometricSession(models.Model):
    # ... existing fields ...
    
    class Meta:
        ordering = ["-started_at"]
        # ADD THESE INDEXES:
        indexes = [
            models.Index(fields=["device_token"]),
            models.Index(fields=["device_token", "is_active", "expires_at"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["-started_at"]),
        ]
```

**Why:** Every authentication check queries this table. Missing indexes cause full table scans.

---

### 2. BiometricAttempt (biometrics/models.py)

**Current Status:** No indexes

**Add this to the Meta class:**

```python
class BiometricAttempt(models.Model):
    # ... existing fields ...
    
    class Meta:
        db_table = "biometric_attempts"
        verbose_name = "Biometric Attempt"
        verbose_name_plural = "Biometric Attempts"
        # ADD THESE INDEXES:
        indexes = [
            models.Index(fields=["ip_address"]),
            models.Index(fields=["ip_address", "blocked_until"]),
            models.Index(fields=["blocked_until"]),
            models.Index(fields=["last_attempt"]),
        ]
```

**Why:** Rate limiting depends on fast IP lookups. Security vulnerability without these indexes.

---

### 3. TokenRefreshLog (users/token_models.py)

**Current Status:** No indexes

**Add this to the Meta class:**

```python
class TokenRefreshLog(models.Model):
    # ... existing fields ...
    
    class Meta:
        ordering = ["-refreshed_at"]
        # ADD THESE INDEXES:
        indexes = [
            models.Index(fields=["device_token"]),
            models.Index(fields=["device_token", "-refreshed_at"]),
            models.Index(fields=["-refreshed_at"]),
        ]
```

**Why:** Used for security monitoring and audit trails. Queries need index support.

---

### 4. BiometricProfile (biometrics/models.py)

**Current Status:** No indexes

**Add this to the Meta class:**

```python
class BiometricProfile(models.Model):
    # ... existing fields ...
    
    class Meta:
        db_table = "biometric_profiles"
        verbose_name = "Biometric Profile"
        verbose_name_plural = "Biometric Profiles"
        # ADD THESE INDEXES:
        indexes = [
            models.Index(fields=["employee"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["-last_updated"]),
            models.Index(fields=["created_at"]),
        ]
```

**Why:** N+1 query problem detected. Employee FK must be indexed.

---

## PHASE 2: HIGH PRIORITY

### 5. Salary (payroll/models.py)

**Current Status:** No indexes (constraint exists but doesn't help)

**Find the existing Meta class and add indexes:**

```python
class Salary(models.Model):
    # ... existing fields ...
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(is_active=True),
                name="unique_active_salary_per_employee",
            )
        ]
        # ADD THESE INDEXES:
        indexes = [
            models.Index(fields=["employee", "is_active"]),  # MOST CRITICAL
            models.Index(fields=["employee"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["-created_at"]),
        ]
```

**Why:** Payroll calculations query this constantly. Missing composite index causes full table scans.

---

### 6. CompensatoryDay (payroll/models.py)

**Current Status:** No Meta class with indexes

**Add Meta class:**

```python
class CompensatoryDay(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="compensatory_days"
    )
    date_earned = models.DateField()
    reason = models.CharField(
        max_length=50,
        choices=[("shabbat", "Work on Shabbat"), ("holiday", "Work on Holiday")],
    )
    date_used = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ADD THIS META CLASS:
    class Meta:
        verbose_name = "Compensatory Day"
        verbose_name_plural = "Compensatory Days"
        ordering = ["-date_earned"]
        indexes = [
            models.Index(fields=["employee", "date_used"]),
            models.Index(fields=["employee"]),
            models.Index(fields=["-date_earned"]),
        ]

    def __str__(self):
        status = "Used" if self.date_used else "Not used"
        return f"{self.employee} - {self.get_reason_display()} ({status})"
```

**Why:** Employee FK queries without index impact payroll performance.

---

### 7. Employee (users/models.py)

**Current Status:** Has 4 indexes, missing 2 critical ones

**Find the existing indexes list and add:**

```python
class Employee(models.Model):
    # ... existing fields ...
    
    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        default_related_name = "employees"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["role"]),
            models.Index(fields=["employment_type"]),
            # ADD THESE TWO:
            models.Index(fields=["user"]),
            models.Index(fields=["-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "employment_type"],
                name="uniq_user_employment_type",
            )
        ]
```

**Why:** User FK lookups are common in auth flows. Created_at used for pagination.

---

## PHASE 3: MEDIUM PRIORITY (Optional)

### 8. BiometricLog (biometrics/models.py)

**Current Status:** Has 3 indexes, add 1 optional

**Find existing indexes and add:**

```python
class BiometricLog(models.Model):
    # ... existing fields ...
    
    class Meta:
        db_table = "biometric_logs"
        verbose_name = "Biometric Log"
        verbose_name_plural = "Biometric Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employee", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["success", "-created_at"]),
            # ADD THIS OPTIONAL INDEX:
            models.Index(fields=["success"]),
        ]
```

**Why:** Optimize failed attempt filtering without sorting.

---

### 9. EmployeeInvitation (users/models.py)

**Current Status:** Has 2 indexes, add 1 optional

**Find existing indexes and add:**

```python
class EmployeeInvitation(models.Model):
    # ... existing fields ...
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["expires_at"]),
            # ADD THIS OPTIONAL INDEX:
            models.Index(fields=["accepted_at", "expires_at"]),
        ]
```

**Why:** Optimize pending invitation queries (accepted_at=None, expires_at>now).

---

### 10. DailyPayrollCalculation (payroll/models.py)

**Current Status:** Has 4 indexes, add 1 optional

**Find existing indexes and add:**

```python
class DailyPayrollCalculation(models.Model):
    # ... existing fields ...
    
    class Meta:
        verbose_name = "Daily Payroll Calculation"
        verbose_name_plural = "Daily Payroll Calculations"
        ordering = ["-work_date", "worklog_id"]
        indexes = [
            models.Index(fields=["employee", "work_date"]),
            models.Index(fields=["work_date"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["worklog"]),
            # ADD THIS OPTIONAL INDEX:
            models.Index(fields=["employee", "-work_date"]),
        ]
```

**Why:** Optimize "recent calculations for employee" queries.

---

## Migration Steps

### Step 1: Update Model Files

Apply all code changes above to the respective model files.

### Step 2: Create Migrations

```bash
cd /Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend/

# Create migrations for each app
python manage.py makemigrations users
python manage.py makemigrations biometrics
python manage.py makemigrations payroll

# Review the migration files before applying
# They should be in:
# - users/migrations/000X_*.py
# - biometrics/migrations/000X_*.py
# - payroll/migrations/000X_*.py
```

### Step 3: Test Migrations

```bash
# Check what will be applied
python manage.py migrate --plan

# Apply migrations to dev database first
python manage.py migrate
```

### Step 4: Verify Indexes Created

#### PostgreSQL:
```bash
python manage.py dbshell

# View all indexes for a table
\d biometric_sessions
\d biometric_attempts
\d token_refresh_logs
\d biometric_profiles
\d salary
\d compensatory_days
```

#### MySQL:
```bash
python manage.py dbshell

# View all indexes
SHOW CREATE TABLE biometric_sessions;
SHOW INDEX FROM biometric_sessions;
```

### Step 5: Monitor Performance

```python
# Test script to compare performance before/after
python manage.py shell

from django.db import connection
from django.test.utils import CaptureQueriesContext
from users.models import Employee
from biometrics.models import BiometricSession, BiometricAttempt
import time

# Example: Test BiometricSession query
with CaptureQueriesContext(connection) as ctx:
    sessions = list(BiometricSession.objects.filter(is_active=True))
    
print(f"Queries executed: {len(ctx.captured_queries)}")
print(f"First query: {ctx.captured_queries[0]['sql'][:200]}")
```

---

## Deployment Checklist

- [ ] All model files updated with new indexes
- [ ] Migrations created and reviewed
- [ ] Tested on development database
- [ ] Indexes verified in dev database
- [ ] Performance tested (queries faster?)
- [ ] Backup taken before production migration
- [ ] Production migration applied (during off-hours)
- [ ] Monitoring enabled for slow queries
- [ ] Index usage verified in production
- [ ] Document deployment in changelog

---

## Rollback Plan (If Needed)

```bash
# If something goes wrong, you can reverse the migration
python manage.py migrate <app_name> <previous_migration_number>

# Example:
python manage.py migrate users 0002_previous_migration
```

---

## Performance Validation Queries

Run these before and after to verify improvement:

```python
from django.db import connection
from django.test.utils import CaptureQueriesContext
from biometrics.models import BiometricSession, BiometricAttempt, BiometricProfile
from payroll.models import Salary, CompensatoryDay
from users.models import Employee
from django.utils import timezone

print("=" * 60)
print("PERFORMANCE TEST: Before/After Index Implementation")
print("=" * 60)

# Test 1: BiometricSession
print("\n1. BiometricSession - device_token lookup:")
with CaptureQueriesContext(connection) as ctx:
    sessions = list(BiometricSession.objects.filter(is_active=True, expires_at__gt=timezone.now())[:10])
print(f"   Queries: {len(ctx.captured_queries)}")
print(f"   Time: {sum(q.get('time', 0) for q in ctx.captured_queries):.4f}s")

# Test 2: BiometricAttempt
print("\n2. BiometricAttempt - IP address lookup:")
with CaptureQueriesContext(connection) as ctx:
    attempt = BiometricAttempt.objects.filter(ip_address="127.0.0.1").first()
print(f"   Queries: {len(ctx.captured_queries)}")

# Test 3: Salary
print("\n3. Salary - active lookup:")
with CaptureQueriesContext(connection) as ctx:
    salaries = list(Salary.objects.filter(employee_id=1, is_active=True)[:10])
print(f"   Queries: {len(ctx.captured_queries)}")

# Test 4: CompensatoryDay
print("\n4. CompensatoryDay - employee unused days:")
with CaptureQueriesContext(connection) as ctx:
    days = list(CompensatoryDay.objects.filter(employee_id=1, date_used__isnull=True))
print(f"   Queries: {len(ctx.captured_queries)}")

# Test 5: Employee
print("\n5. Employee - user FK lookup:")
with CaptureQueriesContext(connection) as ctx:
    employees = list(Employee.objects.filter(user_id=1)[:10])
print(f"   Queries: {len(ctx.captured_queries)}")

print("\n" + "=" * 60)
print("All queries should use indexes (check execution plans)")
print("=" * 60)
```

---

## Common Issues & Solutions

### Issue: Migration fails with "Index already exists"
**Solution:** Indexes might be partially created. Run:
```bash
python manage.py migrate --fake users 0001
python manage.py migrate users
```

### Issue: Database locks during migration
**Solution:** Run during off-hours. Use:
```bash
python manage.py migrate --no-input
```

### Issue: Index not being used (EXPLAIN ANALYZE shows full table scan)
**Solution:** 
- Analyze statistics: `ANALYZE table_name;` (PostgreSQL)
- Check index definition: `\d table_name` (PostgreSQL)
- Verify index names don't conflict with Django conventions

### Issue: Performance hasn't improved
**Solution:**
- Check that queries are actually hitting the indexed fields
- Verify query optimization with EXPLAIN ANALYZE
- May need composite index in different order
- Check table statistics are updated

---

## Next Steps

1. Implement Phase 1 (CRITICAL) first - these are security-critical
2. Test thoroughly in development
3. Deploy to staging for validation
4. Schedule production deployment during maintenance window
5. Monitor slow query logs after deployment
6. Document any performance improvements observed

---

**Report Generated:** 2025-11-15
**Full Analysis:** DATABASE_INDEX_ANALYSIS.md
