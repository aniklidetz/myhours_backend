"""
Data contracts for payroll calculations.

This module defines standardized data structures that all payroll calculation 
strategies must adhere to, ensuring consistency and type safety across the system.
"""

from typing import TypedDict, Optional, Any, Dict
from decimal import Decimal
import decimal


class PayrollBreakdown(TypedDict, total=False):
    """Detailed breakdown of payroll calculations"""
    # Regular time
    regular_hours: float
    regular_rate: float
    regular_pay: float
    
    # Overtime (125%)
    overtime_125_hours: float
    overtime_125_rate: float
    overtime_125_pay: float
    
    # Overtime (150%) 
    overtime_150_hours: float
    overtime_150_rate: float
    overtime_150_pay: float
    
    # Holiday work
    holiday_hours: float
    holiday_rate: float
    holiday_pay: float
    
    # Sabbath work
    sabbath_hours: float
    sabbath_rate: float
    sabbath_pay: float
    
    # Extended Sabbath breakdown
    sabbath_regular_hours: float
    sabbath_regular_pay: float
    sabbath_overtime_175_hours: float
    sabbath_overtime_175_pay: float
    sabbath_overtime_200_hours: float
    sabbath_overtime_200_pay: float
    
    # Night shift differentials
    night_shift_hours: float
    night_shift_rate: float
    night_shift_pay: float
    
    # Monthly salary specifics
    base_monthly_salary: float
    worked_days: int
    total_working_days: int
    work_proportion: float


class PayrollMetadata(TypedDict, total=False):
    """Additional metadata about the calculation"""
    calculation_strategy: str
    calculation_date: str
    employee_type: str  # 'hourly' or 'monthly'
    currency: str
    has_cache: bool
    cache_source: Optional[str]
    performance_stats: Dict[str, Any]
    warnings: list[str]
    
    
class PayrollResult(TypedDict):
    """
    Standardized payroll calculation result contract.
    
    All payroll strategies must return data conforming to this structure.
    This ensures consistency across legacy, enhanced, and optimized calculations.
    """
    # Core financial data (required)
    total_salary: Decimal
    total_hours: Decimal
    
    # Time breakdown (required)
    regular_hours: Decimal
    overtime_hours: Decimal
    holiday_hours: Decimal
    shabbat_hours: Decimal
    
    # Detailed breakdown (required)
    breakdown: PayrollBreakdown
    
    # Additional metadata (required)
    metadata: PayrollMetadata


class CalculationContext(TypedDict):
    """
    Context information needed for payroll calculations.
    
    This provides all necessary data to perform calculations without 
    coupling strategies to Django request objects.
    """
    # Employee information (required)
    employee_id: int
    
    # Time period (required)
    year: int
    month: int
    
    # Request context (required)
    user_id: int  # Who is requesting the calculation
    
    # Calculation hints (optional)
    strategy_hint: Optional[str]
    force_recalculate: bool
    fast_mode: bool
    
    # Additional context (optional, with defaults)
    include_breakdown: bool
    include_daily_details: bool


class ShabbatTimes(TypedDict):
    """
    Unified Shabbat times contract for all payroll services.

    This contract standardizes Shabbat time data across the entire payroll system,
    replacing the inconsistent formats from SunriseSunsetService ("start"/"end")
    and EnhancedSunriseSunsetService ("shabbat_start"/"shabbat_end").

    All times are in ISO 8601 format and Israeli timezone (Asia/Jerusalem).
    """
    # Core Shabbat times (required)
    shabbat_start: str          # ISO datetime - Shabbat begins (18 min before Friday sunset)
    shabbat_end: str            # ISO datetime - Shabbat ends (42 min after Saturday sunset)

    # Reference sunset times (required)
    friday_sunset: str          # ISO datetime - Actual sunset time on Friday
    saturday_sunset: str        # ISO datetime - Actual sunset time on Saturday

    # Metadata (required)
    timezone: str               # Always "Asia/Jerusalem" for Israeli labor law compliance
    is_estimated: bool          # True if fallback/approximate times were used
    calculation_method: str     # "api_precise" | "api_estimated" | "fallback"

    # Location context (required)
    coordinates: Dict[str, float]  # {"lat": 31.7683, "lng": 35.2137} - Jerusalem default

    # Additional context (optional)
    friday_date: str            # ISO date - The Friday date used for calculation
    saturday_date: str          # ISO date - The Saturday date


class ValidationError(Exception):
    """Raised when payroll result doesn't conform to contract"""
    pass


def validate_shabbat_times(result: dict) -> ShabbatTimes:
    """
    Validate that a result dictionary conforms to ShabbatTimes contract.

    Args:
        result: Dictionary to validate (from any Shabbat service)

    Returns:
        ShabbatTimes: Validated and typed result

    Raises:
        ValidationError: If result doesn't conform to contract
    """
    required_fields = [
        'shabbat_start', 'shabbat_end', 'friday_sunset', 'saturday_sunset',
        'timezone', 'is_estimated', 'calculation_method', 'coordinates'
    ]

    missing_fields = [field for field in required_fields if field not in result]
    if missing_fields:
        raise ValidationError(f"Missing required ShabbatTimes fields: {missing_fields}")

    # Validate timezone is Israeli
    if result.get('timezone') != 'Asia/Jerusalem':
        raise ValidationError(f"Invalid timezone: {result.get('timezone')}. Must be 'Asia/Jerusalem'")

    # Validate calculation method
    valid_methods = ['api_precise', 'api_estimated', 'fallback']
    if result.get('calculation_method') not in valid_methods:
        raise ValidationError(f"Invalid calculation_method: {result.get('calculation_method')}. Must be one of {valid_methods}")

    # Validate coordinates structure
    coords = result.get('coordinates', {})
    if not isinstance(coords, dict) or 'lat' not in coords or 'lng' not in coords:
        raise ValidationError("coordinates must be dict with 'lat' and 'lng' keys")

    return result  # type: ignore


def validate_payroll_result(result: dict) -> PayrollResult:
    """
    Validate that a result dictionary conforms to PayrollResult contract.
    
    Args:
        result: Dictionary to validate
        
    Returns:
        PayrollResult: Validated and typed result
        
    Raises:
        ValidationError: If result doesn't conform to contract
    """
    required_fields = [
        'total_salary', 'total_hours', 'regular_hours', 'overtime_hours',
        'holiday_hours', 'shabbat_hours', 'breakdown', 'metadata'
    ]
    
    missing_fields = [field for field in required_fields if field not in result]
    if missing_fields:
        raise ValidationError(f"Missing required fields: {missing_fields}")
    
    # Validate types
    try:
        # Convert to Decimal if needed
        for field in ['total_salary', 'total_hours', 'regular_hours', 'overtime_hours', 
                     'holiday_hours', 'shabbat_hours']:
            if not isinstance(result[field], Decimal):
                try:
                    result[field] = Decimal(str(result[field]))
                except (ValueError, TypeError, decimal.InvalidOperation) as e:
                    raise ValidationError(f"Cannot convert {field} to Decimal: {result[field]} - {e}")
                
        # Validate breakdown and metadata are dicts
        if not isinstance(result['breakdown'], dict):
            raise ValidationError("breakdown must be a dictionary")
            
        if not isinstance(result['metadata'], dict):
            raise ValidationError("metadata must be a dictionary")
            
    except ValidationError:
        raise  # Re-raise our custom ValidationErrors
    except (ValueError, TypeError) as e:
        raise ValidationError(f"Type validation error: {e}")
    
    return result  # type: ignore


def create_empty_breakdown() -> dict:
    """
    Create an empty breakdown dict with all fields initialized to Decimal zero.
    Includes all fields that tests and ShiftSplitter expect to prevent KeyError.
    
    Returns:
        dict: Empty breakdown with all fields set to Decimal("0")
    """
    return {
        # Basic time categories
        "base_regular_hours": Decimal("0"),
        "base_regular_pay": Decimal("0"),
        "regular_hours": Decimal("0"),
        "regular_rate": Decimal("0"),
        "regular_pay": Decimal("0"),
        
        # Overtime tiers
        "overtime_125_hours": Decimal("0"),
        "overtime_125_rate": Decimal("0"),
        "overtime_125_pay": Decimal("0"),
        "overtime_150_hours": Decimal("0"),
        "overtime_150_rate": Decimal("0"),
        "overtime_150_pay": Decimal("0"),
        
        # Holiday work
        "holiday_hours": Decimal("0"),
        "holiday_rate": Decimal("0"),
        "holiday_pay": Decimal("0"),
        
        # Sabbath work (legacy compatibility)
        "sabbath_hours": Decimal("0"),
        "sabbath_rate": Decimal("0"),
        "sabbath_pay": Decimal("0"),
        
        # Extended Sabbath breakdown
        "sabbath_regular_hours": Decimal("0"),
        "sabbath_regular_pay": Decimal("0"),
        "sabbath_overtime_175_hours": Decimal("0"),
        "sabbath_overtime_175_pay": Decimal("0"),
        "sabbath_overtime_200_hours": Decimal("0"),
        "sabbath_overtime_200_pay": Decimal("0"),
        
        # Night shift differentials (diagnostic)
        "night_shift_hours": Decimal("0"),
        "night_shift_rate": Decimal("0"),
        "night_shift_pay": Decimal("0"),
        
        # ShiftSplitter compatibility fields
        "overtime_before_sabbath_1": Decimal("0"),
        "overtime_before_sabbath_2": Decimal("0"),
        
        # Monthly salary specifics
        "base_monthly_salary": Decimal("0"),
        "worked_days": 0,
        "total_working_days": 0,
        "work_proportion": Decimal("0"),
        "proportional_base": Decimal("0"),
        "total_bonuses": Decimal("0"),
        "total_bonuses_monthly": Decimal("0"),
        
        # Legacy aliases for compatibility
        "sabbath_regular": Decimal("0"),  # alias for sabbath_regular_hours
        "night_hours": Decimal("0"),      # alias for night_shift_hours
        "overtime_pay": Decimal("0"),     # total overtime pay
    }


def create_fallback_shabbat_times(
    friday_date: str,
    calculation_method: str = "fallback",
    coordinates: Optional[Dict[str, float]] = None
) -> ShabbatTimes:
    """
    Create fallback Shabbat times for error cases.

    Uses approximate Israeli sunset times based on season when API fails.

    Args:
        friday_date: ISO date string for Friday
        calculation_method: Method that was attempted
        coordinates: Location coordinates

    Returns:
        ShabbatTimes: Fallback result with seasonal approximation
    """
    from datetime import datetime, timedelta

    if coordinates is None:
        coordinates = {"lat": 31.7683, "lng": 35.2137}  # Jerusalem default

    # Parse date and calculate Saturday
    friday = datetime.fromisoformat(friday_date).date()
    saturday = friday + timedelta(days=1)

    # Seasonal sunset approximation for Israel
    month = friday.month
    if month in [6, 7, 8]:  # Summer
        sunset_hour, sunset_minute = 19, 30
    elif month in [12, 1, 2]:  # Winter
        sunset_hour, sunset_minute = 16, 45
    elif month in [3, 4, 5]:  # Spring
        sunset_hour, sunset_minute = 18, 15
    else:  # Fall (9, 10, 11)
        sunset_hour, sunset_minute = 17, 30

    # Create approximate times in Israeli timezone
    friday_sunset = f"{friday.isoformat()}T{sunset_hour:02d}:{sunset_minute:02d}:00+02:00"
    saturday_sunset = f"{saturday.isoformat()}T{sunset_hour:02d}:{sunset_minute+1:02d}:00+02:00"

    # Calculate Shabbat times (18 min before / 42 min after)
    friday_dt = datetime.fromisoformat(friday_sunset.replace('+02:00', ''))
    saturday_dt = datetime.fromisoformat(saturday_sunset.replace('+02:00', ''))

    shabbat_start = friday_dt - timedelta(minutes=18)
    shabbat_end = saturday_dt + timedelta(minutes=42)

    return ShabbatTimes(
        shabbat_start=f"{shabbat_start.isoformat()}+02:00",
        shabbat_end=f"{shabbat_end.isoformat()}+02:00",
        friday_sunset=friday_sunset,
        saturday_sunset=saturday_sunset,
        timezone="Asia/Jerusalem",
        is_estimated=True,
        calculation_method="fallback",
        coordinates=coordinates,
        friday_date=friday_date,
        saturday_date=saturday.isoformat()
    )


def create_empty_payroll_result(
    employee_id: int,
    strategy: str = "unknown",
    currency: str = "ILS"
) -> PayrollResult:
    """
    Create an empty/zero payroll result for error cases.
    
    Args:
        employee_id: Employee ID
        strategy: Strategy name that created this result
        currency: Currency code
        
    Returns:
        PayrollResult: Empty result with zero values
    """
    return PayrollResult(
        total_salary=Decimal('0'),
        total_hours=Decimal('0'),
        regular_hours=Decimal('0'),
        overtime_hours=Decimal('0'),
        holiday_hours=Decimal('0'),
        shabbat_hours=Decimal('0'),
        breakdown=create_empty_breakdown(),
        metadata=PayrollMetadata(
            calculation_strategy=strategy,
            employee_type='unknown',
            currency=currency,
            has_cache=False,
            warnings=['No calculation data available']
        )
    )