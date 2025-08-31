# Authentication and Cache Collision Fix

## Issues Identified

1. **Frontend cache collision**: 8-character token prefixes can theoretically collide
2. **Cross-user data contamination**: Dashboard shows wrong user's hours
3. **Token mapping issues**: Users seeing cached data from other users

## Root Cause

The frontend API service uses token prefixes for caching:
```javascript
const userCacheKey = `${APP_CONFIG.STORAGE_KEYS.EMPLOYEES_CACHE}_${token?.substring(0, 8) || 'anonymous'}`;
```

This creates the possibility of cache collisions where two users share the same cache data.

## Solution Implementation

### 1. Fix Frontend Cache Key Generation

Replace the 8-character prefix with a more robust user-specific key:

**File:** `/Users/aniklidetz/Documents/MyPythonProject/MyHours/frontend2/myhours-app/src/api/apiService.js`

**Change line 401 from:**
```javascript
const userCacheKey = `${APP_CONFIG.STORAGE_KEYS.EMPLOYEES_CACHE}_${token?.substring(0, 8) || 'anonymous'}`;
```

**To:**
```javascript
// Use user ID + first 8 chars of token for better collision resistance
const userData = await SecureStorageManager.getItem(APP_CONFIG.STORAGE_KEYS.USER_DATA);
const userId = userData ? JSON.parse(userData).id : 'anonymous';
const tokenPrefix = token?.substring(0, 8) || 'anonymous';
const userCacheKey = `${APP_CONFIG.STORAGE_KEYS.EMPLOYEES_CACHE}_${userId}_${tokenPrefix}`;
```

### 2. Update Cache Cleanup Logic

Update the UserContext logout function to handle the new cache key format:

**File:** `/Users/aniklidetz/Documents/MyPythonProject/MyHours/frontend2/myhours-app/src/contexts/UserContext.js`

**Update the cache cleanup sections (lines 180-186, 208-213, 240-245, 266-272) to use the user-specific format.**

### 3. Add Explicit Employee Filtering

Fix the dashboard hours calculation to pass explicit employee filtering:

**File:** `/Users/aniklidetz/Documents/MyPythonProject/MyHours/frontend2/myhours-app/app/employees.js`

**Change lines 115-122 from:**
```javascript
const workLogs = await ApiService.worktime.getLogs({
  date: today,
  // Don't pass employee param - let backend determine from token
  page_size: 50
});
```

**To:**
```javascript
const workLogs = await ApiService.worktime.getLogs({
  date: today,
  employee: user.employee_id || user.id, // Explicitly filter by current user
  page_size: 50
});
```

### 4. Backend Authentication Validation

Add additional validation in the backend worktime views:

**File:** `/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend/worktime/views.py`

**Add after line 116:**
```python
# Additional security check: Log potential cross-user data access
if employee_filter and request.user.is_authenticated:
    try:
        employee_profile = request.user.employees.first()
        if employee_profile:
            # If a specific employee is requested and it's not the current user (unless admin/accountant)
            if (employee_filter != str(employee_profile.id) and 
                employee_profile.role not in ['admin', 'accountant']):
                logger.warning(
                    f"SECURITY: User {request.user.username} (role: {employee_profile.role}) "
                    f"attempted to access employee {employee_filter} data"
                )
    except Exception as e:
        logger.error(f"Error validating employee filter access: {e}")
```

## Testing Steps

1. Clear all app cache and storage
2. Login as different users on the same device
3. Verify each user sees only their own data
4. Check that accountants can see all employees (23 total)
5. Verify dashboard shows correct user's hours

## Security Benefits

1. **Collision resistance**: User ID + token prefix makes collisions extremely unlikely
2. **User isolation**: Each user has completely separate cache spaces
3. **Audit trail**: Backend logs potential cross-user access attempts
4. **Explicit filtering**: Frontend explicitly requests user-specific data

## Rollback Plan

If issues arise, the changes can be easily reverted by:
1. Restoring the original 8-character prefix caching
2. Removing the employee filter parameter
3. Clearing all app cache to start fresh