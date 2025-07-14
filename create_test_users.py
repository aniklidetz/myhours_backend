from django.contrib.auth.models import User
from users.models import Employee

# Test users data
test_users = [
    {
        'username': 'employee1',
        'email': 'employee1@example.com',
        'password': 'test123',
        'first_name': 'John',
        'last_name': 'Employee',
        'role': 'employee'
    },
    {
        'username': 'accountant1',
        'email': 'accountant1@example.com',
        'password': 'test123',
        'first_name': 'Jane',
        'last_name': 'Accountant',
        'role': 'accountant'
    },
    {
        'username': 'admin2',
        'email': 'admin2@example.com',
        'password': 'test123',
        'first_name': 'Bob',
        'last_name': 'Admin',
        'role': 'admin'
    }
]

for user_data in test_users:
    # Check if user already exists
    if not User.objects.filter(username=user_data['username']).exists():
        # Create Django user
        user = User.objects.create_user(
            username=user_data['username'],
            email=user_data['email'],
            password=user_data['password'],
            first_name=user_data['first_name'],
            last_name=user_data['last_name']
        )
        
        # Set permissions based on role
        if user_data['role'] == 'admin':
            user.is_staff = True
            user.is_superuser = True
        elif user_data['role'] == 'accountant':
            user.is_staff = True
            user.is_superuser = False
        
        user.save()
        
        # Create Employee profile
        Employee.objects.create(
            user=user,
            first_name=user_data['first_name'],
            last_name=user_data['last_name'],
            email=user_data['email'],
            phone='+1234567890',
            employment_type='full_time',
            hourly_rate=50.00,
            role=user_data['role']
        )
        
        print(f"✅ Created {user_data['role']}: {user_data['username']} (password set)")
    else:
        print(f"ℹ️ User already exists: {user_data['username']}")

print("\nTest users ready! You can login with usernames:")
print("- Employee: employee1")
print("- Accountant: accountant1")  
print("- Admin: admin2")
print("Note: All test users have the same default password configured in the system.")