-- Cleanup script for test payroll data
-- This script removes obviously fake/test salary data that inflates payroll calculations

-- Show current salary data before cleanup
SELECT 'BEFORE CLEANUP - Current Salary Data:' as status;
SELECT 
    u.first_name || ' ' || u.last_name as employee_name,
    s.base_salary,
    s.hourly_rate,
    s.currency,
    s.calculation_type
FROM payroll_salary s
JOIN users_employee e ON s.employee_id = e.id
ORDER BY s.base_salary DESC;

-- Delete salaries with unrealistic values (likely test data)
DELETE FROM payroll_salary 
WHERE 
    base_salary > 40000 OR          -- Monthly salary > 40k ILS (unrealistic)
    hourly_rate > 200 OR            -- Hourly rate > 200 ILS (unrealistic)
    base_salary = 50000 OR          -- Exact 50k (likely hardcoded test value)
    (hourly_rate = 80 AND base_salary = 25000);  -- Common test combination

-- Show remaining salary data after cleanup
SELECT 'AFTER CLEANUP - Remaining Salary Data:' as status;
SELECT 
    u.first_name || ' ' || u.last_name as employee_name,
    s.base_salary,
    s.hourly_rate,
    s.currency,
    s.calculation_type
FROM payroll_salary s
JOIN users_employee e ON s.employee_id = e.id
ORDER BY s.base_salary DESC;

-- Show cleanup summary
SELECT 'CLEANUP SUMMARY:' as status;
SELECT COUNT(*) as remaining_salary_records FROM payroll_salary;