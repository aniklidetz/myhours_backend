"""
Enhanced serializers for detailed payroll information display
"""

from rest_framework import serializers
from decimal import Decimal
from .models import Salary, CompensatoryDay
from .services import PayrollCalculationService, CompensatoryDayService


class EnhancedEarningsSerializer(serializers.Serializer):
    """
    Enhanced earnings serializer with detailed breakdown for UI display
    """
    
    def to_representation(self, instance):
        """
        Convert salary calculation result to enhanced format
        """
        if not hasattr(instance, 'employee') or not hasattr(instance, 'year') or not hasattr(instance, 'month'):
            # Expect instance to have employee, year, month attributes
            raise serializers.ValidationError("Invalid instance for earnings calculation")
        
        # Use advanced calculation service
        calc_service = PayrollCalculationService(instance.employee, instance.year, instance.month)
        result = calc_service.calculate_monthly_salary()
        
        # Get compensatory days info
        comp_service = CompensatoryDayService()
        comp_balance = comp_service.get_compensatory_day_balance(instance.employee)
        comp_days_this_period = comp_service.get_employee_compensatory_days(
            instance.employee, instance.year, instance.month
        )
        
        return {
            "employee": {
                "id": instance.employee.id,
                "name": instance.employee.get_full_name(),
                "email": instance.employee.email,
                "role": instance.employee.role
            },
            "period": f"{instance.year}-{instance.month:02d}",
            "calculation_type": instance.calculation_type,
            "currency": instance.currency,
            
            "summary": {
                "total_gross_pay": result['total_gross_pay'],
                "total_hours": result['total_hours'],
                "worked_days": len([calc for calc in result.get('daily_calculations', [])]),
                "compensatory_days_earned": result['compensatory_days_earned']
            },
            
            "hours_breakdown": self._build_hours_breakdown(result),
            "pay_breakdown": self._build_pay_breakdown(result, instance),
            "compensatory_days": self._build_compensatory_breakdown(comp_balance, comp_days_this_period),
            "legal_compliance": self._build_compliance_info(result),
            "rates_applied": self._build_rates_info(instance),
            "daily_breakdown": self._build_daily_breakdown(result.get('daily_calculations', [])),
            "attendance": self._build_attendance_info(result)
        }
    
    def _build_hours_breakdown(self, result):
        """Build detailed hours breakdown"""
        return {
            "regular_hours": float(result.get('regular_hours', 0)),
            "overtime": {
                "first_2h_per_day": 0,  # Will be calculated from daily breakdown
                "additional_hours": 0,   # Will be calculated from daily breakdown
                "holiday_overtime": 0,
                "sabbath_overtime": 0
            },
            "special_days": {
                "holiday_hours": float(result.get('holiday_hours', 0)),
                "sabbath_hours": float(result.get('sabbath_hours', 0)),
                "regular_friday_evening": 0
            }
        }
    
    def _build_pay_breakdown(self, result, context_instance):
        """Build detailed pay breakdown"""
        # Get salary object from employee
        salary = context_instance.employee.salary_info
        base_rate = salary.hourly_rate or Decimal('0')
        
        return {
            "regular_pay": float(result.get('regular_hours', 0) * base_rate),
            "overtime_pay": {
                "first_2h": 0,         # Calculated from daily breakdown
                "additional": 0,       # Calculated from daily breakdown  
                "holiday_overtime": 0,
                "sabbath_overtime": 0
            },
            "special_day_pay": {
                "holiday_base": float(result.get('holiday_hours', 0) * base_rate * Decimal('1.5')),
                "sabbath_base": float(result.get('sabbath_hours', 0) * base_rate * Decimal('1.5')),
                "friday_evening": 0
            },
            "bonuses": {
                "attendance_bonus": 0,
                "performance_bonus": 0,
                "other_bonuses": 0
            },
            "minimum_wage_supplement": float(result.get('minimum_wage_supplement', 0))
        }
    
    def _build_compensatory_breakdown(self, balance, current_period_days):
        """Build compensatory days breakdown"""
        details = []
        for comp_day in current_period_days:
            detail = {
                "date_earned": comp_day.date_earned.isoformat(),
                "reason": comp_day.reason,
                "is_used": comp_day.date_used is not None
            }
            
            # Add specific details based on reason
            if comp_day.reason == 'holiday':
                # Try to get holiday info
                from integrations.models import Holiday
                holiday = Holiday.objects.filter(date=comp_day.date_earned, is_holiday=True).first()
                if holiday:
                    detail["holiday_name"] = holiday.name
            elif comp_day.reason == 'shabbat':
                # Try to get Sabbath times
                from integrations.models import Holiday
                sabbath = Holiday.objects.filter(date=comp_day.date_earned, is_shabbat=True).first()
                if sabbath and sabbath.start_time and sabbath.end_time:
                    detail["sabbath_start"] = sabbath.start_time.isoformat()
                    detail["sabbath_end"] = sabbath.end_time.isoformat()
            
            details.append(detail)
        
        return {
            "earned_this_period": len(current_period_days),
            "total_balance": {
                "unused_holiday": balance['holiday']['unused'],
                "unused_sabbath": balance['sabbath']['unused'],
                "total_unused": balance['unused']
            },
            "details": details
        }
    
    def _build_compliance_info(self, result):
        """Build legal compliance information"""
        violations = result.get('legal_violations', [])
        warnings = result.get('warnings', [])
        
        # Calculate weekly overtime status (simplified)
        weekly_overtime = 0  # Would need weekly calculation
        
        return {
            "violations": violations,
            "warnings": warnings,
            "weekly_overtime_status": {
                "current_week_overtime": weekly_overtime,
                "max_allowed": 16.0,
                "remaining": max(0, 16.0 - weekly_overtime)
            }
        }
    
    def _build_rates_info(self, context_instance):
        """Build rates information"""
        salary = context_instance.employee.salary_info
        base_rate = salary.hourly_rate or Decimal('0')
        
        return {
            "base_hourly": float(base_rate),
            "overtime_125": float(base_rate * Decimal('1.25')),
            "overtime_150": float(base_rate * Decimal('1.50')),
            "overtime_175": float(base_rate * Decimal('1.75')),
            "overtime_200": float(base_rate * Decimal('2.00')),
            "holiday_base": float(base_rate * Decimal('1.50')),
            "sabbath_base": float(base_rate * Decimal('1.50'))
        }
    
    def _build_daily_breakdown(self, daily_calculations):
        """Build daily breakdown from calculation results"""
        breakdown = []
        
        for calc in daily_calculations:
            day_info = {
                "date": calc['date'].isoformat(),
                "hours_worked": float(calc['hours_worked']),
                "gross_pay": float(calc['total_pay']),
                "breakdown": {}
            }
            
            # Determine day type and add specific info
            if calc['is_holiday']:
                day_info["type"] = "holiday"
                day_info["holiday_name"] = calc.get('holiday_name', 'Unknown Holiday')
                day_info["breakdown"]["holiday_base"] = float(calc['hours_worked'])
                day_info["compensatory_day"] = calc['compensatory_day_created']
            elif calc['is_sabbath']:
                day_info["type"] = "sabbath"
                if calc.get('sabbath_type'):
                    day_info["sabbath_type"] = calc['sabbath_type']
                day_info["breakdown"]["sabbath_base"] = float(calc['hours_worked'])
                day_info["compensatory_day"] = calc['compensatory_day_created']
            else:
                day_info["type"] = "regular"
                # Add regular/overtime breakdown
                if calc['breakdown']:
                    day_info["breakdown"]["regular"] = float(calc['breakdown'].get('regular_hours', 0))
                    overtime_1 = float(calc['breakdown'].get('overtime_hours_1', 0))
                    overtime_2 = float(calc['breakdown'].get('overtime_hours_2', 0))
                    if overtime_1 > 0:
                        day_info["breakdown"]["overtime_125"] = overtime_1
                    if overtime_2 > 0:
                        day_info["breakdown"]["overtime_150"] = overtime_2
            
            breakdown.append(day_info)
        
        return breakdown
    
    def _build_attendance_info(self, result):
        """Build attendance information"""
        return {
            "working_days_in_period": result.get('total_working_days', 0),
            "days_worked": result.get('worked_days', 0),
            "days_missed": max(0, result.get('total_working_days', 0) - result.get('worked_days', 0)),
            "attendance_rate": round(
                (result.get('worked_days', 0) / result.get('total_working_days', 1)) * 100, 2
            ) if result.get('total_working_days', 0) > 0 else 0
        }


class CompensatoryDayDetailSerializer(serializers.ModelSerializer):
    """Detailed compensatory day serializer"""
    
    employee_name = serializers.ReadOnlyField(source='employee.get_full_name')
    is_used = serializers.SerializerMethodField()
    holiday_info = serializers.SerializerMethodField()
    sabbath_info = serializers.SerializerMethodField()
    
    class Meta:
        model = CompensatoryDay
        fields = [
            'id', 'employee', 'employee_name', 'date_earned', 'reason',
            'date_used', 'is_used', 'holiday_info', 'sabbath_info', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_is_used(self, obj):
        return obj.date_used is not None
    
    def get_holiday_info(self, obj):
        if obj.reason == 'holiday':
            from integrations.models import Holiday
            holiday = Holiday.objects.filter(date=obj.date_earned, is_holiday=True).first()
            if holiday:
                return {
                    "name": holiday.name,
                    "is_special_shabbat": holiday.is_special_shabbat
                }
        return None
    
    def get_sabbath_info(self, obj):
        if obj.reason == 'shabbat':
            from integrations.models import Holiday
            sabbath = Holiday.objects.filter(date=obj.date_earned, is_shabbat=True).first()
            if sabbath:
                info = {
                    "is_special": sabbath.is_special_shabbat
                }
                if sabbath.start_time and sabbath.end_time:
                    info["start_time"] = sabbath.start_time.isoformat()
                    info["end_time"] = sabbath.end_time.isoformat()
                return info
        return None