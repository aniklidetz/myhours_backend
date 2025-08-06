# tests/base.py
import uuid
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase, APIClient
from rest_framework.authtoken.models import Token
from users.models import Employee
from django.utils import timezone


class BaseTestCase(TestCase):
    """Base test case with common setup"""

    def setUp(self):
        """Set up test data"""
        # Generate unique identifiers for this test
        self.test_id = str(uuid.uuid4())[:8]

        # Create test user with unique username and email
        self.user = User.objects.create_user(
            username=f"testuser_{self.test_id}",
            email=f"test_{self.test_id}@example.com",
            password="testpass123",
        )

        # Create test employee linked to user with unique email
        self.employee = Employee.objects.create(
            user=self.user,  # Link employee to user
            first_name="John",
            last_name="Doe",
            email=f"test_{self.test_id}@example.com",  # Same email as user but unique
            phone="+972501234567",
            employment_type="hourly",
        )


class BaseAPITestCase(APITestCase):
    """Base API test case with authentication setup"""

    def setUp(self):
        """Set up test data and authentication"""
        # Generate unique identifiers for this test
        self.test_id = str(uuid.uuid4())[:8]

        # Create test user with unique username and email
        self.user = User.objects.create_user(
            username=f"testuser_{self.test_id}",
            email=f"test_{self.test_id}@example.com",
            password="testpass123",
        )

        # Create authentication token
        self.token = Token.objects.create(user=self.user)

        # Set up authenticated client
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        # Create test employee linked to user with unique email
        self.employee = Employee.objects.create(
            user=self.user,  # Link employee to user
            first_name="John",
            last_name="Doe",
            email=f"test_{self.test_id}@example.com",  # Same email as user but unique
            phone="+972501234567",
            employment_type="hourly",
        )

        # Create second test employee for multiple employee tests with unique email
        self.employee2 = Employee.objects.create(
            first_name="Jane",
            last_name="Smith",
            email=f"jane.smith_{self.test_id}@example.com",  # Unique email
            phone="+972507654321",
            employment_type="monthly",
        )

    def create_authenticated_user(self, username="testuser2"):
        """Create additional authenticated user for tests"""
        # Generate unique suffix to prevent conflicts
        unique_suffix = str(uuid.uuid4())[:6]
        unique_username = f"{username}_{unique_suffix}"

        user = User.objects.create_user(
            username=unique_username,
            email=f"{unique_username}@example.com",
            password="testpass123",
        )
        token = Token.objects.create(user=user)
        return user, token

    def get_authenticated_client(self, token=None):
        """Get authenticated API client"""
        if token is None:
            token = self.token

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        return client


class UnauthenticatedAPITestCase(APITestCase):
    """Base API test case without authentication for testing unauthorized access"""

    def setUp(self):
        """Set up test data without authentication"""
        # Generate unique identifiers for this test
        self.test_id = str(uuid.uuid4())[:8]

        # Create test user (but don't authenticate) with unique username and email
        self.user = User.objects.create_user(
            username=f"testuser_{self.test_id}",
            email=f"test_{self.test_id}@example.com",
            password="testpass123",
        )

        # Create test employee linked to user with unique email
        self.employee = Employee.objects.create(
            user=self.user,  # Link employee to user
            first_name="John",
            last_name="Doe",
            email=f"test_{self.test_id}@example.com",  # Same email as user but unique
            phone="+972501234567",
            employment_type="hourly",
        )

        # Use unauthenticated client
        self.client = APIClient()
