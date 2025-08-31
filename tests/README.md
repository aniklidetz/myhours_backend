# MyHours Test Guidelines 
## Employee Salary Contract Understanding the Employee-Salary relationship is critical for writing correct tests: 
### Core Contract 
```python
# Correct usage for single active salary
salary = employee.salary_info # Property returns Salary|None # Correct usage for QuerySet operations all_salaries = employee.salaries.all() # RelatedManager returns QuerySet[Salary] # WRONG - This will cause AttributeError
salary = employee.salary_info.filter(is_active=True).first() # DON'T DO THIS!
``` ### Interface Details - **`employee.salary_info`**: Property returning the active `Salary` object or `None`
- **`employee.salaries`**: RelatedManager providing `QuerySet[Salary]` for all salaries
- **Priority**: `hourly` > `monthly` > `project` (in terms of common usage) ### Safe Testing Utilities Use the helpers from `tests.test_utils`: ```python
from tests.test_utils import get_active_salary, assert_salary_contract, create_test_salary # Safe salary access
salary = get_active_salary(employee) # Handles contract validation # Contract verification
assert_salary_contract(employee) # Use in test setUp() or assertions # Test data creation
salary = create_test_salary(employee, "hourly", hourly_rate=Decimal("75.00"))
``` ### Status Code Expectations After fixing the salary_info bugs, tests should expect correct status codes: ```python
# Good - specific expectations with reasoning
self.assertEqual(response.status_code, status.HTTP_00_OK) # Good - handle multiple valid outcomes self.assertIn(response.status_code, [ status.HTTP_00_OK, # Success case status.HTTP_404_NOT_FOUND, # When employee has no salary
]) # Avoid - accepting 500 errors unless testing error handling
self.assertIn(response.status_code, [ status.HTTP_00_OK, status.HTTP_500_INTERNAL_SERVER_ERROR, # This suggests a bug!
]) # Debugging - catch unexpected server errors from tests.test_utils import assert_response_not_server_error
assert_response_not_server_error(response, self)
``` ## Running Tests ### Local Testing (with pytest)
```bash
# Fast critical tests
DJANGO_SETTINGS_MODULE=myhours.settings_ci ./venv/bin/pytest -q -k "salary_info or employee_relationship" --maxfail=# Specific modules
DJANGO_SETTINGS_MODULE=myhours.settings_ci ./venv/bin/pytest users/tests -k "activate or invitation" -q --no-cov
DJANGO_SETTINGS_MODULE=myhours.settings_ci ./venv/bin/pytest payroll/tests/test_views_targeted.py -q --no-cov
``` ### Docker Testing (with Django test runner)
```bash
# IMPORTANT: In Docker NO pytest, use only Django test runner! # Targeted tests
docker compose exec web python manage.py test payroll.tests.test_views_targeted --failfast -v docker compose exec web python manage.py test users.tests.test_auth_views --failfast -v docker compose exec web python manage.py test tests.test_celery_configuration --failfast -v # Module tests
docker compose exec web python manage.py test payroll.tests --failfast
docker compose exec web python manage.py test users.tests --failfast
docker compose exec web python manage.py test biometrics.tests --failfast # Smoke tests docker compose exec web python manage.py test payroll.tests.test_models_smoke --failfast -v 0
docker compose exec web python manage.py test core.tests --failfast -v 0 # Full test suite with early stop
docker compose exec web python manage.py test --failfast --parallel 4 # NOT WORKS в Docker:
# docker compose exec web pytest payroll/tests/test_views_targeted.py -q
# Error: "pytest": executable file not found in $PATH
``` ### CI-Style Testing
```bash
# Mimics CI environment (local)
DJANGO_SETTINGS_MODULE=myhours.settings_ci DATABASE_URL="postgresql://myhours_user:secure_password_@localhost:54/myhours_test" SECRET_KEY="test-secret-key" ./venv/bin/pytest -q --maxfail=5 --no-cov # Docker CI-style
docker compose exec web python manage.py test --failfast --parallel 4
``` ## Factory Patterns When creating test data, use consistent factories: ```python
# Preferred - factory approach
salary = create_test_salary(employee, "hourly")
salary = create_test_salary(employee, "monthly", base_salary=Decimal("5000.00")) salary = create_test_salary(employee, "project", project_end_date="05--") # Avoid - manual creation without validation
salary = Salary.objects.create(employee=employee, ...) # Missing contract checks
``` ## Common Pitfalls . **Contract Violations**: Using `.filter()` on `salary_info` property
. **Server Error Acceptance**: Accepting 500 status codes when they indicate bugs
. **Manual Data Creation**: Creating test data without using safe factories
4. **Missing Validation**: Not using protective assertions in test setup ## Debugging Failed Tests If a test fails with unexpected behavior: . **Check the contract**: Is `salary_info` being used correctly?
. **Validate test data**: Are you using the test utilities?
. **Examine status codes**: Are you getting 500s that should be 00/400/404?
4. **Use debug helpers**: Add `assert_response_not_server_error()` calls ## Migration Guide If you have existing tests that fail after these changes: ```python
# OLD (broken)
salary = employee.salary_info.filter(is_active=True).first() # NEW (correct) from tests.test_utils import get_active_salary
salary = get_active_salary(employee) # OLD (fragile)
self.assertIn(response.status_code, [00, 500]) # NEW (robust)
from tests.test_utils import assert_response_not_server_error assert_response_not_server_error(response, self)
self.assertEqual(response.status_code, 00)
```