#!/usr/bin/env python
"""
Debug script to test payroll list view error
"""
import os
import sys

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myhours.settings_ci")
django.setup()

from decimal import Decimal
from unittest.mock import MagicMock, patch

from rest_framework.reverse import reverse
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model
from django.test import TestCase

from payroll.models import Salary
from users.models import Employee

User = get_user_model()

# Create or get test data
admin_user, _ = User.objects.get_or_create(
    username="admin", defaults={"email": "admin@example.com", "password": "test123"}
)
admin_employee, _ = Employee.objects.get_or_create(
    user=admin_user,
    defaults={
        "first_name": "Admin",
        "last_name": "User",
        "email": "admin@example.com",
        "employment_type": "full_time",
        "role": "admin",
    },
)
admin_salary, _ = Salary.objects.get_or_create(
    employee=admin_employee,
    defaults={
        "base_salary": Decimal("10000.00"),
        "calculation_type": "monthly",
        "currency": "ILS",
    },
)

client = APIClient()
client.force_authenticate(user=admin_user)

# Try to call the view
with patch("payroll.views.MonthlyPayrollSummary.objects.filter") as mock_filter:
    mock_summary = MagicMock()
    mock_summary.employee = admin_employee
    mock_summary.employee_id = admin_employee.id
    mock_summary.total_gross_pay = Decimal("10000.00")
    mock_summary.total_hours = Decimal("160.00")
    mock_summary.worked_days = 22
    mock_summary.calculation_details = {"work_sessions_count": 22}

    mock_filter.return_value.select_related.return_value = [mock_summary]

    url = reverse("payroll-list")
    response = client.get(url)
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Error: {response.data}")
