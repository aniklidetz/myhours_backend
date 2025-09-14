"""
Custom warning classes for payroll system.

This module defines specialized warning classes to provide better
control over warning visibility and categorization.
"""


class LegacyWarning(Warning):
    """
    Warning for deprecated legacy code usage.
    
    This warning is always visible (not filtered by default)
    and indicates usage of deprecated functionality that
    should be migrated to newer implementations.
    
    Examples:
        - Usage of OptimizedPayrollService (removed due to incorrect calculations)
        - Legacy management commands targeting removed services
        - Deprecated API endpoints or parameters
    """
    pass