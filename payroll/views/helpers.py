"""
Helper functions shared across payroll views.
"""

import logging

logger = logging.getLogger(__name__)


def get_user_employee_profile(user):
    """
    Helper function to get employee profile for a user.

    Returns None if user has no employee profile or if there's an AttributeError.
    """
    try:
        return user.employees.first()
    except AttributeError:
        return None


def check_admin_or_accountant_role(user):
    """
    Helper function to check if user has admin or accountant role.

    Returns True if user has admin or accountant role, False otherwise.
    """
    employee = get_user_employee_profile(user)
    return employee and employee.role in ["accountant", "admin"]
