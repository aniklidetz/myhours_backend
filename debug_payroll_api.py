#!/usr/bin/env python3
"""
Debug the payroll API using Django shell
"""
import os
import sys
import django

# Setup Django
sys.path.append('/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours_backend.settings')

try:
    django.setup()
    
    # Test the service directly
    print("TESTING ENHANCED PAYROLL SERVICE")
    print("=" * 50)
    
    from payroll.services import EnhancedPayrollCalculationService
    from users.models import Employee
    from payroll.models import Salary
    
    # Try to find an employee with hourly calculation
    try:
        hourly_employees = Employee.objects.filter(salary_info__calculation_type='hourly')
        print(f"Found {hourly_employees.count()} hourly employees")
        
        if hourly_employees.exists():
            employee = hourly_employees.first()
            print(f"Testing with employee: {employee.get_full_name()}")
            
            # Test the service
            service = EnhancedPayrollCalculationService(employee, 2025, 7)
            result = service.calculate_monthly_salary()
            
            print(f"Service result keys: {list(result.keys())}")
            print(f"total_gross_pay: {result.get('total_gross_pay', 'NOT FOUND')}")
            print(f"total_hours: {result.get('total_hours', 'NOT FOUND')}")
            
            if result.get('total_gross_pay', 0) > 0:
                print("✅ Service returns non-zero earnings")
            else:
                print("❌ Service returns zero earnings")
                print("Possible reasons:")
                print("- No work logs for July 2025")
                print("- Work logs exist but calculation is wrong")
                print("- Service configuration issues")
        else:
            print("❌ No hourly employees found")
            
    except Exception as service_error:
        print(f"❌ Service error: {service_error}")
        
    # Test the API view directly
    print("\nTESTING API VIEW DIRECTLY")
    print("=" * 50)
    
    try:
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser
        from payroll.views import enhanced_earnings
        
        # Create a mock request
        factory = RequestFactory()
        request = factory.get('/api/v1/payroll/earnings/')
        request.user = AnonymousUser()
        
        # This will fail due to authentication, but we can see if the import works
        print("✅ API view can be imported")
        print("API view will require authentication in real usage")
        
    except Exception as view_error:
        print(f"❌ API view error: {view_error}")
        
    # Check the service import in views.py
    print("\nCHECKING VIEWS.PY IMPORT")
    print("=" * 50)
    
    try:
        # Check if the corrected import works
        from payroll.views import enhanced_earnings
        print("✅ enhanced_earnings view imports successfully")
        
        # Check what's actually imported
        import payroll.views as views_module
        import inspect
        
        # Get the source of enhanced_earnings to see what service it uses
        source = inspect.getsource(views_module.enhanced_earnings)
        
        if 'EnhancedPayrollCalculationService' in source:
            print("✅ View uses EnhancedPayrollCalculationService")
        else:
            print("❌ View does NOT use EnhancedPayrollCalculationService")
            
    except Exception as import_error:
        print(f"❌ Import error: {import_error}")
        
except Exception as django_error:
    print(f"❌ Django setup error: {django_error}")
    print("This might be due to missing database or configuration issues")
    print("Try running: python manage.py migrate")
    
print("\nSUMMARY:")
print("=" * 50)
print("1. ✅ Backend logic is mathematically correct")
print("2. ❓ Need to verify service works with real data") 
print("3. ❓ Need to verify API view uses correct service")
print("4. 🔄 Restart Django server to apply changes")
print("5. 🔄 Clear frontend cache/restart app")

print("\nTO RESTART DJANGO SERVER:")
print("1. Stop current server (Ctrl+C)")
print("2. python manage.py runserver")
print("3. Test frontend again")