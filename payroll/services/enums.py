"""
Enumerations for payroll calculation system.

This module defines all enums used across the payroll calculation system,
ensuring type safety and preventing magic string errors.
"""

from enum import Enum


class CalculationMode(Enum):
    """Calculation modes for different employee types"""
    
    HOURLY = "hourly"
    """Full daily pay calculation for hourly employees"""
    
    MONTHLY = "monthly"
    """Base salary + bonuses for monthly employees"""
    
    def __str__(self):
        return self.value


class CalculationStrategy(Enum):
    """
    Available payroll calculation strategies.
    
    Each strategy represents a different approach to calculating payroll,
    with different performance characteristics and feature sets.
    """
    
    ENHANCED = "enhanced"  
    """Enhanced calculation with detailed breakdowns and all features"""
    
    LEGACY = "legacy"
    """Legacy calculation strategy for backward compatibility"""
    
    @classmethod
    def get_default(cls) -> "CalculationStrategy":
        """Get the default calculation strategy"""
        return cls.ENHANCED
        
    @classmethod 
    def get_fallback(cls) -> "CalculationStrategy":
        """Get the fallback strategy when others fail"""
        return cls.ENHANCED
        
    def __str__(self):
        return self.value
        
    @property
    def display_name(self) -> str:
        """Human-readable display name"""
        return {
            self.ENHANCED: "Enhanced Calculation", 
            self.LEGACY: "Legacy Calculation"
        }[self]
        
    @property
    def description(self) -> str:
        """Description of the strategy"""
        return {
            self.ENHANCED: "Full-featured calculation with detailed breakdowns",
            self.LEGACY: "Backward-compatible calculation for fallback scenarios"
        }[self]

    @classmethod
    def from_string(cls, value: str) -> "CalculationStrategy":
        """
        Parse strategy from string with backwards compatibility.
        
        Args:
            value: Strategy name (case-insensitive)
            
        Returns:
            CalculationStrategy: Parsed strategy
            
        Note:
            'optimized' maps to ENHANCED for backwards compatibility
        """
        if not value:
            return cls.get_default()
            
        # Handle deprecated 'optimized' → 'enhanced'
        if value.lower() == "optimized":
            return cls.ENHANCED
            
        # Try normal parsing
        try:
            return cls(value.lower())
        except ValueError:
            return cls.get_default()


class EmployeeType(Enum):
    """Employee calculation types"""
    
    HOURLY = "hourly"
    """Hourly employee with overtime calculations"""
    
    MONTHLY = "monthly" 
    """Monthly salaried employee"""
    
    def __str__(self):
        return self.value



class CacheSource(Enum):
    """Sources of cached payroll data"""
    
    MONTHLY_SUMMARY = "monthly_summary"
    """Data from MonthlyPayrollSummary model"""
    
    DAILY_CALCULATIONS = "daily_calculations"
    """Data from DailyPayrollCalculation model"""
    
    REDIS = "redis"
    """Data from Redis cache"""
    
    NONE = "none"
    """No cache used"""
    
    def __str__(self):
        return self.value


class PayrollComponent(Enum):
    """Components of payroll calculations"""
    
    BASE_SALARY = "base_salary"
    REGULAR_HOURS = "regular_hours"
    OVERTIME_125 = "overtime_125"
    OVERTIME_150 = "overtime_150"
    HOLIDAY_PAY = "holiday_pay"
    SABBATH_PAY = "sabbath_pay"
    NIGHT_DIFFERENTIAL = "night_differential"
    BONUS = "bonus"
    
    def __str__(self):
        return self.value


class PayrollStatus(Enum):
    """Status of payroll calculation"""
    
    SUCCESS = "success"
    """Calculation completed successfully"""
    
    PARTIAL = "partial" 
    """Calculation completed with some missing data"""
    
    FAILED = "failed"
    """Calculation failed"""
    
    CACHED = "cached"
    """Result served from cache"""
    
    def __str__(self):
        return self.value