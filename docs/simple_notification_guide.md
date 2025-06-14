# Simple Notification System for MyHours

## What is it?

Simplified push notification system without blocking and complex settings.

## What it does:

### 1. 📱 Push notifications for:
- **Overtime**: When employee worked more than 8 hours
- **Long workday**: When worked 10+ hours
- **Approaching limit**: When approaching 12 hours
- **Holiday work**: Reminder about compensation
- **High weekly workload**: At 55+ hours per week
- **Critical weekly hours**: At 60+ hours per week (requires approval)

### 2. ✅ What it does NOT do:
- ❌ Does not block check-in/check-out
- ❌ Does not require complex settings
- ❌ Does not create critical errors
- ❌ Does not interfere with work

## How it works:

### Files:
- `worktime/simple_notifications.py` - main logic
- `worktime/simple_signals.py` - automatic notifications
- Added `send_simple_notifications()` method to `WorkLog`

### Example notifications:

```
📱 "Long Workday"
   "You have worked 10.5 hours. Don't forget to rest!"

📱 "⚠️ Approaching Daily Limit"
   "You have worked 11.5 hours today. Consider ending your workday."

📱 "Overtime Hours"
   "Today you worked 2.5 hours of overtime."

📱 "Holiday Work"
   "You are working on Shavuot. You are entitled to compensatory time off."

📱 "🚨 Critical Weekly Hours"
   "You have worked 62 hours this week. This exceeds recommended limits."
```

## Implementation:

### 1. Connect push service (Firebase/OneSignal):
```python
# In simple_notifications.py replace:
def _send_push(employee, title, message):
    # Instead of print() call real API
    firebase_token = employee.device_token
    if firebase_token:
        send_firebase_notification(firebase_token, title, message)
```

### 2. Add device_token to Employee model:
```python
class Employee(models.Model):
    # ... existing fields
    device_token = models.CharField(max_length=255, blank=True)
```

### 3. Automatically call on check-in/check-out:
```python
# Already implemented in simple_signals.py
# Automatically triggers when WorkLog is saved
```

## Benefits of simple system:

1. **Minimal complexity** - just one logic file
2. **Does not interfere** - no blocking
3. **Easy to configure** - just connect push service
4. **Practical** - only needed notifications
5. **No database required** - all in code

## Testing:

```bash
# Run demo
docker-compose exec web python demo_simple_notifications.py

# Or test with real data
docker-compose exec web python -c "
from worktime.simple_notifications import SimpleNotificationService
from users.models import Employee
emp = Employee.objects.first()
SimpleNotificationService.check_daily_hours(emp, work_log)
"
```

## Result:

✅ Employees receive useful notifications
✅ Managers know about violations
✅ System does not interfere with work
✅ Simple implementation and maintenance

This is a practical solution without unnecessary complexity!