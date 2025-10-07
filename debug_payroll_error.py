#!/usr/bin/env python
"""
Debug script to capture actual exceptions thrown in PayrollService during tests
"""
import os
import sys
import django
from django.conf import settings

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours_backend.settings')
django.setup()

import logging
from datetime import date, datetime, time
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth.models import User
from users.models import Employee
from payroll.models import Salary
from worktime.models import WorkLog
from integrations.models import Holiday
from payroll.services.payroll_service import PayrollService
from payroll.services.enums import CalculationStrategy
from payroll.tests.helpers import make_context

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

def test_sabbath_calculation():
    """Test Sabbath calculation to capture the exception"""
    try:
        # Clean up existing data
        Employee.objects.filter(email='debug@test.com').delete()

        # Create test employee
        user = User.objects.create_user(
            username='debuguser', email='debug@test.com', password='test123'
        )
        employee = Employee.objects.create(
            user=user,
            first_name='Debug',
            last_name='Employee',
            email='debug@test.com',
            employment_type='hourly',
            role='employee',
        )

        # Create salary with is_active=True
        salary = Salary.objects.create(
            employee=employee,
            calculation_type='hourly',
            hourly_rate=Decimal('100.00'),
            currency='ILS',
            is_active=True,
        )

        print(f"Created employee {employee.id} with salary {salary.id}")
        print(f"Salary is_active: {salary.is_active}")
        print(f"Employee salary_info: {employee.salary_info}")

        # Create Sabbath period (Friday evening to Saturday evening)
        friday_date = date(2025, 1, 10)  # Friday
        saturday_date = date(2025, 1, 11)  # Saturday

        # Create Sabbath holiday record
        friday_start = datetime.combine(friday_date, time(18, 0))
        friday_end = datetime.combine(saturday_date, time(19, 0))

        holiday, created = Holiday.objects.get_or_create(
            date=friday_date,
            name="Shabbat",
            defaults={
                'is_shabbat': True,
                'start_time': friday_start,
                'end_time': friday_end
            }
        )
        print(f"Created/found Sabbath holiday: {holiday}")

        # Create work log during Sabbath
        work_start = timezone.make_aware(datetime.combine(saturday_date, time(10, 0)))
        work_end = timezone.make_aware(datetime.combine(saturday_date, time(18, 36)))  # 8.6 hours

        work_log = WorkLog.objects.create(
            employee=employee,
            check_in=work_start,
            check_out=work_end,
        )
        print(f"Created work log: {work_log}")

        # Test PayrollService calculation
        context = make_context(employee.id, 2025, 1)
        service = PayrollService(context)

        print("Calling PayrollService.calculate()...")
        result = service.calculate()

        print(f"Result: {result}")

        # Check if we got fallback result (zero values)
        if result['total_salary'] == Decimal('0'):
            print("ERROR: Got fallback result with zero salary")
        else:
            print("SUCCESS: Got proper calculation result")

    except Exception as e:
        print(f"EXCEPTION in test script: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_sabbath_calculation()