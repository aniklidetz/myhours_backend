def create_test_employee(first_name="Test", last_name="User", email=None, employment_type="hourly"):
    """Helper function to create a test employee."""
    from core.models import Employee
    
    if email is None:
        email = f"{first_name.lower()}.{last_name.lower()}@example.com"
        
    return Employee.objects.create(
        first_name=first_name,
        last_name=last_name,
        email=email,
        employment_type=employment_type
    )