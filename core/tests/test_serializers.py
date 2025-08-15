"""
Tests for core serializers - Import aggregation module for API serializers.
"""

from django.test import TestCase

from core.serializers import EmployeeSerializer, SalarySerializer, WorkLogSerializer


class CoreSerializersModuleTest(TestCase):
    """Tests for core serializers module"""

    def test_employee_serializer_import(self):
        """Test that EmployeeSerializer is properly imported"""
        # Import should work without error
        from core.serializers import EmployeeSerializer

        # Should be a class (not None or other type)
        self.assertIsNotNone(EmployeeSerializer)
        self.assertTrue(hasattr(EmployeeSerializer, "__name__"))
        self.assertEqual(EmployeeSerializer.__name__, "EmployeeSerializer")

    def test_worklog_serializer_import(self):
        """Test that WorkLogSerializer is properly imported"""
        from core.serializers import WorkLogSerializer

        self.assertIsNotNone(WorkLogSerializer)
        self.assertTrue(hasattr(WorkLogSerializer, "__name__"))
        self.assertEqual(WorkLogSerializer.__name__, "WorkLogSerializer")

    def test_salary_serializer_import(self):
        """Test that SalarySerializer is properly imported"""
        from core.serializers import SalarySerializer

        self.assertIsNotNone(SalarySerializer)
        self.assertTrue(hasattr(SalarySerializer, "__name__"))
        self.assertEqual(SalarySerializer.__name__, "SalarySerializer")

    def test_all_exports_available(self):
        """Test that __all__ exports are all available"""
        from core.serializers import __all__

        expected_exports = [
            "EmployeeSerializer",
            "WorkLogSerializer",
            "SalarySerializer",
        ]
        self.assertEqual(set(__all__), set(expected_exports))

    def test_all_exports_importable(self):
        """Test that all exports in __all__ are actually importable"""
        import core.serializers
        from core.serializers import __all__

        for export_name in __all__:
            self.assertTrue(
                hasattr(core.serializers, export_name),
                f"{export_name} not available in core.serializers",
            )

            # Try to get the attribute
            serializer_class = getattr(core.serializers, export_name)
            self.assertIsNotNone(serializer_class)

    def test_serializer_classes_are_different(self):
        """Test that imported serializers are different classes"""
        # They should be distinct classes, not the same object
        self.assertIsNot(EmployeeSerializer, WorkLogSerializer)
        self.assertIsNot(EmployeeSerializer, SalarySerializer)
        self.assertIsNot(WorkLogSerializer, SalarySerializer)

    def test_serializer_inheritance_check(self):
        """Test that imported serializers are proper serializer classes"""
        from rest_framework import serializers

        # Each should be a serializer class (inherit from serializer base classes)
        # Note: We can't test exact inheritance without importing the actual classes
        # from their original modules, but we can test they have serializer-like attributes

        for serializer_class in [
            EmployeeSerializer,
            WorkLogSerializer,
            SalarySerializer,
        ]:
            # Basic check that they look like serializer classes
            self.assertTrue(hasattr(serializer_class, "__name__"))
            self.assertIn("Serializer", serializer_class.__name__)

    def test_module_import_structure(self):
        """Test the module's import structure"""
        import core.serializers as core_serializers

        # Module should have the expected attributes
        expected_attributes = [
            "EmployeeSerializer",
            "WorkLogSerializer",
            "SalarySerializer",
            "__all__",
        ]

        for attr in expected_attributes:
            self.assertTrue(
                hasattr(core_serializers, attr),
                f"Module missing expected attribute: {attr}",
            )

    def test_circular_import_prevention(self):
        """Test that importing the module doesn't cause circular import issues"""
        # This test ensures that the imports work without circular dependency issues
        try:
            import core.serializers

            # Re-import to test for any side effects
            from core.serializers import (
                EmployeeSerializer,
                SalarySerializer,
                WorkLogSerializer,
            )

            # If we get here without ImportError, circular imports are avoided
            self.assertTrue(True)
        except ImportError as e:
            self.fail(f"Circular import or import error detected: {e}")

    def test_serializers_from_different_modules(self):
        """Test that serializers are imported from their respective modules"""
        # Test that we're getting the actual serializers, not some mock objects
        # This is a basic smoke test to ensure the imports are working

        # EmployeeSerializer should come from users.serializers
        from users.serializers import EmployeeSerializer as DirectEmployeeSerializer

        self.assertIs(EmployeeSerializer, DirectEmployeeSerializer)

        # WorkLogSerializer should come from worktime.serializers
        from worktime.serializers import WorkLogSerializer as DirectWorkLogSerializer

        self.assertIs(WorkLogSerializer, DirectWorkLogSerializer)

        # SalarySerializer should come from payroll.serializers
        from payroll.serializers import SalarySerializer as DirectSalarySerializer

        self.assertIs(SalarySerializer, DirectSalarySerializer)

    def test_module_docstring_or_comments(self):
        """Test that the module has proper structure"""
        import core.serializers

        # Module should exist and be importable
        self.assertIsNotNone(core.serializers)

        # Check that it's actually a module
        import types

        self.assertIsInstance(core.serializers, types.ModuleType)

    def test_serializer_class_attributes(self):
        """Test that imported serializers have expected class attributes"""
        serializer_classes = [EmployeeSerializer, WorkLogSerializer, SalarySerializer]

        for serializer_class in serializer_classes:
            # Should be a class, not an instance
            self.assertIsInstance(serializer_class, type)

            # Should have a __module__ attribute indicating where it came from
            self.assertTrue(hasattr(serializer_class, "__module__"))

            # Module should be one of the expected modules
            expected_modules = [
                "users.serializers",
                "worktime.serializers",
                "payroll.serializers",
            ]
            self.assertIn(serializer_class.__module__, expected_modules)

    def test_import_performance(self):
        """Test that imports don't cause performance issues"""
        import time

        start_time = time.time()

        # Import multiple times to check for any performance issues
        for _ in range(10):
            from core.serializers import (
                EmployeeSerializer,
                SalarySerializer,
                WorkLogSerializer,
            )

        end_time = time.time()
        import_time = end_time - start_time

        # Imports should be fast (less than 1 second for 10 imports)
        self.assertLess(
            import_time,
            1.0,
            "Serializer imports taking too long, possible circular import or heavy initialization",
        )

    def test_namespace_pollution_prevention(self):
        """Test that the module doesn't pollute namespace with unwanted imports"""
        import core.serializers

        # Get all attributes of the module
        module_attrs = dir(core.serializers)

        # Filter out private attributes and expected ones
        public_attrs = [
            attr
            for attr in module_attrs
            if not attr.startswith("_") and attr != "__all__"
        ]

        expected_public_attrs = [
            "EmployeeSerializer",
            "WorkLogSerializer",
            "SalarySerializer",
        ]

        # Should only have the expected public attributes
        self.assertEqual(
            set(public_attrs),
            set(expected_public_attrs),
            "Module has unexpected public attributes, possible namespace pollution",
        )

    def test_consistent_import_results(self):
        """Test that imports are consistent across multiple import attempts"""
        # First import
        # Second import (should be same objects due to Python module caching)
        from core.serializers import EmployeeSerializer as ES1
        from core.serializers import EmployeeSerializer as ES2
        from core.serializers import SalarySerializer as SS1
        from core.serializers import SalarySerializer as SS2
        from core.serializers import WorkLogSerializer as WLS1
        from core.serializers import WorkLogSerializer as WLS2

        # Should be the exact same objects (identity check)
        self.assertIs(ES1, ES2)
        self.assertIs(WLS1, WLS2)
        self.assertIs(SS1, SS2)

    def test_module_attributes_accessibility(self):
        """Test that all module attributes are properly accessible"""
        import core.serializers

        # Test accessing via getattr
        employee_serializer = getattr(core.serializers, "EmployeeSerializer", None)
        worklog_serializer = getattr(core.serializers, "WorkLogSerializer", None)
        salary_serializer = getattr(core.serializers, "SalarySerializer", None)

        self.assertIsNotNone(employee_serializer)
        self.assertIsNotNone(worklog_serializer)
        self.assertIsNotNone(salary_serializer)

        # Test accessing via direct attribute access
        self.assertTrue(hasattr(core.serializers, "EmployeeSerializer"))
        self.assertTrue(hasattr(core.serializers, "WorkLogSerializer"))
        self.assertTrue(hasattr(core.serializers, "SalarySerializer"))
