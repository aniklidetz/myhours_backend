# users tests package - conditional imports to handle missing modules
try:
    from .test_employee_api import *  # noqa: F401,F403
except ImportError:
    pass

try:
    from .test_employee_comprehensive import *  # noqa: F401,F403
except ImportError:
    pass
