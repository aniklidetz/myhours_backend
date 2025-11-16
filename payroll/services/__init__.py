# Payroll services package

from . import payroll_service as _payroll_service
from .payroll_service import PayrollService
from .strategies.enhanced import EnhancedPayrollStrategy


# Mock compatibility: tests patch payroll.services.self.payroll_service.*
class _CompatSelf:
    pass


self = _CompatSelf()
self.payroll_service = _payroll_service  # provide path for mock patches

__all__ = ["EnhancedPayrollStrategy", "PayrollService", "self"]
