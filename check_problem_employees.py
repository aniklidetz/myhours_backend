from users.models import Employee
from payroll.models import Salary

# IDs that fail with 500
problem_ids = [51, 52, 56, 58]

print("=== EMPLOYEES WITH 500 ERRORS ===")
for emp_id in problem_ids:
    try:
        emp = Employee.objects.get(id=emp_id)
        print(f"\nID {emp_id}: {emp.get_full_name()}")
        print(f"  Role: {emp.role}")
        
        try:
            salary = Salary.objects.get(employee=emp)
            print(f"  Salary: {salary.calculation_type}, Rate: {salary.hourly_rate or salary.base_salary}")
        except Salary.DoesNotExist:
            print("  ❌ NO SALARY RECORD!")
    except Employee.DoesNotExist:
        print(f"\nID {emp_id}: NOT FOUND")