"""
Temporary adapter classes for backward compatibility during payroll system migration.

These classes provide legacy interface compatibility while using the new PayrollService internally.
They are scheduled for removal once all client code is migrated to use PayrollService directly.

SCHEDULED FOR REMOVAL: See docs/PAYROLL_ADAPTER_REMOVAL_PLAN.md
"""

import warnings
from typing import Dict, Any

from ..services.payroll_service import PayrollService
from ..services.contracts import CalculationContext
from ..services.enums import CalculationStrategy, EmployeeType
from ..warnings import LegacyWarning

# Ensure legacy warnings are always visible
warnings.simplefilter("always", LegacyWarning)


class PayrollCalculationService:
    """
    Temporary adapter for legacy PayrollCalculationService usage.
    
    This class provides backward compatibility during migration to PayrollService.
    All calls are proxied to PayrollService with CalculationStrategy.ENHANCED.
    
    DEPRECATED: Use PayrollService directly with CalculationContext.
    """
    
    def __init__(self, employee, year, month, fast_mode=False):
        warnings.warn(
            "PayrollCalculationService is deprecated. Use PayrollService with CalculationContext instead.",
            LegacyWarning,
            stacklevel=2
        )
        self.employee = employee
        self.year = year
        self.month = month
        self.fast_mode = fast_mode
    
    def calculate_monthly_salary_enhanced(self) -> Dict[str, Any]:
        """
        Legacy method that proxies to PayrollService.calculate().
        
        Returns:
            Dict with legacy format keys mapped from new PayrollService result
        """
        # Determine employee type based on salary configuration
        employee_type = EmployeeType.HOURLY if (
            hasattr(self.employee, 'salaries') and 
            self.employee.salaries.filter(is_active=True, calculation_type='hourly').exists()
        ) else EmployeeType.MONTHLY
        
        # Create context for new service
        context = CalculationContext(
            employee_id=self.employee.id,
            year=self.year,
            month=self.month,
            user_id=1,  # Default system user for legacy compatibility
            employee_type=employee_type,
            fast_mode=self.fast_mode
        )
        
        # Call new service
        service = PayrollService()
        result = service.calculate(context, CalculationStrategy.ENHANCED)
        
        # Map new result structure to legacy format for backward compatibility
        return {
            'total_gross_pay': result.get('total_salary', 0),
            'total_hours': result.get('total_hours', 0),
            'regular_hours': result.get('regular_hours', 0),
            'overtime_hours': result.get('overtime_hours', 0)
        }


class EnhancedPayrollCalculationService(PayrollCalculationService):
    """
    Temporary adapter extending the base PayrollCalculationService adapter.
    
    This class exists purely for backward compatibility with code that references
    EnhancedPayrollCalculationService specifically. All functionality is inherited
    from the base adapter.
    
    DEPRECATED: Use PayrollService directly with CalculationContext.
    """
    
    def __init__(self, employee, year, month, fast_mode=False):
        warnings.warn(
            "EnhancedPayrollCalculationService is deprecated. Use PayrollService with CalculationContext instead.",
            LegacyWarning,
            stacklevel=2
        )
        super().__init__(employee, year, month, fast_mode)