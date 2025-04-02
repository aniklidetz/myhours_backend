from rest_framework import serializers
from users.models import Employee
from worktime.models import WorkLog
from payroll.models import Salary

class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = '__all__'

class SalarySerializer(serializers.ModelSerializer):
    # Ensure that the fields match the updated model
    class Meta:
        model = Salary
        # Use only the fields available in the updated model
        fields = ['id', 'employee', 'base_salary', 'hourly_rate', 
                  'calculation_type', 'currency', 'created_at', 'updated_at']

class WorkLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkLog
        fields = '__all__'