-- Quick SQL script to close admin's long-running session
-- Run this with: psql -d myhours_db -U myhours_user -f close_admin_sql.sql

-- First, check what active sessions exist
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

-- Close sessions for admin@example.com that are longer than 100 hours
UPDATE worktime_worklog 
SET check_out = NOW() 
WHERE check_out IS NULL 
AND employee_id IN (
    SELECT id FROM users_employee WHERE email = 'admin@example.com'
)
AND EXTRACT(EPOCH FROM (NOW() - check_in))/3600 > 100;

-- Show what was closed
SELECT 
    'Closed sessions for admin@example.com:' as message,
    COUNT(*) as sessions_closed
FROM worktime_worklog wl
JOIN users_employee e ON wl.employee_id = e.id
WHERE e.email = 'admin@example.com'
AND wl.check_out IS NOT NULL
AND wl.check_out::date = NOW()::date;