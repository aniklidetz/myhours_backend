"""
Payroll views package - provides backward compatibility for all view imports.

All views are now split into separate modules by functionality:
- payroll_list_views.py - List views and legacy calculations
- earnings_views.py - Earnings calculations
- calculation_views.py - Recalculation operations
- analytics_views.py - Analytics and summaries
"""

import logging

# Create logger for backward compatibility with tests
logger = logging.getLogger(__name__)

from users.models import Employee

# Import models for backward compatibility with tests that patch them
from ..models import DailyPayrollCalculation, MonthlyPayrollSummary

# Import services for test mocking
from ..services.payroll_service import PayrollService

# Import analytics and summary views
from .analytics_views import (
    monthly_payroll_summary,
    payroll_analytics,
)

# Import calculation and recalculation views
from .calculation_views import (
    daily_payroll_calculations,
    recalculate_payroll,
)

# Import earnings calculation views
from .earnings_views import (
    _calculate_hourly_daily_earnings,
    backward_compatible_earnings,
    enhanced_earnings,
)

# Import helper functions
from .helpers import check_admin_or_accountant_role, get_user_employee_profile

# Import all views from payroll_list_views for backward compatibility
from .payroll_list_views import _legacy_payroll_calculation, payroll_list

# Export all view functions for backward compatibility
__all__ = [
    # List views
    "payroll_list",
    "get_user_employee_profile",
    "check_admin_or_accountant_role",
    "_legacy_payroll_calculation",
    # Earnings views
    "enhanced_earnings",
    "backward_compatible_earnings",
    "_calculate_hourly_daily_earnings",
    # Calculation views
    "daily_payroll_calculations",
    "recalculate_payroll",
    # Analytics views
    "payroll_analytics",
    "monthly_payroll_summary",
    # Models for test compatibility
    "MonthlyPayrollSummary",
    "DailyPayrollCalculation",
    "Employee",
    # Services for test compatibility
    "PayrollService",
    # Logger for tests
    "logger",
]
