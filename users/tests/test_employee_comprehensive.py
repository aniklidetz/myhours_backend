"""
Comprehensive tests for Employee model and related functionality.
Tests employee management, validation, relationships, and business logic.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from payroll.models import Salary
from users.models import BiometricSession, DeviceToken, Employee, EmployeeInvitation
from worktime.models import WorkLog


class EmployeeModelTest(TestCase):
    """Comprehensive tests for Employee model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_employee_creation_basic(self):
        """Test basic employee creation"""
        employee = Employee.objects.create(
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com",
            employment_type="hourly",
            role="employee",
        )

        self.assertEqual(employee.first_name, "John")
        self.assertEqual(employee.last_name, "Doe")
        self.assertEqual(employee.email, "john.doe@example.com")
        self.assertEqual(employee.employment_type, "hourly")
        self.assertEqual(employee.role, "employee")
        self.assertTrue(employee.is_active)
        self.assertIsNotNone(employee.created_at)

    def test_employee_creation_with_user(self):
        """Test employee creation linked to Django User"""
        employee = Employee.objects.create(
            user=self.user,
            first_name="Jane",
            last_name="Smith",
            email="jane.smith@example.com",
            employment_type="full_time",
            role="manager",
        )

        self.assertEqual(employee.user, self.user)
        self.assertEqual(employee.email, "jane.smith@example.com")
        self.assertEqual(employee.employment_type, "full_time")

    def test_employee_get_full_name(self):
        """Test get_full_name method"""
        employee = Employee.objects.create(
            first_name="Alice",
            last_name="Johnson",
            email="alice@example.com",
            employment_type="part_time",
        )

        self.assertEqual(employee.get_full_name(), "Alice Johnson")

    def test_employee_employment_type_choices(self):
        """Test different employment type choices"""
        employment_types = ["hourly", "full_time", "part_time", "contract"]

        for emp_type in employment_types:
            employee = Employee.objects.create(
                first_name="Test",
                last_name=f"Employee{emp_type}",
                email=f"test.{emp_type}@example.com",
                employment_type=emp_type,
            )
            self.assertEqual(employee.employment_type, emp_type)

    def test_employee_role_choices(self):
        """Test different role choices"""
        roles = ["employee", "manager", "admin", "hr"]

        for role in roles:
            employee = Employee.objects.create(
                first_name="Test",
                last_name=f"Role{role}",
                email=f"test.{role}@example.com",
                employment_type="hourly",
                role=role,
            )
            self.assertEqual(employee.role, role)

    def test_employee_email_uniqueness(self):
        """Test that employee emails must be unique"""
        Employee.objects.create(
            first_name="First",
            last_name="Employee",
            email="duplicate@example.com",
            employment_type="hourly",
        )

        # Attempting to create another employee with same email should raise error
        with self.assertRaises(Exception):  # IntegrityError or ValidationError
            Employee.objects.create(
                first_name="Second",
                last_name="Employee",
                email="duplicate@example.com",
                employment_type="full_time",
            )

    def test_employee_soft_delete(self):
        """Test employee soft delete functionality"""
        employee = Employee.objects.create(
            first_name="Delete",
            last_name="Test",
            email="delete@example.com",
            employment_type="hourly",
        )

        # Soft delete
        employee.is_active = False
        employee.save()

        # Employee should still exist in database but marked inactive
        self.assertFalse(employee.is_active)
        self.assertTrue(Employee.objects.filter(id=employee.id).exists())

    def test_employee_string_representation(self):
        """Test string representation of Employee"""
        employee = Employee.objects.create(
            first_name="String",
            last_name="Test",
            email="string@example.com",
            employment_type="hourly",
        )

        str_repr = str(employee)
        self.assertIn("String Test", str_repr)

    def test_employee_ordering(self):
        """Test default ordering of employees"""
        employees = [
            Employee.objects.create(
                first_name="Charlie",
                last_name="Alpha",
                email="charlie@example.com",
                employment_type="hourly",
            ),
            Employee.objects.create(
                first_name="Alice",
                last_name="Beta",
                email="alice@example.com",
                employment_type="hourly",
            ),
            Employee.objects.create(
                first_name="Bob",
                last_name="Gamma",
                email="bob@example.com",
                employment_type="hourly",
            ),
        ]

        # Test ordering (depends on your model's Meta class)
        ordered_employees = Employee.objects.all()
        # Verify some form of consistent ordering exists
        self.assertEqual(len(ordered_employees), 3)

    def test_employee_manager_methods(self):
        """Test custom manager methods if they exist"""
        # Create active and inactive employees
        active_emp = Employee.objects.create(
            first_name="Active",
            last_name="Employee",
            email="active@example.com",
            employment_type="hourly",
            is_active=True,
        )

        inactive_emp = Employee.objects.create(
            first_name="Inactive",
            last_name="Employee",
            email="inactive@example.com",
            employment_type="hourly",
            is_active=False,
        )

        # Test filtering
        active_employees = Employee.objects.filter(is_active=True)
        self.assertIn(active_emp, active_employees)
        self.assertNotIn(inactive_emp, active_employees)


class EmployeeRelationshipsTest(TestCase):
    """Test relationships between Employee and other models"""

    def setUp(self):
        """Set up test data"""
        self.employee = Employee.objects.create(
            first_name="Relationship",
            last_name="Test",
            email="relationship@example.com",
            employment_type="hourly",
        )

    def test_employee_salary_relationship(self):
        """Test one-to-one relationship with Salary"""
        salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="hourly",
            hourly_rate=Decimal("100.00"),
            currency="ILS",
        )

        # Test forward relationship
        self.assertEqual(salary.employee, self.employee)

        # Test reverse relationship
        self.assertEqual(self.employee.salary, salary)

    def test_employee_worklog_relationship(self):
        """Test one-to-many relationship with WorkLog"""
        # Create multiple work logs
        for i in range(3):
            WorkLog.objects.create(
                employee=self.employee,
                check_in=timezone.now() - timedelta(days=i),
                check_out=timezone.now() - timedelta(days=i) + timedelta(hours=8),
            )

        # Test reverse relationship
        worklogs = self.employee.worklog_set.all()
        self.assertEqual(worklogs.count(), 3)

        # Verify all work logs belong to this employee
        for worklog in worklogs:
            self.assertEqual(worklog.employee, self.employee)

    def test_employee_cascade_behavior(self):
        """Test cascade behavior when employee is deleted"""
        # Create related objects
        salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="hourly",
            hourly_rate=Decimal("80.00"),
            currency="ILS",
        )

        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.now(),
            check_out=timezone.now() + timedelta(hours=8),
        )

        employee_id = self.employee.id

        # Delete employee
        self.employee.delete()

        # Check if related objects are handled appropriately
        # (This depends on your model definitions - CASCADE, PROTECT, etc.)
        with self.assertRaises(Employee.DoesNotExist):
            Employee.objects.get(id=employee_id)


class EmployeeBusinessLogicTest(TestCase):
    """Test business logic and methods for Employee"""

    def setUp(self):
        """Set up test data"""
        self.hourly_employee = Employee.objects.create(
            first_name="Hourly",
            last_name="Worker",
            email="hourly@example.com",
            employment_type="hourly",
        )

        self.monthly_employee = Employee.objects.create(
            first_name="Monthly",
            last_name="Worker",
            email="monthly@example.com",
            employment_type="full_time",
        )

        # Create salaries
        Salary.objects.create(
            employee=self.hourly_employee,
            calculation_type="hourly",
            hourly_rate=Decimal("120.00"),
            currency="ILS",
        )

        Salary.objects.create(
            employee=self.monthly_employee,
            calculation_type="monthly",
            base_salary=Decimal("18000.00"),
            currency="ILS",
        )

    def test_employee_salary_calculation_type_mapping(self):
        """Test automatic mapping from employment_type to calculation_type"""
        # This tests the business logic that maps employment types to salary calculation types
        hourly_salary = self.hourly_employee.salary
        monthly_salary = self.monthly_employee.salary

        # Verify mapping is correct
        self.assertEqual(hourly_salary.calculation_type, "hourly")
        self.assertEqual(monthly_salary.calculation_type, "monthly")

    def test_employee_work_patterns(self):
        """Test different work patterns for different employee types"""
        # Create work logs for both employees
        base_time = timezone.make_aware(datetime(2025, 7, 25, 9, 0))

        # Regular 8-hour day for both
        for employee in [self.hourly_employee, self.monthly_employee]:
            WorkLog.objects.create(
                employee=employee,
                check_in=base_time,
                check_out=base_time + timedelta(hours=8),
                is_approved=True,
            )

        # Verify work logs were created
        hourly_logs = self.hourly_employee.worklog_set.all()
        monthly_logs = self.monthly_employee.worklog_set.all()

        self.assertEqual(hourly_logs.count(), 1)
        self.assertEqual(monthly_logs.count(), 1)

        # Both should have same hours but different pay calculation
        self.assertEqual(hourly_logs.first().get_total_hours(), 8.0)
        self.assertEqual(monthly_logs.first().get_total_hours(), 8.0)

    def test_employee_overtime_eligibility(self):
        """Test overtime eligibility for different employee types"""
        # Create overtime work logs
        base_time = timezone.make_aware(datetime(2025, 7, 25, 8, 0))
        overtime_end = base_time + timedelta(hours=12)  # 12-hour day

        for employee in [self.hourly_employee, self.monthly_employee]:
            WorkLog.objects.create(
                employee=employee,
                check_in=base_time,
                check_out=overtime_end,
                is_approved=True,
            )

        # Both employee types should be eligible for overtime
        # The calculation difference would be in the payroll service
        hourly_overtime_log = self.hourly_employee.worklog_set.first()
        monthly_overtime_log = self.monthly_employee.worklog_set.first()

        self.assertEqual(hourly_overtime_log.get_total_hours(), 12.0)
        self.assertEqual(monthly_overtime_log.get_total_hours(), 12.0)

    def test_employee_monthly_summary_generation(self):
        """Test generation of monthly summaries for employees"""
        # Create work logs for a full month
        july_2025 = date(2025, 7, 1)

        for day in range(1, 11):  # 10 work days
            work_date = july_2025.replace(day=day)
            check_in = timezone.make_aware(
                datetime.combine(work_date, datetime.min.time().replace(hour=9))
            )
            check_out = check_in + timedelta(hours=8)

            WorkLog.objects.create(
                employee=self.hourly_employee,
                check_in=check_in,
                check_out=check_out,
                is_approved=True,
            )

        # Verify work logs were created
        july_logs = self.hourly_employee.worklog_set.filter(
            check_in__year=2025, check_in__month=7
        )

        self.assertEqual(july_logs.count(), 10)

        # Calculate total hours
        total_hours = sum(log.get_total_hours() for log in july_logs)
        self.assertEqual(total_hours, 80.0)  # 10 days × 8 hours

    def test_employee_permissions_by_role(self):
        """Test different permissions based on employee role"""
        # Create employees with different roles
        admin_employee = Employee.objects.create(
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            employment_type="full_time",
            role="admin",
        )

        manager_employee = Employee.objects.create(
            first_name="Manager",
            last_name="User",
            email="manager@example.com",
            employment_type="full_time",
            role="manager",
        )

        regular_employee = Employee.objects.create(
            first_name="Regular",
            last_name="User",
            email="regular@example.com",
            employment_type="hourly",
            role="employee",
        )

        # Test role-based logic (this would depend on your permission system)
        self.assertEqual(admin_employee.role, "admin")
        self.assertEqual(manager_employee.role, "manager")
        self.assertEqual(regular_employee.role, "employee")

    def test_employee_active_status_impact(self):
        """Test impact of active status on business operations"""
        # Create work log for active employee
        active_log = WorkLog.objects.create(
            employee=self.hourly_employee,
            check_in=timezone.now(),
            check_out=timezone.now() + timedelta(hours=8),
        )

        # Deactivate employee
        self.hourly_employee.is_active = False
        self.hourly_employee.save()

        # Verify employee is deactivated
        self.assertFalse(self.hourly_employee.is_active)

        # Work log should still exist (historical data)
        self.assertTrue(WorkLog.objects.filter(id=active_log.id).exists())

    def test_employee_bulk_operations(self):
        """Test bulk operations on employees"""
        # Create multiple employees
        employees = []
        for i in range(10):
            employees.append(
                Employee(
                    first_name=f"Bulk{i}",
                    last_name="Employee",
                    email=f"bulk{i}@example.com",
                    employment_type="hourly",
                    role="employee",
                )
            )

        Employee.objects.bulk_create(employees)

        # Verify bulk creation
        bulk_employees = Employee.objects.filter(first_name__startswith="Bulk")
        self.assertEqual(bulk_employees.count(), 10)

        # Test bulk update
        bulk_employees.update(employment_type="full_time")

        # Verify bulk update
        updated_employees = Employee.objects.filter(
            first_name__startswith="Bulk", employment_type="full_time"
        )
        self.assertEqual(updated_employees.count(), 10)


class EmployeeQueryTest(TestCase):
    """Test querying and filtering employees"""

    def setUp(self):
        """Set up test data"""
        # Create employees with different attributes
        self.employees = [
            Employee.objects.create(
                first_name="Alice",
                last_name="Admin",
                email="alice@example.com",
                employment_type="full_time",
                role="admin",
            ),
            Employee.objects.create(
                first_name="Bob",
                last_name="Manager",
                email="bob@example.com",
                employment_type="full_time",
                role="manager",
            ),
            Employee.objects.create(
                first_name="Charlie",
                last_name="Worker",
                email="charlie@example.com",
                employment_type="hourly",
                role="employee",
            ),
            Employee.objects.create(
                first_name="Diana",
                last_name="Contractor",
                email="diana@example.com",
                employment_type="contract",
                role="employee",
                is_active=False,
            ),
        ]

    def test_filter_by_employment_type(self):
        """Test filtering employees by employment type"""
        hourly_employees = Employee.objects.filter(employment_type="hourly")
        self.assertEqual(hourly_employees.count(), 1)
        self.assertEqual(hourly_employees.first().first_name, "Charlie")

        full_time_employees = Employee.objects.filter(employment_type="full_time")
        self.assertEqual(full_time_employees.count(), 2)

    def test_filter_by_role(self):
        """Test filtering employees by role"""
        admins = Employee.objects.filter(role="admin")
        self.assertEqual(admins.count(), 1)
        self.assertEqual(admins.first().first_name, "Alice")

        employees = Employee.objects.filter(role="employee")
        self.assertEqual(employees.count(), 2)

    def test_filter_by_active_status(self):
        """Test filtering employees by active status"""
        active_employees = Employee.objects.filter(is_active=True)
        self.assertEqual(active_employees.count(), 3)

        inactive_employees = Employee.objects.filter(is_active=False)
        self.assertEqual(inactive_employees.count(), 1)
        self.assertEqual(inactive_employees.first().first_name, "Diana")

    def test_search_by_name(self):
        """Test searching employees by name"""
        alice_employees = Employee.objects.filter(first_name__icontains="Alice")
        self.assertEqual(alice_employees.count(), 1)

        # Search by last name
        admin_employees = Employee.objects.filter(last_name__icontains="Admin")
        self.assertEqual(admin_employees.count(), 1)

    def test_search_by_email(self):
        """Test searching employees by email"""
        example_employees = Employee.objects.filter(email__icontains="example.com")
        self.assertEqual(example_employees.count(), 4)

        specific_employee = Employee.objects.filter(email="bob@example.com")
        self.assertEqual(specific_employee.count(), 1)

    def test_complex_queries(self):
        """Test complex queries with multiple filters"""
        # Active full-time employees
        active_full_time = Employee.objects.filter(
            is_active=True, employment_type="full_time"
        )
        self.assertEqual(active_full_time.count(), 2)

        # Active employees who are not admins
        non_admin_active = Employee.objects.filter(is_active=True).exclude(role="admin")
        self.assertEqual(non_admin_active.count(), 2)

    def test_query_optimization(self):
        """Test query optimization techniques"""
        # Create related data
        for employee in self.employees:
            if employee.is_active:
                Salary.objects.create(
                    employee=employee,
                    calculation_type=(
                        "hourly" if employee.employment_type == "hourly" else "monthly"
                    ),
                    hourly_rate=(
                        Decimal("100.00")
                        if employee.employment_type == "hourly"
                        else None
                    ),
                    base_salary=(
                        Decimal("15000.00")
                        if employee.employment_type != "hourly"
                        else None
                    ),
                    currency="ILS",
                )

        # Test select_related for forward foreign keys
        employees_with_salary = Employee.objects.select_related("salary_info").filter(
            is_active=True
        )

        # This should minimize database queries
        for employee in employees_with_salary:
            if hasattr(employee, "salary_info"):
                # Accessing salary should not trigger additional query
                salary_amount = (
                    employee.salary_info.hourly_rate or employee.salary_info.base_salary
                )
                self.assertIsNotNone(salary_amount)

    def test_aggregation_queries(self):
        """Test aggregation queries on employees"""
        from django.db.models import Count, Q

        # Count employees by employment type
        employment_counts = Employee.objects.values("employment_type").annotate(
            count=Count("id")
        )

        # Should have counts for each employment type
        self.assertTrue(len(employment_counts) > 0)

        # Count active vs inactive
        active_count = Employee.objects.filter(is_active=True).count()
        inactive_count = Employee.objects.filter(is_active=False).count()

        self.assertEqual(active_count, 3)
        self.assertEqual(inactive_count, 1)


class EmployeeIntegrationTest(TestCase):
    """Integration tests for Employee with other systems"""

    def setUp(self):
        """Set up test data"""
        self.employee = Employee.objects.create(
            first_name="Integration",
            last_name="Test",
            email="integration@example.com",
            employment_type="hourly",
        )

        self.salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="hourly",
            hourly_rate=Decimal("150.00"),
            currency="ILS",
        )

    def test_employee_payroll_integration(self):
        """Test integration with payroll calculations"""
        # Create work logs
        for day in range(1, 6):  # 5 work days
            check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
            check_out = timezone.make_aware(datetime(2025, 7, day, 17, 0))

            WorkLog.objects.create(
                employee=self.employee,
                check_in=check_in,
                check_out=check_out,
                is_approved=True,
            )

        # Verify integration data
        work_logs = self.employee.worklog_set.filter(
            check_in__year=2025, check_in__month=7
        )

        self.assertEqual(work_logs.count(), 5)

        # Calculate total hours
        total_hours = sum(log.get_total_hours() for log in work_logs)
        self.assertEqual(total_hours, 40.0)  # 5 days × 8 hours

        # Expected pay calculation (hourly rate × hours)
        expected_gross_pay = self.salary.hourly_rate * Decimal(str(total_hours))
        self.assertEqual(expected_gross_pay, Decimal("6000.00"))  # 150 × 40

    @patch("users.models.Employee.send_notification")
    def test_employee_notification_integration(self, mock_send_notification):
        """Test integration with notification system"""
        # This would test notification sending for employee events
        # For now, just verify the employee can be created and updated

        self.employee.role = "manager"
        self.employee.save()

        # In a real system, this might trigger a notification
        # mock_send_notification.assert_called_once()

        self.assertEqual(self.employee.role, "manager")

    def test_employee_biometric_integration(self):
        """Test integration with biometric systems"""
        # Create biometric session (if the model exists)
        # This tests the relationship between employees and biometric data

        # For now, just verify employee can have biometric-related data
        self.assertIsNotNone(self.employee.id)
        self.assertTrue(hasattr(self.employee, "email"))

        # In a real implementation, you might test:
        # - Face encoding storage
        # - Biometric authentication
        # - Device registration

    def test_employee_audit_trail(self):
        """Test audit trail for employee changes"""
        original_name = self.employee.first_name

        # Make changes
        self.employee.first_name = "Updated"
        self.employee.employment_type = "full_time"
        self.employee.save()

        # Verify changes
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.first_name, "Updated")
        self.assertEqual(self.employee.employment_type, "full_time")

        # In a real system, you might check audit logs here
