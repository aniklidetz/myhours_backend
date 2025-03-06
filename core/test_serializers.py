from core.test_utils import create_test_employee
from django.test import TestCase
from core.serializers import EmployeeSerializer, SalarySerializer, WorkLogSerializer
from core.models import Employee, Salary, WorkLog
from django.utils import timezone

class EmployeeSerializerTest(TestCase):
    def test_serializer_valid_data(self):
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'employment_type': 'hourly'
        }
        serializer = EmployeeSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
    def test_serializer_invalid_data(self):
        # Missing required field 'email'
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'employment_type': 'hourly'
        }
        serializer = EmployeeSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)

class WorkLogSerializerTest(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name="John",
            last_name="Doe",
            email="john@example.com"
        )
        
    def test_worklog_serializer(self):
        check_in = timezone.now()
        check_out = check_in + timezone.timedelta(hours=8)
        
        data = {
            'employee': self.employee.id,
            'check_in': check_in,
            'check_out': check_out
        }
        
        serializer = WorkLogSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        worklog = serializer.save()
        self.assertEqual(worklog.get_total_hours(), 8.0)
