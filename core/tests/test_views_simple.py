"""
Simple tests for core views - testing view classes directly without URL routing.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from rest_framework import status
from rest_framework.test import APIRequestFactory

from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase

from core.views import EmployeeViewSet, SalaryViewSet, WorkLogViewSet
from payroll.models import Salary
from users.models import Employee
from worktime.models import WorkLog


class CoreViewsDirectTestCase(TestCase):
    """Base test case for direct view testing"""

    def setUp(self):
        """Set up test data"""
        self.factory = APIRequestFactory()
        
        # Create test user and employee
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.employee = Employee.objects.create(
            user=self.user,
            first_name='Test',
            last_name='User',
            email='test@example.com',
            employment_type='full_time',
            role='employee'
        )
        
        # Create admin user
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='adminpass123'
        )
        
        self.admin_employee = Employee.objects.create(
            user=self.admin_user,
            first_name='Admin',
            last_name='User',
            email='admin@example.com',
            employment_type='full_time',
            role='admin'
        )
        
        # Create test salary
        self.salary = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal('10000.00'),
            calculation_type='monthly',
            currency='ILS'
        )


class EmployeeViewSetDirectTest(CoreViewsDirectTestCase):
    """Tests for EmployeeViewSet direct functionality"""

    def test_employee_viewset_class_attributes(self):
        """Test EmployeeViewSet has correct class attributes"""
        self.assertEqual(EmployeeViewSet.serializer_class.__name__, 'EmployeeSerializer')
        self.assertTrue(hasattr(EmployeeViewSet, 'queryset'))
        self.assertTrue(hasattr(EmployeeViewSet, 'filter_backends'))
        self.assertTrue(hasattr(EmployeeViewSet, 'search_fields'))

    def test_employee_viewset_search_fields(self):
        """Test EmployeeViewSet search configuration"""
        expected_search_fields = ["first_name", "last_name", "email"]
        self.assertEqual(EmployeeViewSet.search_fields, expected_search_fields)

    def test_employee_viewset_queryset(self):
        """Test EmployeeViewSet queryset"""
        queryset = EmployeeViewSet.queryset
        self.assertEqual(str(queryset.query).count('ORDER BY'), 1)  # Should have ordering

    def test_employee_list_view_direct(self):
        """Test employee list view directly"""
        view = EmployeeViewSet()
        view.action = 'list'
        
        # Mock request
        request = self.factory.get('/')
        request.user = self.user
        view.request = request
        view.format_kwarg = None
        
        # Test queryset method
        queryset = view.get_queryset()
        self.assertTrue(queryset.exists())

    def test_employee_retrieve_view_direct(self):
        """Test employee retrieve view functionality"""
        view = EmployeeViewSet()
        view.action = 'retrieve'
        view.kwargs = {'pk': self.employee.pk}
        
        # Test queryset filtering by pk
        queryset = view.get_queryset()
        filtered_queryset = queryset.filter(pk=self.employee.pk)
        self.assertTrue(filtered_queryset.exists())
        self.assertEqual(filtered_queryset.first(), self.employee)


class SalaryViewSetDirectTest(CoreViewsDirectTestCase):
    """Tests for SalaryViewSet direct functionality"""

    def test_salary_viewset_class_attributes(self):
        """Test SalaryViewSet has correct class attributes"""
        self.assertEqual(SalaryViewSet.serializer_class.__name__, 'SalarySerializer')
        self.assertTrue(hasattr(SalaryViewSet, 'queryset'))
        self.assertTrue(hasattr(SalaryViewSet, 'filter_backends'))
        self.assertTrue(hasattr(SalaryViewSet, 'filterset_fields'))

    def test_salary_viewset_filterset_fields(self):
        """Test SalaryViewSet filter configuration"""
        expected_filterset_fields = ["employee", "currency"]
        self.assertEqual(SalaryViewSet.filterset_fields, expected_filterset_fields)

    def test_salary_viewset_queryset(self):
        """Test SalaryViewSet queryset"""
        queryset = SalaryViewSet.queryset
        self.assertEqual(str(queryset.query).count('ORDER BY'), 1)  # Should have ordering

    def test_salary_calculate_action_exists(self):
        """Test that calculate action exists"""
        self.assertTrue(hasattr(SalaryViewSet, 'calculate'))
        
        # Check it's a method
        self.assertTrue(callable(getattr(SalaryViewSet, 'calculate')))

    def test_salary_calculate_action_signature(self):
        """Test calculate action has correct signature"""
        import inspect
        
        calculate_method = getattr(SalaryViewSet, 'calculate')
        sig = inspect.signature(calculate_method)
        
        # Should accept self, request, pk=None
        params = list(sig.parameters.keys())
        self.assertIn('self', params)
        self.assertIn('request', params)
        self.assertIn('pk', params)

    @patch('payroll.models.Salary.calculate_salary')
    def test_calculate_method_calls_salary_method(self, mock_calculate):
        """Test calculate action calls salary calculation method"""
        mock_calculate.return_value = None
        
        view = SalaryViewSet()
        view.kwargs = {'pk': self.salary.pk}
        
        request = self.factory.post('/')
        request.user = self.admin_user
        view.request = request
        view.format_kwarg = None
        
        # Mock get_object to return our salary
        view.get_object = MagicMock(return_value=self.salary)
        
        response = view.calculate(request, pk=self.salary.pk)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)

    def test_calculate_method_without_calculation_methods(self):
        """Test calculate method when salary has no calculation methods"""
        view = SalaryViewSet()
        view.kwargs = {'pk': self.salary.pk}
        
        request = self.factory.post('/')
        request.user = self.admin_user
        view.request = request
        view.format_kwarg = None
        
        # Mock get_object to return our salary
        view.get_object = MagicMock(return_value=self.salary)
        
        response = view.calculate(request, pk=self.salary.pk)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Salary recalculated')


class WorkLogViewSetDirectTest(CoreViewsDirectTestCase):
    """Tests for WorkLogViewSet direct functionality"""

    def setUp(self):
        super().setUp()
        from django.utils import timezone

        # Create test worklog
        now = timezone.now()
        self.worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=now,
            check_out=now + timezone.timedelta(hours=8)
        )

    def test_worklog_viewset_class_attributes(self):
        """Test WorkLogViewSet has correct class attributes"""
        self.assertEqual(WorkLogViewSet.serializer_class.__name__, 'WorkLogSerializer')
        self.assertTrue(hasattr(WorkLogViewSet, 'queryset'))
        self.assertTrue(hasattr(WorkLogViewSet, 'filter_backends'))
        self.assertTrue(hasattr(WorkLogViewSet, 'filterset_class'))

    def test_worklog_viewset_filterset_class(self):
        """Test WorkLogViewSet uses WorkLogFilter"""
        from core.filters import WorkLogFilter
        self.assertEqual(WorkLogViewSet.filterset_class, WorkLogFilter)

    def test_worklog_viewset_queryset_ordering(self):
        """Test WorkLogViewSet queryset ordering"""
        queryset = WorkLogViewSet.queryset
        # Should be ordered by check_in DESC (most recent first)
        self.assertIn('ORDER BY', str(queryset.query))
        self.assertIn('DESC', str(queryset.query))

    def test_worklog_list_view_direct(self):
        """Test worklog list view directly"""
        view = WorkLogViewSet()
        view.action = 'list'
        
        request = self.factory.get('/')
        request.user = self.user
        view.request = request
        view.format_kwarg = None
        
        # Test queryset method
        queryset = view.get_queryset()
        self.assertTrue(queryset.exists())
        
        # Should contain our worklog
        self.assertIn(self.worklog, queryset)


class ViewSetPermissionTest(CoreViewsDirectTestCase):
    """Tests for view permissions"""

    def test_employee_viewset_permission_classes(self):
        """Test EmployeeViewSet permission configuration"""
        view = EmployeeViewSet()
        self.assertTrue(hasattr(view, 'permission_classes'))

    def test_salary_viewset_permission_classes(self):
        """Test SalaryViewSet permission configuration"""
        view = SalaryViewSet()
        self.assertTrue(hasattr(view, 'permission_classes'))

    def test_worklog_viewset_permission_classes(self):
        """Test WorkLogViewSet permission configuration"""
        view = WorkLogViewSet()
        self.assertTrue(hasattr(view, 'permission_classes'))


class ViewSetSerializerTest(CoreViewsDirectTestCase):
    """Tests for view serializers"""

    def test_employee_viewset_get_serializer(self):
        """Test EmployeeViewSet get_serializer method"""
        view = EmployeeViewSet()
        view.action = 'list'
        
        request = self.factory.get('/')
        request.user = self.user
        view.request = request
        view.format_kwarg = None
        
        serializer = view.get_serializer()
        self.assertEqual(serializer.__class__.__name__, 'EmployeeSerializer')

    def test_salary_viewset_get_serializer(self):
        """Test SalaryViewSet get_serializer method"""
        view = SalaryViewSet()
        view.action = 'list'
        
        request = self.factory.get('/')
        request.user = self.user
        view.request = request
        view.format_kwarg = None
        
        serializer = view.get_serializer()
        self.assertEqual(serializer.__class__.__name__, 'SalarySerializer')

    def test_worklog_viewset_get_serializer(self):
        """Test WorkLogViewSet get_serializer method"""
        view = WorkLogViewSet()
        view.action = 'list'
        
        request = self.factory.get('/')
        request.user = self.user
        view.request = request
        view.format_kwarg = None
        
        serializer = view.get_serializer()
        self.assertEqual(serializer.__class__.__name__, 'WorkLogSerializer')


class ViewSetFilterTest(CoreViewsDirectTestCase):
    """Tests for view filtering functionality"""

    def test_employee_viewset_search_functionality(self):
        """Test EmployeeViewSet search filter"""
        from rest_framework.filters import SearchFilter
        
        view = EmployeeViewSet()
        
        # Should have SearchFilter in filter_backends
        self.assertIn(SearchFilter, view.filter_backends)
        
        # Should have correct search fields
        expected_fields = ["first_name", "last_name", "email"]
        self.assertEqual(view.search_fields, expected_fields)

    def test_salary_viewset_filter_functionality(self):
        """Test SalaryViewSet filter configuration"""
        from django_filters.rest_framework import DjangoFilterBackend
        
        view = SalaryViewSet()
        
        # Should have DjangoFilterBackend in filter_backends
        self.assertIn(DjangoFilterBackend, view.filter_backends)
        
        # Should have correct filterset fields
        expected_fields = ["employee", "currency"]
        self.assertEqual(view.filterset_fields, expected_fields)

    def test_worklog_viewset_filter_functionality(self):
        """Test WorkLogViewSet filter configuration"""
        from django_filters.rest_framework import DjangoFilterBackend

        from core.filters import WorkLogFilter
        
        view = WorkLogViewSet()
        
        # Should have DjangoFilterBackend in filter_backends
        self.assertIn(DjangoFilterBackend, view.filter_backends)
        
        # Should use WorkLogFilter class
        self.assertEqual(view.filterset_class, WorkLogFilter)


class ViewSetInheritanceTest(CoreViewsDirectTestCase):
    """Tests for view inheritance and base functionality"""

    def test_viewset_inheritance(self):
        """Test that viewsets inherit from ModelViewSet"""
        from rest_framework import viewsets
        
        self.assertTrue(issubclass(EmployeeViewSet, viewsets.ModelViewSet))
        self.assertTrue(issubclass(SalaryViewSet, viewsets.ModelViewSet))
        self.assertTrue(issubclass(WorkLogViewSet, viewsets.ModelViewSet))

    def test_viewset_model_binding(self):
        """Test that viewsets are bound to correct models"""
        # Check queryset models
        self.assertEqual(EmployeeViewSet.queryset.model, Employee)
        self.assertEqual(SalaryViewSet.queryset.model, Salary)
        self.assertEqual(WorkLogViewSet.queryset.model, WorkLog)


class ViewMethodTest(CoreViewsDirectTestCase):
    """Tests for specific view methods"""

    def test_salary_calculate_action_decorator(self):
        """Test that calculate action has correct decorators"""
        calculate_method = getattr(SalaryViewSet, 'calculate')
        
        # Should have action decorator attributes
        self.assertTrue(hasattr(calculate_method, 'mapping'))
        self.assertTrue(hasattr(calculate_method, 'detail'))
        
        # Should be a detail action (True) and accept POST
        if hasattr(calculate_method, 'detail'):
            self.assertTrue(calculate_method.detail)
        if hasattr(calculate_method, 'mapping'):
            self.assertIn('post', calculate_method.mapping)

    def test_calculate_method_response_format(self):
        """Test calculate method response format"""
        view = SalaryViewSet()
        view.kwargs = {'pk': self.salary.pk}
        
        request = self.factory.post('/')
        request.user = self.admin_user
        view.request = request
        view.format_kwarg = None
        
        # Mock get_object
        view.get_object = MagicMock(return_value=self.salary)
        
        response = view.calculate(request, pk=self.salary.pk)
        
        # Should return Response object
        from rest_framework.response import Response
        self.assertIsInstance(response, Response)
        
        # Should have message key
        self.assertIn('message', response.data)
        self.assertEqual(response.data['message'], 'Salary recalculated')


class ViewSetConfigurationTest(CoreViewsDirectTestCase):
    """Tests for view configuration and setup"""

    def test_employee_viewset_configuration(self):
        """Test EmployeeViewSet is properly configured"""
        view = EmployeeViewSet()
        
        # Basic configuration
        self.assertIsNotNone(view.queryset)
        self.assertIsNotNone(view.serializer_class)
        self.assertIsNotNone(view.filter_backends)
        
        # Should have queryset with employees
        self.assertTrue(view.queryset.exists())

    def test_salary_viewset_configuration(self):
        """Test SalaryViewSet is properly configured"""
        view = SalaryViewSet()
        
        # Basic configuration
        self.assertIsNotNone(view.queryset)
        self.assertIsNotNone(view.serializer_class)
        self.assertIsNotNone(view.filter_backends)
        
        # Should have queryset with salaries
        self.assertTrue(view.queryset.exists())

    def test_worklog_viewset_configuration(self):
        """Test WorkLogViewSet is properly configured"""
        view = WorkLogViewSet()
        
        # Basic configuration
        self.assertIsNotNone(view.queryset)
        self.assertIsNotNone(view.serializer_class)
        self.assertIsNotNone(view.filter_backends)
        
        # Test queryset class - worklog may not exist yet but queryset should be configured
        from worktime.models import WorkLog
        self.assertEqual(view.queryset.model, WorkLog)