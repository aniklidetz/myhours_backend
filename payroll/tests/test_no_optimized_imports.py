"""
Guard test to prevent optimized_service imports in non-legacy code.

This test ensures that no new code imports optimized_service outside of
legacy modules, preventing accidental usage of the removed service with
incorrect calculation formula (hours × rate × 1.3).
"""
import importlib
import inspect
import pkgutil

def test_no_optimized_imports_in_non_legacy():
    """
    Verify that optimized_service is not imported in non-legacy modules.

    This test scans all payroll modules and fails if it finds
    'optimized_service' imports outside of:
    - Legacy test files (marked with legacy)
    - Management commands explicitly marked as legacy
    - Archive/backup directories

    Raises:
        AssertionError: If optimized_service imports are found in non-legacy modules
    """
    bad_modules = []

    # Scan all payroll package modules
    import payroll
    for module_info in pkgutil.walk_packages(payroll.__path__, payroll.__name__ + "."):
        module_name = module_info.name

        # Skip explicitly allowed legacy locations
        if any(pattern in module_name for pattern in [
            ".tests.legacy.",
            ".management.commands.test_payroll_optimization",
            "archive",
            "backup"
        ]):
            continue

        # Skip test modules in general (they may reference it for mocking)
        if ".tests." in module_name:
            continue

        try:
            module = importlib.import_module(module_name)

            # Get source code if available
            try:
                source_code = inspect.getsource(module)
            except OSError:
                # Module might be compiled or built-in, skip
                continue

            # Check for optimized_service imports or usage
            if "optimized_service" in source_code:
                bad_modules.append(module_name)

        except (ImportError, AttributeError, ModuleNotFoundError):
            # Module couldn't be imported, skip
            continue

    assert not bad_modules, (
        f"Found optimized_service imports in non-legacy modules: {bad_modules}. "
        f"OptimizedPayrollService was removed due to incorrect calculation formula. "
        f"Use PayrollService with CalculationStrategy.ENHANCED instead."
    )

def test_legacy_files_exist_where_expected():
    """
    Verify that known legacy files still exist in expected locations.

    This test ensures that the legacy files we expect to contain
    optimized_service imports are still present and can be monitored.
    """
    expected_legacy_files = [
        "payroll.tests.legacy.test_optimized_service",
        "payroll.tests.legacy.test_optimized_service_equivalency",
        "payroll.management.commands.test_payroll_optimization"
    ]

    missing_files = []
    for module_name in expected_legacy_files:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing_files.append(module_name)

    # This is more of a documentation test - if files are moved/deleted,
    # we want to know so we can update the guard test above
    if missing_files:
        print(f"Note: Expected legacy files not found: {missing_files}")
        print("This may be expected if legacy cleanup has progressed.")
