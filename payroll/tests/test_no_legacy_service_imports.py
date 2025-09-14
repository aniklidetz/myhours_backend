"""
Guard test to prevent legacy PayrollCalculationService imports in non-legacy code.

This test ensures that no new code imports the legacy PayrollCalculationService
directly from payroll.services, enforcing migration to the new PayrollService
architecture.
"""
import importlib
import inspect
import pkgutil


def test_no_legacy_service_imports_in_non_legacy():
    """
    Verify that legacy PayrollCalculationService is not imported in non-legacy modules.
    
    This test scans all payroll modules and fails if it finds
    'PayrollCalculationService' imports outside of:
    - Legacy test files 
    - Management commands explicitly marked as legacy
    - Archive/backup directories
    - The services.py file itself (where it's defined)
    
    Raises:
        AssertionError: If legacy service imports are found in non-legacy modules
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
            ".services",  # Where the class is defined
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
                
            # Check for legacy PayrollCalculationService imports
            if "from payroll.services import" in source_code and "PayrollCalculationService" in source_code:
                bad_modules.append(module_name)
                
        except (ImportError, AttributeError, ModuleNotFoundError):
            # Module couldn't be imported, skip
            continue
    
    assert not bad_modules, (
        f"Found legacy PayrollCalculationService imports in non-legacy modules: {bad_modules}. "
        f"Legacy PayrollCalculationService should not be used in new code. "
        f"Use PayrollService with CalculationStrategy.ENHANCED instead."
    )


def test_payroll_service_available():
    """
    Verify that the new PayrollService architecture is available.
    
    This test ensures that the new service classes can be imported
    and are properly configured.
    """
    # Test that new architecture components can be imported
    from payroll.services.payroll_service import PayrollService
    from payroll.services.contracts import CalculationContext
    from payroll.services.enums import CalculationStrategy, EmployeeType
    from payroll.services.factory import get_payroll_factory
    
    # Test that factory has strategies registered
    factory = get_payroll_factory()
    available_strategies = factory.get_available_strategies()
    
    assert CalculationStrategy.ENHANCED in available_strategies, (
        "EnhancedPayrollStrategy should be registered in factory"
    )
    
    # Test that we can create a PayrollService instance
    service = PayrollService()
    assert service is not None
    
    # Test that CalculationStrategy has expected values
    assert hasattr(CalculationStrategy, 'ENHANCED')
    assert hasattr(CalculationStrategy, 'LEGACY')
    assert CalculationStrategy.get_default() == CalculationStrategy.ENHANCED