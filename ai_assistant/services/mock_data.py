"""
Mock data service for AI Assistant.

This module provides mock salary data for the AI explainer.
In production, this will be replaced with real data from:
- PayrollService
- DailyPayrollCalculation
- Employee models

The structure mirrors the actual PayrollResult format for easy migration.
"""

from decimal import Decimal
from typing import Any, Dict


def get_mock_salary_data(employee_id: int, period: str) -> Dict[str, Any]:
    """
    Get mock salary data for AI explanation.

    In production, this function will:
    1. Call PayrollService.calculate_monthly_payroll(employee_id, year, month)
    2. Fetch DailyPayrollCalculation records
    3. Get employee details from Employee model

    Args:
        employee_id: ID of the employee
        period: Period string (e.g., "October 2025")

    Returns:
        Dictionary with salary breakdown matching PayrollResult structure
    """

    # Mock data structure - mirrors actual PayrollResult
    return {
        "employee_info": {
            "id": employee_id,
            "name": "Itai Shapiro",
            "employment_type": "full_time",
            "calculation_type": "hourly",
        },
        "period": period,
        "summary": {
            "total_hours_worked": Decimal("186.5"),
            "regular_hours": Decimal("160.0"),
            "overtime_125_hours": Decimal("18.5"),
            "overtime_150_hours": Decimal("8.0"),
            "shabbat_hours": Decimal("8.0"),
            "holiday_hours": Decimal("0.0"),
            "night_hours": Decimal("12.0"),
        },
        "rates": {
            "base_hourly_rate": Decimal("55.00"),
            "overtime_125_rate": Decimal("68.75"),  # 55 * 1.25
            "overtime_150_rate": Decimal("82.50"),  # 55 * 1.50
            "shabbat_rate": Decimal("82.50"),  # 55 * 1.50
            "holiday_rate": Decimal("82.50"),  # 55 * 1.50
            "night_bonus_rate": Decimal("5.50"),  # 10% of base
        },
        "earnings": {
            "base_pay": Decimal("8800.00"),  # 160 * 55
            "overtime_125_pay": Decimal("1271.88"),  # 18.5 * 68.75
            "overtime_150_pay": Decimal("660.00"),  # 8 * 82.50
            "shabbat_bonus": Decimal("660.00"),  # 8 * 82.50
            "holiday_bonus": Decimal("0.00"),
            "night_bonus": Decimal("66.00"),  # 12 * 5.50
            "total_gross": Decimal("11457.88"),
        },
        "deductions": {
            "income_tax": Decimal("1145.79"),  # ~10%
            "national_insurance": Decimal("343.74"),  # ~3%
            "health_insurance": Decimal("572.89"),  # ~5%
            "pension_employee": Decimal("687.47"),  # 6%
            "total_deductions": Decimal("2749.89"),
        },
        "net_pay": Decimal("8707.99"),
        "work_days": {
            "total_work_days": 22,
            "actual_worked_days": 20,
            "sick_days": 1,
            "vacation_days": 1,
        },
        # Specific component details for AI explanation
        "components_detail": {
            "shabbat_work": {
                "date": "2025-10-11",
                "hours": 8,
                "base_rate": "55 NIS/hour",
                "multiplier": "x1.50",
                "reason": "Standard Shabbat premium per Israeli labor law",
                "calculation": "8 hours * 55 NIS * 1.50 = 660 NIS",
                "amount": Decimal("660.00"),
            },
            "overtime": {
                "first_2_hours": {
                    "hours": 18.5,
                    "multiplier": "x1.25",
                    "calculation": "18.5 hours * 55 NIS * 1.25 = 1,271.88 NIS",
                },
                "beyond_2_hours": {
                    "hours": 8,
                    "multiplier": "x1.50",
                    "calculation": "8 hours * 55 NIS * 1.50 = 660 NIS",
                },
            },
            "night_shift": {
                "hours": 12,
                "bonus_percentage": "10%",
                "calculation": "12 hours * 55 NIS * 0.10 = 66 NIS",
            },
        },
        # Legal references for citations
        "legal_references": [
            {
                "law": "Hours of Work and Rest Law, 5711-1951",
                "section": "Section 16",
                "description": "Overtime pay: 125% for first 2 hours, 150% beyond",
            },
            {
                "law": "Hours of Work and Rest Law, 5711-1951",
                "section": "Section 17",
                "description": "Shabbat and holiday work: 150% premium",
            },
            {
                "law": "Protection of Wages Law, 5718-1958",
                "section": "Section 6",
                "description": "Night work bonus requirements",
            },
        ],
    }


def get_employee_context(employee_id: int) -> Dict[str, Any]:
    """
    Get employee context for personalized AI responses.

    Args:
        employee_id: ID of the employee

    Returns:
        Dictionary with employee preferences and history
    """
    return {
        "preferred_language": "he",  # Hebrew
        "previous_queries": [
            "Why is my overtime different this month?",
            "Explain my Shabbat bonus",
        ],
        "employment_start_date": "2023-03-15",
        "department": "Operations",
    }
