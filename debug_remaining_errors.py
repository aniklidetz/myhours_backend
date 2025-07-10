#!/usr/bin/env python3
"""
Debug remaining internal server errors
"""

import os
import sys
import django
import traceback

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from users.models import Employee
from payroll.models import Salary

def debug_problem_employees():
    """Debug the remaining problem employees"""
    
    print("=== DEBUGGING REMAINING ERRORS ===")
    
    # Test the other problem employees
    problem_ids = [52, 56, 58]  # 51 already works
    
    for emp_id in problem_ids:
        try:
            emp = Employee.objects.get(id=emp_id)
            print(f"\nEmployee {emp_id}: {emp.get_full_name()}")
            
            try:
                salary = emp.salary_info
                print(f"  ✅ Salary exists: {salary.calculation_type}")
                print(f"  Base salary: {salary.base_salary}")
                print(f"  Hourly rate: {salary.hourly_rate}")
                print(f"  Currency: {salary.currency}")
                
                # Test the monthly calculation directly
                try:
                    result = salary.calculate_monthly_salary(7, 2025)
                    print(f"  ✅ Monthly calc works: {result}")
                except Exception as calc_error:
                    print(f"  ❌ Monthly calc failed: {calc_error}")
                    print(f"  Traceback: {traceback.format_exc()}")
                    
            except Exception as salary_error:
                print(f"  ❌ Salary error: {salary_error}")
                print(f"  Traceback: {traceback.format_exc()}")
                
        except Employee.DoesNotExist:
            print(f"Employee {emp_id}: NOT FOUND")
        except Exception as e:
            print(f"Employee {emp_id}: ERROR - {e}")
            print(f"Traceback: {traceback.format_exc()}")

def test_enhanced_serializer():
    """Test the enhanced serializer directly"""
    
    print("\n=== TESTING ENHANCED SERIALIZER ===")
    
    from payroll.enhanced_serializers import EnhancedEarningsSerializer
    
    # Test with employee 52
    try:
        emp = Employee.objects.get(id=52)
        salary = emp.salary_info
        
        print(f"Testing {emp.get_full_name()}")
        print(f"Salary type: {salary.calculation_type}")
        
        # Create mock instance
        class MockInstance:
            def __init__(self, employee, year, month, calculation_type):
                self.employee = employee
                self.year = year
                self.month = month
                self.calculation_type = calculation_type
        
        mock_instance = MockInstance(emp, 2025, 7, salary.calculation_type)
        serializer = EnhancedEarningsSerializer()
        
        try:
            result = serializer.to_representation(mock_instance)
            print(f"✅ Enhanced serializer works!")
            print(f"Total gross pay: {result['summary']['total_gross_pay']}")
        except Exception as e:
            print(f"❌ Enhanced serializer failed: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    debug_problem_employees()
    test_enhanced_serializer()