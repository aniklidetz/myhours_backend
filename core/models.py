# core/models.py
# Import models from new applications for backward compatibility
from users.models import Employee
from worktime.models import WorkLog
from payroll.models import Salary
from integrations.models import Holiday

# Now, if any existing code imports from core.models,
# it will still have access to the required models