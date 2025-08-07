# core/models.py
# Import models from new applications for backward compatibility
from integrations.models import Holiday
from payroll.models import Salary
from users.models import Employee
from worktime.models import WorkLog

# Now, if any existing code imports from core.models,
# it will still have access to the required models
