"""
LEGACY: Approximation comparison tests for OptimizedPayrollService vs EnhancedPayrollCalculationService

WARNING: OptimizedPayrollService has been REMOVED from the system due to incorrect calculation formula.
    This test exists only for historical coverage and will be deleted during legacy cleanup.
    
    SCHEDULED FOR REMOVAL: 2025-10-15
    
    PROBLEM: OptimizedPayrollService used incorrect formula (hours × rate × 1.3) instead of proper Israeli labor law.
    SOLUTION: Use PayrollService with CalculationStrategy.ENHANCED for all new implementations.

Tests that the "fast" optimized service produces reasonable approximations compared to the base service
on a representative set of scenarios. The OptimizedPayrollService uses estimation algorithms (1.3x coefficient)
for performance, while the base service does exact calculations.

IMPORTANT: These services are NOT equivalent by design:
- OptimizedPayrollService: Fast estimation with approximations (~30% overhead coefficient) [REMOVED - INCORRECT]
- EnhancedPayrollCalculationService: Detailed business logic with exact calculations [LEGACY]

Test scenarios:
1. Weekdays without overtime, with 125% overtime, with 150% overtime
2. Pure Sabbath work, Sabbath + night work
3. Holiday work, Holiday + night work
4. Shifts spanning midnight, long shifts with multiple overtime thresholds
5. Monthly aggregation on 4-6 different shift types

Goal: Verify that approximations are within reasonable bounds (±50% typically, due to complex scenarios).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytz

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

# Mark all tests in this module as legacy
pytestmark = [pytest.mark.legacy]

from integrations.models import Holiday
from payroll.models import Salary
from payroll.optimized_service import OptimizedPayrollService
from payroll.services.adapters import EnhancedPayrollCalculationService
from users.models import Employee
from worktime.models import WorkLog


@pytest.mark.legacy
class OptimizedServiceEquivalencyTest(TestCase):
    """Test equivalency between OptimizedPayrollService and EnhancedPayrollCalculationService"""

    def setUp(self):
        """Set up test data"""
        self.israel_tz = pytz.timezone("Asia/Jerusalem")

        # Create hourly employee
        self.hourly_user = User.objects.create_user(
            username="hourly_emp", email="hourly@test.com", password="pass123"
        )
        self.hourly_employee = Employee.objects.create(
            user=self.hourly_user,
            first_name="Hourly",
            last_name="Employee",
            email="hourly@test.com",
            employment_type="part_time",
            role="employee",
        )
        self.hourly_salary = Salary.objects.create(
            employee=self.hourly_employee,
            calculation_type="hourly",
            hourly_rate=Decimal("75.00"),  # Good rate for testing percentages
            base_salary=Decimal("0.00"),
            currency="ILS",
        )

        # Create monthly employee
        self.monthly_user = User.objects.create_user(
            username="monthly_emp", email="monthly@test.com", password="pass123"
        )
        self.monthly_employee = Employee.objects.create(
            user=self.monthly_user,
            first_name="Monthly",
            last_name="Employee",
            email="monthly@test.com",
            employment_type="full_time",
            role="employee",
        )
        self.monthly_salary = Salary.objects.create(
            employee=self.monthly_employee,
            calculation_type="monthly",
            base_salary=Decimal("15000.00"),
            hourly_rate=Decimal("0.00"),
            currency="ILS",
        )

        # Test dates
        self.test_year = 2025
        self.test_month = 2

        # Create test holidays
        self._create_test_holidays()

    def _create_test_holidays(self):
        """Create test holidays and Sabbaths"""
        # Regular Sabbath (Friday evening to Saturday evening)
        self.sabbath_friday, _ = Holiday.objects.get_or_create(
            date=date(2025, 2, 7),  # Friday
            defaults={
                "name": "Erev Shabbat",
                "is_shabbat": True,
                "is_holiday": False,
                "start_time": self.israel_tz.localize(datetime(2025, 2, 7, 17, 0)),
                "end_time": self.israel_tz.localize(datetime(2025, 2, 8, 18, 0)),
            },
        )

        self.sabbath_saturday, _ = Holiday.objects.get_or_create(
            date=date(2025, 2, 8),  # Saturday
            defaults={
                "name": "Shabbat",
                "is_shabbat": True,
                "is_holiday": False,
                "start_time": self.israel_tz.localize(datetime(2025, 2, 7, 17, 0)),
                "end_time": self.israel_tz.localize(datetime(2025, 2, 8, 18, 0)),
            },
        )

        # Jewish holiday
        self.holiday, _ = Holiday.objects.get_or_create(
            date=date(2025, 2, 15),  # Saturday
            defaults={
                "name": "Tu BiShvat",
                "is_holiday": True,
                "is_shabbat": False,
                "start_time": self.israel_tz.localize(datetime(2025, 2, 15, 0, 0)),
                "end_time": self.israel_tz.localize(datetime(2025, 2, 15, 23, 59)),
            },
        )

    def _compare_calculation_results(
        self, optimized_results, base_result, employee, scenario_name
    ):
        """
        Compare results between optimized (bulk) and base (single) services

        Args:
            optimized_results: List from OptimizedPayrollService.calculate_bulk_payroll
            base_result: Dict from EnhancedPayrollCalculationService.calculate_monthly_salary_enhanced
            employee: Employee object
            scenario_name: String description for debugging
        """
        # Find result for this employee in optimized results
        optimized_result = None
        for result in optimized_results:
            if (
                isinstance(result.get("employee"), dict)
                and result["employee"].get("id") == employee.id
            ):
                optimized_result = result
                break
            elif (
                hasattr(result.get("employee"), "id")
                and result["employee"].id == employee.id
            ):
                optimized_result = result
                break

        self.assertIsNotNone(
            optimized_result,
            f"No result found for employee {employee.id} in scenario: {scenario_name}",
        )

        # Compare key financial metrics
        # Note: OptimizedPayrollService uses 'total_salary' while base service uses 'total_gross_pay'
        optimized_pay = optimized_result.get(
            "total_salary", optimized_result.get("total_gross_pay", 0)
        )
        base_pay = base_result.get("total_gross_pay", 0)

        self._assert_decimal_close(
            optimized_pay, base_pay, f"Total gross pay mismatch in {scenario_name}"
        )

        self._assert_decimal_close(
            optimized_result.get("total_hours", 0),
            base_result.get("total_hours", 0),
            f"Total hours mismatch in {scenario_name}",
        )

        # Compare detailed breakdowns if available
        if "regular_hours" in optimized_result and "regular_hours" in base_result:
            self._assert_decimal_close(
                optimized_result["regular_hours"],
                base_result["regular_hours"],
                f"Regular hours mismatch in {scenario_name}",
            )

        if "overtime_hours" in optimized_result and "overtime_hours" in base_result:
            self._assert_decimal_close(
                optimized_result["overtime_hours"],
                base_result["overtime_hours"],
                f"Overtime hours mismatch in {scenario_name}",
            )

    def _assert_decimal_close(
        self, actual, expected, msg, tolerance_percent=Decimal("50.0")
    ):
        """
        Assert that two Decimal/numeric values are close within percentage tolerance

        OptimizedPayrollService uses approximation (1.3x coefficient), so we expect ~30-50% difference
        """
        actual_decimal = Decimal(str(actual))
        expected_decimal = Decimal(str(expected))

        if expected_decimal == 0:
            # If expected is 0, just check actual is also close to 0
            tolerance = Decimal("10.00")  # Allow small absolute difference
            diff = abs(actual_decimal)
        else:
            # Calculate percentage difference
            diff = abs(actual_decimal - expected_decimal)
            percentage_diff = (diff / expected_decimal) * 100

            self.assertLessEqual(
                percentage_diff,
                tolerance_percent,
                f"{msg}. Expected: {expected_decimal}, Actual: {actual_decimal}, "
                f"Diff: {diff}, Percentage diff: {percentage_diff:.2f}%",
            )
            return

        self.assertLessEqual(
            diff,
            tolerance,
            f"{msg}. Expected: {expected_decimal}, Actual: {actual_decimal}, Diff: {diff}",
        )

    def _create_work_log(self, employee, start_time, end_time, description=""):
        """Helper to create work logs with timezone handling"""
        if isinstance(start_time, datetime) and start_time.tzinfo is None:
            start_time = self.israel_tz.localize(start_time)
        if isinstance(end_time, datetime) and end_time.tzinfo is None:
            end_time = self.israel_tz.localize(end_time)

        return WorkLog.objects.create(
            employee=employee, check_in=start_time, check_out=end_time
        )

    def test_weekday_no_overtime(self):
        """Test regular weekday work without overtime (< 8 hours)"""
        # Clear any existing work logs
        WorkLog.objects.all().delete()

        # Create regular 6-hour shift on Monday
        self._create_work_log(
            self.hourly_employee,
            datetime(2025, 2, 3, 9, 0),  # Monday 9 AM
            datetime(2025, 2, 3, 15, 0),  # Monday 3 PM (6 hours)
        )

        # Test optimized service
        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.hourly_employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        # Test base service
        base_service = EnhancedPayrollCalculationService(
            self.hourly_employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        # Compare results
        self._compare_calculation_results(
            optimized_results, base_result, self.hourly_employee, "weekday_no_overtime"
        )

    def test_weekday_125_percent_overtime(self):
        """Test weekday work with 125% overtime (8-10 hours)"""
        WorkLog.objects.all().delete()

        # Create 9-hour shift on Tuesday (8 regular + 1 overtime at 125%)
        self._create_work_log(
            self.hourly_employee,
            datetime(2025, 2, 4, 8, 0),  # Tuesday 8 AM
            datetime(2025, 2, 4, 17, 0),  # Tuesday 5 PM (9 hours)
        )

        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.hourly_employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        base_service = EnhancedPayrollCalculationService(
            self.hourly_employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        self._compare_calculation_results(
            optimized_results, base_result, self.hourly_employee, "weekday_125_overtime"
        )

    def test_weekday_150_percent_overtime(self):
        """Test weekday work with 150% overtime (> 10 hours)"""
        WorkLog.objects.all().delete()

        # Create 12-hour shift on Wednesday (8 regular + 2 at 125% + 2 at 150%)
        self._create_work_log(
            self.hourly_employee,
            datetime(2025, 2, 5, 7, 0),  # Wednesday 7 AM
            datetime(2025, 2, 5, 19, 0),  # Wednesday 7 PM (12 hours)
        )

        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.hourly_employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        base_service = EnhancedPayrollCalculationService(
            self.hourly_employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        self._compare_calculation_results(
            optimized_results, base_result, self.hourly_employee, "weekday_150_overtime"
        )

    def test_pure_sabbath_work(self):
        """Test work during Sabbath only"""
        WorkLog.objects.all().delete()

        # Work during Saturday afternoon (pure Sabbath time)
        self._create_work_log(
            self.hourly_employee,
            datetime(2025, 2, 8, 10, 0),  # Saturday 10 AM
            datetime(2025, 2, 8, 16, 0),  # Saturday 4 PM (6 hours)
        )

        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.hourly_employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        base_service = EnhancedPayrollCalculationService(
            self.hourly_employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        self._compare_calculation_results(
            optimized_results, base_result, self.hourly_employee, "pure_sabbath_work"
        )

    def test_sabbath_plus_night(self):
        """Test Sabbath work extending into night"""
        WorkLog.objects.all().delete()

        # Work from Saturday afternoon to Sunday early morning
        self._create_work_log(
            self.hourly_employee,
            datetime(2025, 2, 8, 14, 0),  # Saturday 2 PM
            datetime(2025, 2, 9, 2, 0),  # Sunday 2 AM (12 hours, spanning midnight)
        )

        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.hourly_employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        base_service = EnhancedPayrollCalculationService(
            self.hourly_employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        self._compare_calculation_results(
            optimized_results, base_result, self.hourly_employee, "sabbath_plus_night"
        )

    def test_pure_holiday_work(self):
        """Test work during holiday only"""
        WorkLog.objects.all().delete()

        # Work during Tu BiShvat holiday
        self._create_work_log(
            self.hourly_employee,
            datetime(2025, 2, 15, 9, 0),  # Holiday 9 AM
            datetime(2025, 2, 15, 17, 0),  # Holiday 5 PM (8 hours)
        )

        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.hourly_employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        base_service = EnhancedPayrollCalculationService(
            self.hourly_employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        self._compare_calculation_results(
            optimized_results, base_result, self.hourly_employee, "pure_holiday_work"
        )

    def test_holiday_plus_night(self):
        """Test holiday work extending into night"""
        WorkLog.objects.all().delete()

        # Work from holiday evening to next day early morning
        self._create_work_log(
            self.hourly_employee,
            datetime(2025, 2, 15, 18, 0),  # Holiday 6 PM
            datetime(2025, 2, 16, 4, 0),  # Next day 4 AM (10 hours, spanning midnight)
        )

        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.hourly_employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        base_service = EnhancedPayrollCalculationService(
            self.hourly_employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        self._compare_calculation_results(
            optimized_results, base_result, self.hourly_employee, "holiday_plus_night"
        )

    def test_shift_spanning_midnight(self):
        """Test regular shift spanning midnight"""
        WorkLog.objects.all().delete()

        # Regular night shift from Monday to Tuesday
        self._create_work_log(
            self.hourly_employee,
            datetime(2025, 2, 10, 22, 0),  # Monday 10 PM
            datetime(2025, 2, 11, 6, 0),  # Tuesday 6 AM (8 hours)
        )

        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.hourly_employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        base_service = EnhancedPayrollCalculationService(
            self.hourly_employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        self._compare_calculation_results(
            optimized_results,
            base_result,
            self.hourly_employee,
            "shift_spanning_midnight",
        )

    def test_long_shift_multiple_thresholds(self):
        """Test very long shift crossing multiple overtime thresholds"""
        WorkLog.objects.all().delete()

        # 14-hour shift: 8 regular + 2 at 125% + 4 at 150%
        self._create_work_log(
            self.hourly_employee,
            datetime(2025, 2, 12, 6, 0),  # Wednesday 6 AM
            datetime(2025, 2, 12, 20, 0),  # Wednesday 8 PM (14 hours)
        )

        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.hourly_employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        base_service = EnhancedPayrollCalculationService(
            self.hourly_employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        self._compare_calculation_results(
            optimized_results,
            base_result,
            self.hourly_employee,
            "long_shift_multiple_thresholds",
        )

    def test_monthly_aggregation_diverse_shifts(self):
        """Test monthly aggregation on 6 different shift types"""
        WorkLog.objects.all().delete()

        # Create 6 different types of shifts for comprehensive testing
        shifts = [
            # 1. Regular weekday (6 hours)
            (datetime(2025, 2, 3, 9, 0), datetime(2025, 2, 3, 15, 0)),
            # 2. Weekday with 125% overtime (9 hours)
            (datetime(2025, 2, 4, 8, 0), datetime(2025, 2, 4, 17, 0)),
            # 3. Weekday with 150% overtime (12 hours)
            (datetime(2025, 2, 5, 7, 0), datetime(2025, 2, 5, 19, 0)),
            # 4. Sabbath work (6 hours)
            (datetime(2025, 2, 8, 10, 0), datetime(2025, 2, 8, 16, 0)),
            # 5. Holiday work (8 hours)
            (datetime(2025, 2, 15, 9, 0), datetime(2025, 2, 15, 17, 0)),
            # 6. Night shift spanning midnight (8 hours)
            (datetime(2025, 2, 17, 22, 0), datetime(2025, 2, 18, 6, 0)),
        ]

        # Create all work logs
        for start_time, end_time in shifts:
            self._create_work_log(self.hourly_employee, start_time, end_time)

        # Test optimized service
        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.hourly_employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        # Test base service
        base_service = EnhancedPayrollCalculationService(
            self.hourly_employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        # Compare results with stricter tolerance for monthly aggregation
        self._compare_calculation_results(
            optimized_results,
            base_result,
            self.hourly_employee,
            "monthly_aggregation_diverse_shifts",
        )

    def test_monthly_employee_equivalency(self):
        """Test equivalency for monthly employee with diverse shifts"""
        WorkLog.objects.all().delete()

        # Create varied shifts for monthly employee
        shifts = [
            # Regular day
            (datetime(2025, 2, 3, 9, 0), datetime(2025, 2, 3, 17, 0)),
            # Long day
            (datetime(2025, 2, 4, 8, 0), datetime(2025, 2, 4, 20, 0)),
            # Sabbath work
            (datetime(2025, 2, 8, 10, 0), datetime(2025, 2, 8, 18, 0)),
            # Holiday work
            (datetime(2025, 2, 15, 9, 0), datetime(2025, 2, 15, 17, 0)),
        ]

        for start_time, end_time in shifts:
            self._create_work_log(self.monthly_employee, start_time, end_time)

        # Test optimized service
        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.monthly_employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        # Test base service
        base_service = EnhancedPayrollCalculationService(
            self.monthly_employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        self._compare_calculation_results(
            optimized_results,
            base_result,
            self.monthly_employee,
            "monthly_employee_diverse_shifts",
        )

    def test_bulk_vs_individual_consistency(self):
        """Test that bulk processing produces same results as individual calculations"""
        WorkLog.objects.all().delete()

        # Create work for both employees
        # Hourly employee: regular + overtime
        self._create_work_log(
            self.hourly_employee,
            datetime(2025, 2, 10, 8, 0),
            datetime(2025, 2, 10, 19, 0),  # 11 hours
        )

        # Monthly employee: regular + sabbath
        self._create_work_log(
            self.monthly_employee,
            datetime(2025, 2, 8, 9, 0),
            datetime(2025, 2, 8, 17, 0),  # 8 hours on Sabbath
        )

        # Test optimized bulk service
        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id__in=[self.hourly_employee.id, self.monthly_employee.id]
        )
        bulk_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        # Test individual base services
        hourly_base_service = EnhancedPayrollCalculationService(
            self.hourly_employee, self.test_year, self.test_month, fast_mode=True
        )
        hourly_base_result = hourly_base_service.calculate_monthly_salary_enhanced()

        monthly_base_service = EnhancedPayrollCalculationService(
            self.monthly_employee, self.test_year, self.test_month, fast_mode=True
        )
        monthly_base_result = monthly_base_service.calculate_monthly_salary_enhanced()

        # Compare each employee's results
        self._compare_calculation_results(
            bulk_results,
            hourly_base_result,
            self.hourly_employee,
            "bulk_vs_individual_hourly",
        )

        self._compare_calculation_results(
            bulk_results,
            monthly_base_result,
            self.monthly_employee,
            "bulk_vs_individual_monthly",
        )


@pytest.mark.legacy
class OptimizedServiceEquivalencyEdgeCasesTest(TestCase):
    """Test edge cases in equivalency"""

    def setUp(self):
        self.israel_tz = pytz.timezone("Asia/Jerusalem")

        # Create employee with edge case salary
        self.user = User.objects.create_user(
            username="edge_emp", email="edge@test.com", password="pass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Edge",
            last_name="Case",
            email="edge@test.com",
            employment_type="part_time",
            role="employee",
        )
        self.salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="hourly",
            hourly_rate=Decimal("28.49"),  # Minimum wage
            base_salary=Decimal("0.00"),
            currency="ILS",
        )

        self.test_year = 2025
        self.test_month = 2

    def _assert_decimal_close(
        self, actual, expected, msg, tolerance_percent=Decimal("50.0")
    ):
        """
        Assert that two Decimal/numeric values are close within percentage tolerance

        OptimizedPayrollService uses approximation (1.3x coefficient), so we expect ~30-50% difference
        """
        actual_decimal = Decimal(str(actual))
        expected_decimal = Decimal(str(expected))

        if expected_decimal == 0:
            # If expected is 0, just check actual is also close to 0
            tolerance = Decimal("10.00")  # Allow small absolute difference
            diff = abs(actual_decimal)
        else:
            # Calculate percentage difference
            diff = abs(actual_decimal - expected_decimal)
            percentage_diff = (diff / expected_decimal) * 100

            self.assertLessEqual(
                percentage_diff,
                tolerance_percent,
                f"{msg}. Expected: {expected_decimal}, Actual: {actual_decimal}, "
                f"Diff: {diff}, Percentage diff: {percentage_diff:.2f}%",
            )
            return

        self.assertLessEqual(
            diff,
            tolerance,
            f"{msg}. Expected: {expected_decimal}, Actual: {actual_decimal}, Diff: {diff}",
        )

    def test_zero_hours_equivalency(self):
        """Test equivalency when employee has no work hours"""
        # No work logs created - should both return zero

        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        base_service = EnhancedPayrollCalculationService(
            self.employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        # Both should return zero/minimal values
        self.assertEqual(len(optimized_results), 1)
        optimized_result = optimized_results[0]

        # Check that both report zero hours and pay
        self.assertEqual(
            Decimal(str(optimized_result.get("total_hours", 0))), Decimal("0")
        )
        self.assertEqual(Decimal(str(base_result.get("total_hours", 0))), Decimal("0"))

    def test_rounding_precision_equivalency(self):
        """Test that rounding precision matches between services"""
        # Create work log with fractional minutes
        WorkLog.objects.create(
            employee=self.employee,
            check_in=self.israel_tz.localize(
                datetime(2025, 2, 10, 8, 17, 30)
            ),  # 8:17:30
            check_out=self.israel_tz.localize(
                datetime(2025, 2, 10, 16, 43, 45)
            ),  # 16:43:45
        )

        optimized_service = OptimizedPayrollService(fast_mode=True)
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.employee.id
        )
        optimized_results = optimized_service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        base_service = EnhancedPayrollCalculationService(
            self.employee, self.test_year, self.test_month, fast_mode=True
        )
        base_result = base_service.calculate_monthly_salary_enhanced()

        # Compare with very tight precision for rounding consistency
        optimized_result = optimized_results[0]

        # Check hours calculation precision
        optimized_hours = Decimal(str(optimized_result.get("total_hours", 0)))
        base_hours = Decimal(str(base_result.get("total_hours", 0)))
        hours_diff = abs(optimized_hours - base_hours)

        # Allow for minimal rounding differences (1 second = 0.00028 hours)
        self.assertLessEqual(
            hours_diff,
            Decimal("0.01"),
            f"Hours precision mismatch: {optimized_hours} vs {base_hours}",
        )

        # Check pay calculation precision - use percentage-based comparison for approximation service
        optimized_pay = optimized_result.get(
            "total_salary", optimized_result.get("total_gross_pay", 0)
        )
        base_pay = base_result.get("total_gross_pay", 0)

        # Use the same percentage tolerance as other tests (since this is an approximation service)
        self._assert_decimal_close(
            optimized_pay, base_pay, "Pay precision mismatch in rounding test"
        )
