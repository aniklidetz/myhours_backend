from users.models import Employee
from payroll.models import Salary

print('=== CHECKING MONTHLY EMPLOYEES ===')
monthly_employees = ['Elior Weisman', 'Leah Ben-Ami', 'Noam Peretz', 'Gilad Friedman']

for name in monthly_employees:
    first, last = name.split()
    try:
        emp = Employee.objects.get(first_name=first, last_name=last)
        print(f'\n{name}:')
        print(f'  Employee ID: {emp.id}')
        try:
            salary = Salary.objects.get(employee=emp)
            print(f'  ✓ Salary exists: {salary.calculation_type}, {salary.base_salary} {salary.currency}')
        except Salary.DoesNotExist:
            print(f'  ✗ NO SALARY RECORD!')
    except Employee.DoesNotExist:
        print(f'\n{name}: ✗ NOT FOUND')

print('\n=== TOTALS ===')        
print(f'Total Salary records: {Salary.objects.count()}')
emps_without_salary = Employee.objects.filter(is_active=True).exclude(
    id__in=Salary.objects.values_list("employee_id", flat=True)
)
print(f'Employees without salary: {emps_without_salary.count()}')
if emps_without_salary.exists():
    print('They are:')
    for emp in emps_without_salary:
        print(f'  - {emp.get_full_name()} (ID: {emp.id})')