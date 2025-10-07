"""
Tests for the enhanced payroll calculation strategy.

This module tests the EnhancedPayrollStrategy to ensure proper Israeli labor law
compliance, API integration, and comprehensive payroll calculations.
"""

import pytest
from decimal import Decimal
from payroll.tests.helpers import MONTHLY_NORM_HOURS, ISRAELI_DAILY_NORM_HOURS, NIGHT_NORM_HOURS, MONTHLY_NORM_HOURS
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from django.utils import timezone

from payroll.services.strategies.enhanced import EnhancedPayrollStrategy
from payroll.services.contracts import CalculationContext, PayrollResult
from payroll.services.enums import CalculationStrategy, PayrollStatus, EmployeeType, CalculationMode
from users.models import Employee


class TestEnhancedPayrollStrategy:
    """Test the enhanced payroll strategy with full Israeli labor law compliance"""

    @pytest.fixture
    def context(self):
        """Create a test calculation context"""
        return CalculationContext(
            employee_id=123,
            year=2025,
            month=1,
            user_id=456,
            strategy_hint=None,
            force_recalculate=False,
            fast_mode=False,  # Enable full features
            include_breakdown=True,
            include_daily_details=True
        )

    @pytest.fixture
    def fast_context(self):
        """Create a fast mode calculation context"""
        return CalculationContext(
            employee_id=123,
            year=2025,
            month=1,
            user_id=456,
            strategy_hint=None,
            force_recalculate=False,
            fast_mode=True,  # Fast mode for performance
            include_breakdown=True,
            include_daily_details=False
        )

    @pytest.fixture
    def strategy(self, context):
        """Create an enhanced strategy instance"""
        return EnhancedPayrollStrategy(context)

    @pytest.fixture
    def fast_strategy(self, fast_context):
        """Create an enhanced strategy instance in fast mode"""
        return EnhancedPayrollStrategy(fast_context)

    @pytest.fixture
    def mock_hourly_employee(self):
        """Create a mock hourly employee with salary info"""
        employee = Mock(spec=Employee)
        employee.id = 123
        employee.get_full_name.return_value = "Test Hourly Employee"

        # Mock hourly salary info
        mock_salary = Mock()
        mock_salary.hourly_rate = Decimal('35.0')  # Use correct field name and type
        mock_salary.calculation_type = "hourly"
        mock_salary.currency = "ILS"
        mock_salary.base_salary = None
        employee.salary_info = mock_salary
        # Add proper salary filter mock for _get_salary_info method
        employee.salaries.filter.return_value.first.return_value = mock_salary

        return employee

    @pytest.fixture
    def mock_monthly_employee(self):
        """Create a mock monthly employee with salary info"""
        employee = Mock(spec=Employee)
        employee.id = 456
        employee.get_full_name.return_value = "Test Monthly Employee"

        # Mock monthly salary info
        mock_salary = Mock()
        mock_salary.hourly_rate = None
        mock_salary.calculation_type = "monthly"
        mock_salary.currency = "ILS"
        mock_salary.base_salary = Decimal('12000.0')  # Use correct type
        employee.salary_info = mock_salary
        # Add proper salary filter mock for _get_salary_info method
        employee.salaries.filter.return_value.first.return_value = mock_salary

        return employee

    @pytest.fixture
    def mock_work_logs_regular(self):
        """Create mock work logs for regular work days"""
        logs = []
        for day in range(1, 21):  # 20 work days
            log = Mock()
            log.check_in = timezone.make_aware(datetime(2025, 1, day, 9, 0))  # 9 AM start
            # Regular 8 hour days, some with overtime
            hours = ISRAELI_DAILY_NORM_HOURS if day <= 15 else Decimal('10.0')
            # Calculate check_out based on hours + break
            log.check_out = log.check_in + timedelta(hours=float(hours), minutes=60)  # Add break time
            log.get_total_hours.return_value = hours
            log.employee_id = 123
            log.break_minutes = 60  # 1 hour break
            logs.append(log)
        return logs

    @pytest.fixture
    def mock_work_logs_with_specials(self):
        """Create mock work logs with holiday and sabbath work"""
        logs = []

        # Regular weekdays
        for day in [1, 2, 3, 6, 7, 8, 9, 10]:
            log = Mock()
            log.check_in = timezone.make_aware(datetime(2025, 1, day, 9, 0))
            log.check_out = log.check_in + timedelta(hours=float(ISRAELI_DAILY_NORM_HOURS), minutes=60)  # Add check_out
            log.get_total_hours.return_value = ISRAELI_DAILY_NORM_HOURS
            log.employee_id = 123
            log.break_minutes = 60
            logs.append(log)

        # Holiday work (January 1st - New Year)
        holiday_log = Mock()
        holiday_log.check_in = timezone.make_aware(datetime(2025, 1, 1, 10, 0))
        holiday_log.check_out = holiday_log.check_in + timedelta(hours=6, minutes=30)  # Add check_out
        holiday_log.get_total_hours.return_value = Decimal('6.0')
        holiday_log.employee_id = 123
        holiday_log.break_minutes = 30
        logs.append(holiday_log)

        # Saturday work (Sabbath)
        sabbath_log = Mock()
        sabbath_log.check_in = timezone.make_aware(datetime(2025, 1, 4, 10, 0))  # Saturday
        sabbath_log.check_out = sabbath_log.check_in + timedelta(hours=5, minutes=30)  # Add check_out
        sabbath_log.get_total_hours.return_value = Decimal('5.0')
        sabbath_log.employee_id = 123
        sabbath_log.break_minutes = 30
        logs.append(sabbath_log)

        return logs

    def test_strategy_initialization(self, strategy):
        """Test enhanced strategy initialization"""
        assert strategy._employee_id == 123
        assert strategy._year == 2025
        assert strategy._month == 1
        assert strategy._fast_mode is False
        assert strategy._strategy_name == "EnhancedPayrollStrategy"
        assert strategy._api_usage == {
            "sunrise_sunset_calls": 0,
            "hebcal_calls": 0,
            "precise_sabbath_times": 0,
            "api_holidays_found": 0,
            "fallback_calculations": 0,
            "redis_cache_hits": 0,
            "redis_cache_misses": 0,
        }
        assert strategy._calculation_errors == []
        assert strategy._warnings == []

    def test_fast_mode_strategy_initialization(self, fast_strategy):
        """Test enhanced strategy initialization in fast mode"""
        assert fast_strategy._fast_mode is True
        assert fast_strategy._include_daily_details is False

    @patch('payroll.services.strategies.enhanced.Employee.objects')
    def test_get_employee_with_relations(self, mock_objects, strategy, mock_hourly_employee):
        """Test employee retrieval with enhanced relations"""
        # Setup complex query mock chain
        mock_queryset = Mock()
        mock_queryset.select_related.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset
        mock_queryset.get.return_value = mock_hourly_employee
        mock_objects.select_related.return_value = mock_queryset

        result = strategy._get_employee_with_relations()

        assert result == mock_hourly_employee
        mock_objects.select_related.assert_called_once_with('user')
        mock_queryset.prefetch_related.assert_called()
        mock_queryset.get.assert_called_once_with(id=123)

    def test_determine_calculation_mode_hourly(self, strategy, mock_hourly_employee):
        """Test calculation mode determination for hourly employees"""
        salary = mock_hourly_employee.salary_info
        mode = strategy._determine_calculation_mode(salary)
        assert mode == CalculationMode.HOURLY

    def test_determine_calculation_mode_monthly(self, strategy, mock_monthly_employee):
        """Test calculation mode determination for monthly employees"""
        salary = mock_monthly_employee.salary_info
        mode = strategy._determine_calculation_mode(salary)
        assert mode == CalculationMode.MONTHLY

    def test_israeli_labor_law_constants(self, strategy):
        """Test that Israeli labor law constants are correctly defined"""
        assert strategy.MAX_DAILY_HOURS == Decimal("12")
        assert strategy.MAX_WEEKLY_REGULAR_HOURS == Decimal("42")
        assert strategy.MAX_WEEKLY_OVERTIME_HOURS == Decimal("16")
        assert strategy.OVERTIME_RATE_125 == Decimal("1.25")
        assert strategy.OVERTIME_RATE_150 == Decimal("1.50")
        assert strategy.HOLIDAY_RATE == Decimal("1.50")
        assert strategy.SABBATH_RATE == Decimal("1.50")
        assert strategy.SABBATH_OVERTIME_RATE_175 == Decimal("1.75")
        assert strategy.SABBATH_OVERTIME_RATE_200 == Decimal("2.00")

    @patch('payroll.services.strategies.enhanced.enhanced_payroll_cache')
    def test_get_holidays_enhanced_cache_hit(self, mock_cache, strategy):
        """Test enhanced holiday retrieval with cache hit"""
        cached_holidays = {
            date(2025, 1, 1): {'name': 'New Year', 'is_paid': True, 'source': 'database'}
        }
        mock_cache.get_holidays.return_value = cached_holidays

        result = strategy._get_holidays_enhanced()

        assert result == cached_holidays
        assert strategy._holidays_cache == cached_holidays
        assert strategy._api_usage["redis_cache_hits"] == 1
        mock_cache.get_holidays.assert_called_once_with(2025, 1)

    @patch('payroll.services.strategies.enhanced.enhanced_payroll_cache')
    @patch('payroll.services.strategies.enhanced.Holiday.objects')
    def test_get_holidays_enhanced_cache_miss(self, mock_holiday_objects, mock_cache, strategy):
        """Test enhanced holiday retrieval with cache miss and database fallback"""
        mock_cache.get_holidays.return_value = None

        mock_holidays = [
            {'date': date(2025, 1, 1), 'name': 'New Year', 'is_paid': True}
        ]
        mock_holiday_objects.filter.return_value.values.return_value = mock_holidays

        result = strategy._get_holidays_enhanced()

        expected = {
            date(2025, 1, 1): {'name': 'New Year', 'is_paid': True, 'source': 'database'}
        }
        assert result == expected
        assert strategy._api_usage["redis_cache_misses"] == 1
        mock_cache.set_holidays.assert_called_once_with(2025, 1, expected)


    def test_validate_legal_compliance_normal_hours(self, strategy, mock_work_logs_regular):
        """Test legal compliance validation with normal work hours"""
        # Regular 8-hour logs should pass validation
        normal_logs = [log for log in mock_work_logs_regular if log.get_total_hours() <= ISRAELI_DAILY_NORM_HOURS]

        strategy._validate_legal_compliance(normal_logs)

        assert strategy._warnings == []  # No warnings for normal hours

    def test_validate_legal_compliance_excessive_hours(self, strategy):
        """Test legal compliance validation with excessive daily hours"""
        # Create a log with excessive hours
        excessive_log = Mock()
        excessive_log.check_in = timezone.make_aware(datetime(2025, 1, 15, 8, 0))
        excessive_log.get_total_hours.return_value = Decimal('14.0')  # Exceeds 12 hour limit

        strategy._validate_legal_compliance([excessive_log])

        assert len(strategy._warnings) == 1
        assert "Daily hours (14.0) exceed legal maximum (12)" in strategy._warnings[0]

    @patch('payroll.services.strategies.enhanced.night_hours')
    def test_calculate_night_shift_hours(self, mock_night_hours, strategy):
        """Test night shift hours calculation"""
        mock_night_hours.return_value = 3.5  # 3.5 hours of night work

        work_log = Mock()
        work_log.check_in = datetime(2025, 1, 15, 21, 0)  # 9 PM
        work_log.check_out = datetime(2025, 1, 16, 3, 0)   # 3 AM next day

        result = strategy._calculate_night_shift_hours(work_log)

        assert result == Decimal('3.5')
        mock_night_hours.assert_called_once_with(work_log.check_in, work_log.check_out)

    @patch.object(EnhancedPayrollStrategy, '_get_employee_with_relations')
    @patch.object(EnhancedPayrollStrategy, '_get_holidays_enhanced')
    @patch.object(EnhancedPayrollStrategy, '_get_work_logs_enhanced')
    @patch.object(EnhancedPayrollStrategy, '_calculate_hourly_employee')
    def test_calculate_hourly_employee_flow(self, mock_calc_hourly, mock_get_logs,
                                          mock_get_holidays, mock_get_employee,
                                          strategy, mock_hourly_employee, mock_work_logs_regular):
        """Test complete calculation flow for hourly employee"""
        # Setup mocks
        mock_get_employee.return_value = mock_hourly_employee
        mock_get_holidays.return_value = {}
        mock_get_logs.return_value = mock_work_logs_regular

        expected_result = PayrollResult(
            total_salary=Decimal('5000.00'),
            total_hours=Decimal('160.0'),
            regular_hours=Decimal('150.0'),
            overtime_hours=Decimal('10.0'),
            holiday_hours=Decimal('0.0'),
            shabbat_hours=Decimal('0.0'),
            breakdown={},
            metadata={'calculation_strategy': 'enhanced'}
        )
        mock_calc_hourly.return_value = expected_result

        result = strategy.calculate()

        assert result == expected_result
        mock_get_employee.assert_called_once()
        mock_get_holidays.assert_called_once()
        mock_get_logs.assert_called_once_with(mock_hourly_employee)
        mock_calc_hourly.assert_called_once()

    def test_hourly_employee_overtime_calculation(self, strategy, mock_hourly_employee, mock_work_logs_regular):
        """Test detailed overtime calculation for hourly employees"""
        # Mock the dependencies to avoid database calls
        with patch.object(strategy, '_get_holidays_enhanced', return_value={}):
            with patch.object(strategy, '_calculate_night_shift_hours', return_value=Decimal('0.0')):

                result = strategy._calculate_hourly_employee(
                    mock_hourly_employee,
                    mock_hourly_employee.salary_info,
                    mock_work_logs_regular,
                    {}
                )

                # Verify overtime calculation
                assert result['overtime_hours'] > Decimal('0')  # Should have overtime
                assert result['metadata']['calculation_strategy'] == 'enhanced_critical_points'
                assert result['metadata']['employee_type'] == 'hourly'

                # Verify breakdown has detailed overtime rates
                breakdown = result['breakdown']
                assert 'overtime_125_hours' in breakdown
                assert 'overtime_125_rate' in breakdown
                assert 'overtime_125_pay' in breakdown

    def test_monthly_employee_bonus_calculation(self, strategy, mock_monthly_employee):
        """Test bonus calculation for monthly employees"""
        # Create work logs with overtime
        overtime_logs = []
        for day in range(1, 6):  # 5 days
            log = Mock()
            log.check_in = timezone.make_aware(datetime(2025, 1, day, 9, 0))
            log.check_out = log.check_in + timedelta(hours=10, minutes=60)  # 10 hours + break
            log.get_total_hours.return_value = Decimal('10.0')  # 1.4 hours over 8.6 norm
            log.employee_id = 456
            overtime_logs.append(log)

        # Mock the dependencies
        with patch.object(strategy, '_get_holidays_enhanced', return_value={}):

            result = strategy._calculate_monthly_employee(
                mock_monthly_employee,
                mock_monthly_employee.salary_info,
                overtime_logs,
                {}
            )

            # Calculate expected result for 5 days of work
            total_hours = Decimal('50.0')  # 5 days * 10 hours
            monthly_salary = Decimal('12000.0')
            monthly_norm = Decimal('182')  # Monthly norm hours

            # For 5 days of 10 hours each, proportional base salary
            proportional_base = (total_hours / monthly_norm) * monthly_salary

            # Verify proportional calculation (not full monthly salary for 5 days)
            assert result['total_salary'] > proportional_base  # Should include overtime bonuses
            assert result['total_salary'] < monthly_salary  # But less than full monthly salary
            assert result['metadata']['employee_type'] == 'monthly'

            # Verify breakdown has base salary
            breakdown = result['breakdown']
            assert breakdown['base_monthly_salary'] == Decimal('12000.0')
            assert 'overtime_125_hours' in breakdown  # Should have overtime bonuses


class TestEnhancedStrategyIntegration:
    """Integration tests for enhanced strategy with realistic scenarios"""

    def test_holiday_work_premium_calculation(self):
        """Test that holiday work gets proper premium rates"""
        context = CalculationContext(
            employee_id=789,
            year=2025,
            month=1,
            user_id=456,
            strategy_hint=None,
            force_recalculate=False,
            fast_mode=True,  # Fast mode to avoid API calls
            include_breakdown=True,
            include_daily_details=False
        )

        strategy = EnhancedPayrollStrategy(context)

        # Mock employee
        employee = Mock()
        employee.id = 789
        salary = Mock()
        salary.hourly_rate = Decimal('40.0')  # Fix field name
        salary.calculation_type = "hourly"
        salary.currency = "ILS"
        employee.salary_info = salary

        # Holiday work log
        holiday_log = Mock()
        holiday_log.check_in = timezone.make_aware(datetime(2025, 1, 1, 9, 0))
        holiday_log.check_out = holiday_log.check_in + timedelta(hours=float(ISRAELI_DAILY_NORM_HOURS), minutes=60)  # Add check_out
        holiday_log.get_total_hours.return_value = ISRAELI_DAILY_NORM_HOURS
        holiday_log.employee_id = 789

        holidays = {
            date(2025, 1, 1): {'name': 'New Year', 'is_paid': True}
        }

        with patch.object(strategy, '_calculate_night_shift_hours', return_value=Decimal('0.0')):
            result = strategy._calculate_hourly_employee(employee, salary, [holiday_log], holidays)

            # Verify holiday premium (150% rate)
            assert result['holiday_hours'] == ISRAELI_DAILY_NORM_HOURS
            expected_holiday_pay = ISRAELI_DAILY_NORM_HOURS * Decimal('40.0') * Decimal('1.5')  # 480.0
            assert result['breakdown']['holiday_pay'] == float(expected_holiday_pay)
            assert result['breakdown']['holiday_rate'] == 60.0  # 40 * 1.5

    def test_sabbath_work_premium_calculation(self):
        """Test that Sabbath work gets proper premium rates"""
        context = CalculationContext(
            employee_id=790,
            year=2025,
            month=1,
            user_id=456,
            strategy_hint=None,
            force_recalculate=False,
            fast_mode=True,
            include_breakdown=True,
            include_daily_details=False
        )

        strategy = EnhancedPayrollStrategy(context)

        # Mock employee
        employee = Mock()
        employee.id = 790
        salary = Mock()
        salary.hourly_rate = Decimal('30.0')  # Fix field name
        salary.calculation_type = "hourly"
        salary.currency = "ILS"
        employee.salary_info = salary

        # Saturday work log - 6 hours work + 30 minutes break = 6.5 total duration
        sabbath_log = Mock()
        sabbath_log.check_in = timezone.make_aware(datetime(2025, 1, 4, 10, 0))  # Saturday
        sabbath_log.check_out = sabbath_log.check_in + timedelta(hours=6, minutes=30)  # Add check_out
        sabbath_log.employee_id = 790

        with patch.object(strategy, '_calculate_night_shift_hours', return_value=Decimal('0.0')):
            result = strategy._calculate_hourly_employee(employee, salary, [sabbath_log], {})

            # Verify Sabbath premium (150% rate)
            # Algorithm calculates real duration: 6.5 hours (includes break time in total duration)
            assert result['shabbat_hours'] == Decimal('6.5')
            expected_sabbath_pay = Decimal('6.5') * Decimal('30.0') * Decimal('1.5')  # 292.5
            assert result['breakdown']['sabbath_pay'] == float(expected_sabbath_pay)
            assert result['breakdown']['sabbath_rate'] == 45.0  # 30 * 1.5
