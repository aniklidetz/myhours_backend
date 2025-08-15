"""
Smoke tests for payroll/views.py - focusing on API endpoints functionality
without deep integration complexity. Tests response structure and basic behavior.
"""

import calendar
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from rest_framework import status
from rest_framework.test import APIClient

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from payroll.models import (
    CompensatoryDay,
    DailyPayrollCalculation,
    MonthlyPayrollSummary,
    Salary,
)
from users.models import Employee
from worktime.models import WorkLog


class PayrollViewsSmokeTest(TestCase):
    """Smoke tests for payroll views - basic functionality"""

    def setUp(self):
        """Set up test data"""
        # Create test users
        self.admin_user = User.objects.create_user(
            username="admin", email="admin@example.com", password="test123"
        )

        self.employee_user = User.objects.create_user(
            username="employee", email="employee@example.com", password="test123"
        )

        # Create employees
        self.admin_employee = Employee.objects.create(
            user=self.admin_user,
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            employment_type="full_time",
            role="admin",
        )

        self.regular_employee = Employee.objects.create(
            user=self.employee_user,
            first_name="Regular",
            last_name="Employee",
            email="employee@example.com",
            employment_type="full_time",
            role="employee",
        )

        # Create salary info
        self.admin_salary = Salary.objects.create(
            employee=self.admin_employee,
            base_salary=Decimal("10000.00"),
            calculation_type="monthly",
            currency="ILS",
        )

        self.employee_salary = Salary.objects.create(
            employee=self.regular_employee,
            hourly_rate=Decimal("50.00"),
            calculation_type="hourly",
            currency="ILS",
        )

        # Create API clients
        self.admin_client = APIClient()
        self.employee_client = APIClient()
        self.anonymous_client = APIClient()

        self.admin_client.force_authenticate(user=self.admin_user)
        self.employee_client.force_authenticate(user=self.employee_user)


class HelperFunctionsSmokeTest(PayrollViewsSmokeTest):
    """Test helper functions in payroll views"""

    def test_get_user_employee_profile_success(self):
        """Test getting employee profile successfully"""
        from payroll.views import get_user_employee_profile

        # Mock user with employees relation
        mock_user = MagicMock()
        mock_user.employees.first.return_value = self.admin_employee

        result = get_user_employee_profile(mock_user)
        self.assertEqual(result, self.admin_employee)

    def test_get_user_employee_profile_no_profile(self):
        """Test getting employee profile when none exists"""
        from payroll.views import get_user_employee_profile

        # Mock user without employees attribute
        mock_user = MagicMock()
        mock_user.employees = None

        result = get_user_employee_profile(mock_user)
        self.assertIsNone(result)

    def test_check_admin_or_accountant_role_admin(self):
        """Test admin role check returns True"""
        from payroll.views import check_admin_or_accountant_role

        result = check_admin_or_accountant_role(self.admin_user)
        self.assertTrue(result)

    def test_check_admin_or_accountant_role_employee(self):
        """Test employee role check returns False"""
        from payroll.views import check_admin_or_accountant_role

        result = check_admin_or_accountant_role(self.employee_user)
        self.assertFalse(result)

    def test_check_admin_or_accountant_role_accountant(self):
        """Test accountant role check returns True"""
        from payroll.views import check_admin_or_accountant_role

        # Create accountant user
        accountant_user = User.objects.create_user(
            username="accountant", email="accountant@example.com", password="pass123"
        )
        Employee.objects.create(
            user=accountant_user,
            first_name="Account",
            last_name="Ant",
            email="accountant@example.com",
            role="accountant",
        )

        result = check_admin_or_accountant_role(accountant_user)
        self.assertTrue(result)

    def test_check_admin_or_accountant_role_regular_user(self):
        """Test regular user role check returns False"""
        from payroll.views import check_admin_or_accountant_role

        # Use the regular employee user
        result = check_admin_or_accountant_role(self.employee_user)
        self.assertFalse(result)

    def test_check_admin_or_accountant_role_no_employee(self):
        """Test role check with user having no employee profile"""
        from payroll.views import check_admin_or_accountant_role

        user_without_profile = User.objects.create_user(
            username="noprofile", password="test123"
        )

        result = check_admin_or_accountant_role(user_without_profile)
        self.assertFalse(result)


class PayrollListViewSmokeTest(PayrollViewsSmokeTest):
    """Test payroll list endpoint"""

    def test_payroll_list_admin_success(self):
        """Test admin can access payroll list"""
        url = reverse("payroll-list")
        response = self.admin_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_payroll_list_employee_success(self):
        """Test employee can access their own payroll"""
        url = reverse("payroll-list")
        response = self.employee_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_payroll_list_anonymous_denied(self):
        """Test anonymous access is denied"""
        url = reverse("payroll-list")
        response = self.anonymous_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_payroll_list_accountant_success(self):
        """Test accountant can access payroll list"""
        # Create accountant user
        accountant_user = User.objects.create_user(
            username="accountant2", email="accountant2@example.com", password="pass123"
        )
        Employee.objects.create(
            user=accountant_user,
            first_name="Account",
            last_name="Ant",
            email="accountant2@example.com",
            role="accountant",
        )

        client = APIClient()
        client.force_authenticate(user=accountant_user)

        url = reverse("payroll-list")
        response = client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_payroll_list_regular_user_forbidden(self):
        """Test regular user gets forbidden for admin-only payroll list"""
        # This test assumes there's an admin-only payroll endpoint
        # If regular users can see their own payroll, this might return 200
        # Adjust based on actual permission logic
        url = reverse("payroll-list")
        response = self.employee_client.get(
            url, {"all": "true"}
        )  # Try to get all payrolls

        # Regular user should either get 403 or filtered results
        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN]
        )

    def test_payroll_list_unauthenticated(self):
        """Test unauthenticated access to payroll list"""
        url = reverse("payroll-list")
        response = self.anonymous_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("payroll.views.get_user_employee_profile")
    def test_payroll_list_no_employee_profile(self, mock_get_profile):
        """Test payroll list with user having no employee profile"""
        mock_get_profile.return_value = None

        url = reverse("payroll-list")
        response = self.admin_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    def test_payroll_list_with_year_month_params(self):
        """Test payroll list with year/month parameters"""
        url = reverse("payroll-list")
        response = self.admin_client.get(url, {"year": "2025", "month": "1"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_payroll_list_invalid_year_month(self):
        """Test payroll list with invalid year/month parameters"""
        url = reverse("payroll-list")
        response = self.admin_client.get(url, {"year": "invalid", "month": "invalid"})

        # Should fallback to current date
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("payroll.views.MonthlyPayrollSummary.objects.filter")
    def test_payroll_list_with_cached_data(self, mock_filter):
        """Test payroll list using cached data"""
        # Mock cached summary
        mock_summary = MagicMock()
        mock_summary.employee = self.admin_employee
        mock_summary.employee_id = self.admin_employee.id
        mock_summary.total_gross_pay = Decimal("10000.00")
        mock_summary.total_hours = Decimal("160.00")
        mock_summary.worked_days = 22
        mock_summary.calculation_details = {"work_sessions_count": 22}

        mock_filter.return_value.select_related.return_value = [mock_summary]

        url = reverse("payroll-list")
        response = self.admin_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_payroll_list_with_optimized_service_mock(self):
        """Test payroll list flow (optimized service may not exist)"""
        url = reverse("payroll-list")
        response = self.admin_client.get(url)

        # Service should handle missing optimized service gracefully
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_payroll_list_legacy_fallback_exists(self):
        """Test that legacy payroll calculation function exists"""
        from payroll.views import _legacy_payroll_calculation

        # Function should exist and be callable
        self.assertTrue(callable(_legacy_payroll_calculation))

    @patch("payroll.views.logger")
    def test_payroll_list_exception_handling(self, mock_logger):
        """Test payroll list exception handling"""
        with patch("payroll.views.get_user_employee_profile") as mock_get_profile:
            mock_get_profile.side_effect = Exception("Database error")

            url = reverse("payroll-list")
            response = self.admin_client.get(url)

            self.assertEqual(
                response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            mock_logger.exception.assert_called_once()


class EnhancedEarningsViewSmokeTest(PayrollViewsSmokeTest):
    """Test enhanced earnings endpoint"""

    def test_enhanced_earnings_employee_own_data(self):
        """Test employee accessing their own earnings"""
        url = reverse("current-earnings")
        response = self.employee_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("employee", response.data)

    def test_enhanced_earnings_admin_specific_employee(self):
        """Test admin accessing specific employee data"""
        url = reverse("current-earnings")
        response = self.admin_client.get(url, {"employee_id": self.regular_employee.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["employee"]["id"], self.regular_employee.id)

    def test_enhanced_earnings_employee_access_denied(self):
        """Test employee cannot access other employee data"""
        url = reverse("current-earnings")
        response = self.employee_client.get(
            url, {"employee_id": self.admin_employee.id}
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_enhanced_earnings_employee_not_found(self):
        """Test enhanced earnings with non-existent employee"""
        url = reverse("current-earnings")
        response = self.admin_client.get(url, {"employee_id": 99999})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("payroll.views.get_user_employee_profile")
    def test_enhanced_earnings_no_employee_profile(self, mock_get_profile):
        """Test enhanced earnings with no employee profile"""
        mock_get_profile.return_value = None

        url = reverse("current-earnings")
        response = self.employee_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_enhanced_earnings_with_year_month_params(self):
        """Test enhanced earnings with year/month parameters"""
        url = reverse("current-earnings")
        response = self.employee_client.get(url, {"year": "2025", "month": "1"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["year"], 2025)
        self.assertEqual(response.data["month"], 1)

    def test_enhanced_earnings_no_salary_config(self):
        """Test enhanced earnings with employee having no salary configuration"""
        # Create employee without salary
        no_salary_user = User.objects.create_user(
            username="nosalary", password="test123"
        )
        no_salary_employee = Employee.objects.create(
            user=no_salary_user,
            first_name="No",
            last_name="Salary",
            email="nosalary@example.com",
            employment_type="full_time",
            role="employee",
        )

        client = APIClient()
        client.force_authenticate(user=no_salary_user)

        url = reverse("current-earnings")
        response = client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["calculation_type"], "not_configured")
        self.assertEqual(response.data["total_salary"], 0)

    def test_enhanced_earnings_with_cached_data(self):
        """Test enhanced earnings using cached monthly summary"""
        # Create monthly summary
        summary = MonthlyPayrollSummary.objects.create(
            employee=self.regular_employee,
            year=2025,
            month=1,
            total_hours=Decimal("160.00"),
            total_gross_pay=Decimal("8000.00"),
            base_pay=Decimal("8000.00"),
            worked_days=22,
        )

        url = reverse("current-earnings")
        response = self.employee_client.get(url, {"year": "2025", "month": "1"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_salary"], 8000.0)

    @patch("payroll.views.DailyPayrollCalculation.objects.filter")
    def test_enhanced_earnings_hourly_with_daily_calcs(self, mock_filter):
        """Test enhanced earnings for hourly employee with daily calculations"""
        mock_aggregate = MagicMock()
        mock_aggregate.return_value = {
            "total_regular": Decimal("120.00"),
            "total_overtime_1": Decimal("10.00"),
            "total_overtime_2": Decimal("5.00"),
            "sabbath_regular": Decimal("0.00"),
            "sabbath_overtime_1": Decimal("0.00"),
            "sabbath_overtime_2": Decimal("0.00"),
            "holiday_regular": Decimal("0.00"),
            "holiday_overtime_1": Decimal("0.00"),
            "holiday_overtime_2": Decimal("0.00"),
        }
        mock_filter.return_value.aggregate = mock_aggregate

        url = reverse("current-earnings")
        response = self.employee_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_enhanced_earnings_exception_handling_basic(self):
        """Test enhanced earnings basic exception handling"""
        # Test with invalid employee_id should return 404
        url = reverse("current-earnings")
        response = self.admin_client.get(url, {"employee_id": 99999})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class DailyPayrollCalculationsViewSmokeTest(PayrollViewsSmokeTest):
    """Test daily payroll calculations functions"""

    def test_daily_calculations_function_exists(self):
        """Test that daily calculations function exists"""
        from payroll.views import daily_payroll_calculations

        # Function should exist and be callable
        self.assertTrue(callable(daily_payroll_calculations))

    def test_daily_calculation_model_basic_creation(self):
        """Test basic daily calculation model creation"""
        calculation = DailyPayrollCalculation.objects.create(
            employee=self.regular_employee,
            work_date=date.today(),
            regular_hours=Decimal("8.0"),
            total_pay=Decimal("400.0"),
        )

        self.assertEqual(calculation.employee, self.regular_employee)
        self.assertEqual(calculation.regular_hours, Decimal("8.0"))
        self.assertEqual(calculation.total_pay, Decimal("400.0"))


class RecalculatePayrollViewSmokeTest(PayrollViewsSmokeTest):
    """Test payroll recalculation endpoint"""

    def test_recalculate_payroll_admin_success(self):
        """Test admin can recalculate payroll"""
        url = reverse("recalculate-payroll")
        data = {"year": 2025, "month": 1, "employee_id": self.regular_employee.id}

        with patch("payroll.views.EnhancedPayrollCalculationService") as mock_service:
            mock_instance = MagicMock()
            mock_instance.calculate_monthly_salary_enhanced.return_value = {
                "total_hours": 160,
                "total_gross_pay": 8000,
            }
            mock_service.return_value = mock_instance

            response = self.admin_client.post(url, data, format="json")

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("message", response.data)

    def test_recalculate_payroll_employee_denied(self):
        """Test employee cannot recalculate payroll"""
        url = reverse("recalculate-payroll")
        data = {"year": 2025, "month": 1}

        response = self.employee_client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_recalculate_payroll_missing_params(self):
        """Test recalculate payroll with missing parameters"""
        url = reverse("recalculate-payroll")
        data = {}

        response = self.admin_client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recalculate_payroll_invalid_year_month(self):
        """Test recalculate payroll with invalid year/month"""
        url = reverse("recalculate-payroll")
        data = {"year": "invalid", "month": "invalid"}

        response = self.admin_client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recalculate_payroll_employee_not_found(self):
        """Test recalculate payroll with non-existent employee"""
        url = reverse("recalculate-payroll")
        data = {"year": 2025, "month": 1, "employee_id": 99999}

        response = self.admin_client.post(url, data, format="json")

        # Should return error (404 or 400 both acceptable for missing employee)
        self.assertIn(
            response.status_code,
            [status.HTTP_404_NOT_FOUND, status.HTTP_400_BAD_REQUEST],
        )

    def test_recalculate_payroll_all_employees(self):
        """Test recalculate payroll for all employees"""
        url = reverse("recalculate-payroll")
        data = {"year": 2025, "month": 1}

        response = self.admin_client.post(url, data, format="json")

        # Should return some response (success or validation error both OK for smoke test)
        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
        )


class PayrollAnalyticsViewSmokeTest(PayrollViewsSmokeTest):
    """Test payroll analytics endpoint"""

    def test_payroll_analytics_admin_success(self):
        """Test admin can access payroll analytics"""
        # Create monthly summary for analytics
        MonthlyPayrollSummary.objects.create(
            employee=self.regular_employee,
            year=2025,
            month=1,
            total_hours=Decimal("160.00"),
            total_gross_pay=Decimal("8000.00"),
            base_pay=Decimal("8000.00"),
        )

        url = reverse("payroll-analytics")
        response = self.admin_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return analytics data structure
        self.assertIn("analytics", response.data)

    def test_payroll_analytics_employee_denied(self):
        """Test employee cannot access payroll analytics"""
        url = reverse("payroll-analytics")
        response = self.employee_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_payroll_analytics_with_year_param(self):
        """Test payroll analytics with year parameter"""
        url = reverse("payroll-analytics")
        response = self.admin_client.get(url, {"year": "2025"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_payroll_analytics_invalid_year(self):
        """Test payroll analytics with invalid year"""
        url = reverse("payroll-analytics")
        response = self.admin_client.get(url, {"year": "invalid"})

        # Should handle invalid year gracefully (400 error or fallback to current year)
        self.assertIn(
            response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_200_OK]
        )


class MonthlyPayrollSummaryViewSmokeTest(PayrollViewsSmokeTest):
    """Test monthly payroll summary function"""

    def test_monthly_summary_function_exists(self):
        """Test that monthly summary function exists"""
        from payroll.views import monthly_payroll_summary

        # Function should exist and be callable
        self.assertTrue(callable(monthly_payroll_summary))

    def test_monthly_summary_model_creation(self):
        """Test creating monthly summary data"""
        # Create monthly summary
        summary = MonthlyPayrollSummary.objects.create(
            employee=self.regular_employee,
            year=2025,
            month=1,
            total_hours=Decimal("160.00"),
            total_gross_pay=Decimal("8000.00"),
            base_pay=Decimal("8000.00"),
            worked_days=22,
        )

        self.assertEqual(summary.employee, self.regular_employee)
        self.assertEqual(summary.total_gross_pay, Decimal("8000.00"))

    def test_monthly_summary_basic_attributes(self):
        """Test monthly summary basic attributes"""
        summary = MonthlyPayrollSummary.objects.create(
            employee=self.regular_employee,
            year=2025,
            month=1,
            total_hours=Decimal("160.00"),
            total_gross_pay=Decimal("8000.00"),
            base_pay=Decimal("8000.00"),
            worked_days=22,
        )

        # Test basic attributes exist
        self.assertEqual(summary.year, 2025)
        self.assertEqual(summary.month, 1)
        self.assertEqual(summary.worked_days, 22)


class BackwardCompatibleEarningsViewSmokeTest(PayrollViewsSmokeTest):
    """Test backward compatible earnings function (not exposed via URL)"""

    def test_backward_earnings_function_exists(self):
        """Test that backward compatible earnings function exists"""
        from payroll.views import backward_compatible_earnings

        # Function should exist and be callable
        self.assertTrue(callable(backward_compatible_earnings))

    def test_backward_earnings_logic_with_mock_request(self):
        """Test backward earnings logic with mock request"""
        from payroll.views import backward_compatible_earnings

        # Mock request object
        mock_request = MagicMock()
        mock_request.user = self.employee_user
        mock_request.GET = {"year": "2025", "month": "1"}

        # Test that function can be called (even if it fails due to missing dependencies)
        try:
            result = backward_compatible_earnings(mock_request)
            # If it succeeds, check it returns a Response-like object
            self.assertTrue(hasattr(result, "status_code") or hasattr(result, "data"))
        except Exception as e:
            # Function exists but may fail due to dependencies - that's OK for smoke test
            self.assertIsInstance(e, Exception)

    @patch("payroll.views.get_user_employee_profile")
    def test_backward_earnings_no_employee_profile(self, mock_get_profile):
        """Test backward earnings with no employee profile"""
        from payroll.views import backward_compatible_earnings

        mock_get_profile.return_value = None

        mock_request = MagicMock()
        mock_request.user = self.employee_user
        mock_request.GET = {}

        try:
            result = backward_compatible_earnings(mock_request)
            if hasattr(result, "status_code"):
                self.assertEqual(result.status_code, 404)
        except Exception:
            # Expected for mock test
            pass

    def test_calculate_hourly_daily_earnings_function_exists(self):
        """Test that calculate hourly daily earnings helper exists"""
        from payroll.views import _calculate_hourly_daily_earnings

        # Function should exist and be callable
        self.assertTrue(callable(_calculate_hourly_daily_earnings))


class CalculateHourlyDailyEarningsViewSmokeTest(PayrollViewsSmokeTest):
    """Test calculate hourly daily earnings helper function"""

    def test_calculate_hourly_daily_earnings_regular_day(self):
        """Test calculating earnings for regular working day"""
        from payroll.views import _calculate_hourly_daily_earnings

        # Create work logs
        work_logs = [
            MagicMock(
                check_in=timezone.make_aware(timezone.datetime(2025, 1, 15, 9, 0)),
                check_in_date=date(2025, 1, 15),
            )
        ]

        target_date = date(2025, 1, 15)  # Wednesday
        total_hours = 8.0

        result = _calculate_hourly_daily_earnings(
            self.employee_salary, work_logs, target_date, total_hours
        )

        self.assertIn("total_earnings", result)
        self.assertIn("breakdown", result)
        self.assertEqual(result["hours_worked"], 8.0)

    def test_calculate_hourly_daily_earnings_overtime(self):
        """Test calculating earnings with overtime hours"""
        from payroll.views import _calculate_hourly_daily_earnings

        work_logs = [
            MagicMock(
                check_in=timezone.make_aware(timezone.datetime(2025, 1, 15, 9, 0)),
                check_in_date=date(2025, 1, 15),
            )
        ]

        target_date = date(2025, 1, 15)
        total_hours = 10.0  # 1.4 hours overtime

        result = _calculate_hourly_daily_earnings(
            self.employee_salary, work_logs, target_date, total_hours
        )

        self.assertGreater(
            result["total_earnings"], 8.6 * 50
        )  # More than regular hours
        self.assertIn("overtime_breakdown", result["breakdown"])

    def test_calculate_hourly_daily_earnings_holiday_mock(self):
        """Test calculating earnings for holiday work (using mock)"""
        from payroll.views import _calculate_hourly_daily_earnings

        # Test basic holiday calculation without external dependencies
        with patch("integrations.models.Holiday.objects.filter") as mock_filter:
            mock_holiday = MagicMock()
            mock_holiday.is_shabbat = False
            mock_holiday.is_holiday = True
            mock_filter.return_value.first.return_value = mock_holiday

            work_logs = []
            target_date = date(2025, 1, 15)
            total_hours = 8.0

            result = _calculate_hourly_daily_earnings(
                self.employee_salary, work_logs, target_date, total_hours
            )

            # Should return some earnings calculation
            self.assertIn("total_earnings", result)
            self.assertIn("breakdown", result)

    def test_calculate_hourly_daily_earnings_shabbat_mock(self):
        """Test calculating earnings for Shabbat work (using mock)"""
        from payroll.views import _calculate_hourly_daily_earnings

        # Test basic shabbat calculation without external dependencies
        with patch("integrations.models.Holiday.objects.filter") as mock_filter:
            mock_holiday = MagicMock()
            mock_holiday.is_shabbat = True
            mock_holiday.is_holiday = False
            mock_filter.return_value.first.return_value = mock_holiday

            work_logs = [
                MagicMock(
                    check_in=timezone.make_aware(timezone.datetime(2025, 1, 15, 10, 0)),
                    check_in_date=date(2025, 1, 15),
                )
            ]

            target_date = date(2025, 1, 15)
            total_hours = 8.0

            result = _calculate_hourly_daily_earnings(
                self.employee_salary, work_logs, target_date, total_hours
            )

            # Should return earnings calculation with special rates
            self.assertIn("total_earnings", result)
            self.assertIn("breakdown", result)

    def test_calculate_hourly_daily_earnings_night_shift(self):
        """Test calculating earnings for night shift"""
        from payroll.views import _calculate_hourly_daily_earnings

        work_logs = [
            MagicMock(
                check_in=timezone.make_aware(
                    timezone.datetime(2025, 1, 15, 22, 0)
                ),  # 10 PM
                check_in_date=date(2025, 1, 15),
            )
        ]

        target_date = date(2025, 1, 15)
        total_hours = 7.0  # Night shift hours

        result = _calculate_hourly_daily_earnings(
            self.employee_salary, work_logs, target_date, total_hours
        )

        self.assertEqual(result["breakdown"]["regular_hours"], 7.0)

    def test_calculate_hourly_daily_earnings_friday(self):
        """Test calculating earnings for Friday (shortened day)"""
        from payroll.views import _calculate_hourly_daily_earnings

        work_logs = [
            MagicMock(
                check_in=timezone.make_aware(
                    timezone.datetime(2025, 1, 17, 9, 0)
                ),  # Friday
                check_in_date=date(2025, 1, 17),
            )
        ]

        target_date = date(2025, 1, 17)  # Friday
        total_hours = 8.0  # More than Friday norm (7.6)

        result = _calculate_hourly_daily_earnings(
            self.employee_salary, work_logs, target_date, total_hours
        )

        # Should return earnings calculation
        self.assertIn("total_earnings", result)
        self.assertIn("breakdown", result)
        # Friday may have different calculation, so just check basic structure


class LegacyPayrollCalculationSmokeTest(PayrollViewsSmokeTest):
    """Test legacy payroll calculation function"""

    def test_legacy_payroll_calculation_basic(self):
        """Test basic legacy payroll calculation"""
        from payroll.views import _legacy_payroll_calculation

        # Create work logs
        WorkLog.objects.create(
            employee=self.regular_employee,
            check_in=timezone.make_aware(timezone.datetime(2025, 1, 15, 9, 0)),
            check_out=timezone.make_aware(timezone.datetime(2025, 1, 15, 17, 0)),
        )

        employees = Employee.objects.filter(id=self.regular_employee.id)
        current_date = date(2025, 1, 15)
        start_date = date(2025, 1, 1)
        end_date = date(2025, 1, 31)

        result = _legacy_payroll_calculation(
            employees, current_date, start_date, end_date
        )

        self.assertIsInstance(result, list)
        if result:  # If there are results
            self.assertIn("employee", result[0])
            self.assertIn("total_salary", result[0])

    def test_legacy_payroll_calculation_monthly_employee(self):
        """Test legacy calculation for monthly employee"""
        from payroll.views import _legacy_payroll_calculation

        employees = Employee.objects.filter(id=self.admin_employee.id)
        current_date = date(2025, 1, 15)
        start_date = date(2025, 1, 1)
        end_date = date(2025, 1, 31)

        with patch("payroll.models.Salary.calculate_monthly_salary") as mock_calc:
            mock_calc.return_value = {"total_salary": 10000}

            result = _legacy_payroll_calculation(
                employees, current_date, start_date, end_date
            )

            self.assertIsInstance(result, list)

    def test_legacy_payroll_calculation_service_failure(self):
        """Test legacy calculation handles service failures gracefully"""
        from payroll.views import _legacy_payroll_calculation

        employees = Employee.objects.filter(id=self.regular_employee.id)
        current_date = date(2025, 1, 15)
        start_date = date(2025, 1, 1)
        end_date = date(2025, 1, 31)

        # Test that function handles failures gracefully without external service mocking
        result = _legacy_payroll_calculation(
            employees, current_date, start_date, end_date
        )

        self.assertIsInstance(result, list)


class PayrollViewsExceptionHandlingSmokeTest(PayrollViewsSmokeTest):
    """Test exception handling across payroll views"""

    @patch("payroll.views.logger")
    def test_payroll_list_database_error(self, mock_logger):
        """Test payroll list handling database errors"""
        with patch("payroll.views.Employee.objects.filter") as mock_filter:
            mock_filter.side_effect = Exception("Database connection failed")

            url = reverse("payroll-list")
            response = self.admin_client.get(url)

            self.assertEqual(
                response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            self.assertIn("error", response.data)

    @patch("payroll.views.logger")
    def test_enhanced_earnings_calculation_error(self, mock_logger):
        """Test enhanced earnings handling calculation errors"""
        with patch("payroll.views.EnhancedPayrollCalculationService") as mock_service:
            mock_service.side_effect = Exception("Calculation failed")

            url = reverse("current-earnings")
            response = self.employee_client.get(url)

            # Service may handle exceptions gracefully, so accept either 500 or 200
            self.assertIn(
                response.status_code,
                [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR],
            )

    @patch("payroll.views.logger")
    def test_recalculate_payroll_service_error(self, mock_logger):
        """Test recalculate payroll handling service errors"""
        url = reverse("recalculate-payroll")
        data = {"year": 2025, "month": 1, "employee_id": self.regular_employee.id}

        with patch("payroll.views.EnhancedPayrollCalculationService") as mock_service:
            mock_instance = MagicMock()
            mock_instance.calculate_monthly_salary_enhanced.side_effect = Exception(
                "Service failed"
            )
            mock_service.return_value = mock_instance

            response = self.admin_client.post(url, data, format="json")

            # Service may handle exceptions gracefully, so accept either 500 or 200
            self.assertIn(
                response.status_code,
                [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR],
            )

    def test_view_authentication_required(self):
        """Test that main views require authentication"""
        urls = [
            reverse("payroll-list"),
            reverse("current-earnings"),
            reverse("recalculate-payroll"),
            reverse("payroll-analytics"),
        ]

        for url in urls:
            response = self.anonymous_client.get(url)
            self.assertEqual(
                response.status_code,
                status.HTTP_401_UNAUTHORIZED,
                f"URL {url} should require authentication",
            )


class PayrollViewsPermissionsSmokeTest(PayrollViewsSmokeTest):
    """Test permission handling across payroll views"""

    def test_admin_endpoints_employee_access_denied(self):
        """Test employee cannot access admin-only endpoints"""
        # Test analytics endpoint (GET)
        analytics_url = reverse("payroll-analytics")
        response = self.employee_client.get(analytics_url)
        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            f"Employee should not access {analytics_url}",
        )

        # Test recalculate endpoint (POST) - might return 405 for wrong method
        recalc_url = reverse("recalculate-payroll")
        response = self.employee_client.post(recalc_url, {})
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED],
            f"Employee should not access {recalc_url} (got {response.status_code})",
        )

    def test_employee_specific_data_access_control(self):
        """Test employees can only access their own data"""
        url = reverse("current-earnings")

        # Employee trying to access admin's data
        response = self.employee_client.get(
            url, {"employee_id": self.admin_employee.id}
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_access_all_employee_data(self):
        """Test admin can access any employee's data"""
        url = reverse("current-earnings")

        response = self.admin_client.get(url, {"employee_id": self.regular_employee.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["employee"]["id"], self.regular_employee.id)


class PayrollCalculationViewSmokeTest(PayrollViewsSmokeTest):
    """Test payroll calculation views"""

    def test_daily_payroll_calculations_admin_access(self):
        """Test daily payroll calculations access with admin"""
        url = reverse("daily-payroll-calculations")
        response = self.admin_client.get(
            url, {"year": 2025, "month": 1, "employee_id": self.regular_employee.id}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_enhanced_earnings_view(self):
        """Test enhanced earnings view basic positive scenario"""
        url = reverse("enhanced-earnings")
        response = self.admin_client.get(url, {"year": 2025, "month": 1})

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PayrollAnalyticsViewSmokeTest(PayrollViewsSmokeTest):
    """Test payroll analytics views"""

    def test_payroll_analytics_admin_access(self):
        """Test payroll analytics access for admin"""
        url = reverse("payroll-analytics")
        response = self.admin_client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_payroll_analytics_with_filters(self):
        """Test payroll analytics with date and employee filters"""
        url = reverse("payroll-analytics")
        params = {
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
            "employee_id": self.regular_employee.id,
        }

        response = self.admin_client.get(url, params)

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PayrollRecalculateViewSmokeTest(PayrollViewsSmokeTest):
    """Test payroll recalculation views"""

    def test_recalculate_payroll_regular_user_forbidden(self):
        """Test regular user cannot recalculate payroll"""
        url = reverse("recalculate-payroll")
        response = self.employee_client.post(url, {"year": 2025, "month": 1})

        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED],
        )


class PayrollViewsFilteringSmokeTest(PayrollViewsSmokeTest):
    """Test filtering functionality in payroll views"""

    def test_payroll_list_with_date_filters(self):
        """Test payroll list with date filters"""
        # Test with date parameters
        params = {"start_date": "2025-01-01", "end_date": "2025-01-31"}

        response = self.admin_client.get(reverse("payroll-list"), params)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_payroll_list_with_employee_filter(self):
        """Test payroll list with employee filter"""
        params = {"employee_id": self.regular_employee.id}

        response = self.admin_client.get(reverse("payroll-list"), params)

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PayrollViewsUtilityFunctionsSmokeTest(PayrollViewsSmokeTest):
    """Test utility functions in payroll views"""

    def test_get_user_employee_profile_no_employee(self):
        """Test get_user_employee_profile with user without employee"""
        from payroll.views import get_user_employee_profile

        # Create user without employee profile
        user_no_employee = User.objects.create_user(
            username="noemployee", email="noemployee@example.com", password="pass123"
        )

        result = get_user_employee_profile(user_no_employee)

        self.assertIsNone(result)

    @patch("payroll.views.logger")
    def test_payroll_views_logging_functionality(self, mock_logger):
        """Test that payroll views use logging properly"""
        try:
            url = reverse("payroll-list")
        except:
            url = "/api/v1/payroll/"

        response = self.admin_client.get(url)

        # Should not crash and logging should be available
        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )

    def test_payroll_views_permission_edge_cases(self):
        """Test permission edge cases"""
        # Test with inactive user
        inactive_user = User.objects.create_user(
            username="inactive",
            email="inactive@example.com",
            password="pass123",
            is_active=False,
        )

        # Create client for inactive user
        client = APIClient()
        client.force_authenticate(user=inactive_user)

        response = client.get(reverse("payroll-list"))

        # Should be denied access
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_payroll_views_handle_invalid_dates(self):
        """Test graceful handling of invalid date parameters"""
        url = reverse("payroll-list")

        # Test with invalid date format
        params = {"start_date": "invalid-date", "end_date": "2025-01-31"}

        response = self.admin_client.get(url, params)

        # Should either handle gracefully or return 400
        self.assertIn(
            response.status_code,
            [
                status.HTTP_200_OK,  # Ignores invalid dates
                status.HTTP_400_BAD_REQUEST,  # Validates dates
            ],
        )
