-- SQL queries to check and manage active work sessions
-- Use these queries if you need to access the database directly

-- 1. Find all active work sessions (check_in without check_out)
SELECT 
    wl.id,
    e.first_name,
    e.last_name,
    e.email,
    e.role,
    wl.check_in,
    wl.location_check_in,
    wl.notes,
    EXTRACT(EPOCH FROM (NOW() - wl.check_in))/3600 as duration_hours
FROM worktime_worklog wl
JOIN users_employee e ON wl.employee_id = e.id
WHERE wl.check_out IS NULL
ORDER BY wl.check_in DESC;

-- 2. Find only admin users with active sessions
SELECT 
    wl.id,
    e.first_name,
    e.last_name,
    e.email,
    wl.check_in,
    EXTRACT(EPOCH FROM (NOW() - wl.check_in))/3600 as duration_hours
FROM worktime_worklog wl
JOIN users_employee e ON wl.employee_id = e.id
WHERE wl.check_out IS NULL 
AND e.role = 'admin'
ORDER BY wl.check_in DESC;

-- 3. Count active sessions by role
SELECT 
    e.role,
    COUNT(*) as active_sessions,
    AVG(EXTRACT(EPOCH FROM (NOW() - wl.check_in))/3600) as avg_duration_hours
FROM worktime_worklog wl
JOIN users_employee e ON wl.employee_id = e.id
WHERE wl.check_out IS NULL
GROUP BY e.role
ORDER BY active_sessions DESC;

-- 4. Find sessions longer than 12 hours
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
AND EXTRACT(EPOCH FROM (NOW() - wl.check_in))/3600 > 12
ORDER BY duration_hours DESC;

-- 5. CLOSE ALL ACTIVE SESSIONS (USE WITH CAUTION!)
-- This will close all active sessions with current timestamp
-- Uncomment the line below only if you want to close ALL active sessions:
-- UPDATE worktime_worklog SET check_out = NOW() WHERE check_out IS NULL;

-- 6. Close sessions for specific employee by email
-- Replace 'admin@myhours.com' with the actual email
-- UPDATE worktime_worklog 
-- SET check_out = NOW() 
-- WHERE check_out IS NULL 
-- AND employee_id IN (
--     SELECT id FROM users_employee WHERE email = 'admin@myhours.com'
-- );

-- 7. Close specific session by ID
-- Replace 123 with the actual session ID
-- UPDATE worktime_worklog SET check_out = NOW() WHERE id = 123;

-- 8. Get recent activity for an employee
SELECT 
    wl.id,
    wl.check_in,
    wl.check_out,
    CASE 
        WHEN wl.check_out IS NULL THEN 'ACTIVE'
        ELSE 'COMPLETED'
    END as status,
    CASE 
        WHEN wl.check_out IS NULL THEN EXTRACT(EPOCH FROM (NOW() - wl.check_in))/3600
        ELSE EXTRACT(EPOCH FROM (wl.check_out - wl.check_in))/3600
    END as duration_hours
FROM worktime_worklog wl
JOIN users_employee e ON wl.employee_id = e.id
WHERE e.email = 'admin@myhours.com'  -- Replace with target email
ORDER BY wl.check_in DESC
LIMIT 10;