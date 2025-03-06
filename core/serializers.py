from rest_framework import serializers
from .models import Employee, Salary, WorkLog


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