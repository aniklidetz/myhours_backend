from rest_framework import serializers
from users.models import Employee
from worktime.models import WorkLog
from payroll.models import Salary

class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = '__all__'  # Или укажи конкретные поля ['id', 'first_name', 'last_name', 'email']

class SalarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Salary
        fields = '__all__'

class WorkLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkLog
        fields = '__all__'  # Или перечисли только нужные поля