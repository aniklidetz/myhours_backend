"""
Shift splitting logic for handling work periods that span across Sabbath or holidays
"""

import logging
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytz

from django.utils import timezone

logger = logging.getLogger(__name__)


# Legacy keys for backward compatibility with existing breakdown structures
LEGACY_KEYS = (
    "regular_hours", "overtime_125_hours", "overtime_150_hours",
    "sabbath_regular", "holiday_hours",
    "base_regular_pay", "overtime_125_pay", "overtime_150_pay", "sabbath_bonus_pay", "holiday_bonus_pay",
    "overtime_before_sabbath_1", "overtime_before_sabbath_2", "overtime_before_sabbath_3",
)


def create_empty_breakdown():
    """Create empty breakdown dictionary with all legacy keys initialized to zero."""
    from decimal import Decimal
    return {k: Decimal("0") for k in LEGACY_KEYS}


class ShiftSplitter:
    """Handles splitting of shifts that span across special periods (Sabbath, holidays)"""

    ISRAEL_TZ = pytz.timezone("Israel")
    DEFAULT_SABBATH_START_HOUR = 18  # Default if no precise time available (winter)
    SUMMER_SABBATH_START_HOUR = 19  # Summer default (roughly May-September)
    DEFAULT_SABBATH_END_HOUR = 20  # Saturday evening

    @classmethod
    def split_shift_for_sabbath(
        cls, check_in, check_out, sabbath_start_time=None, use_api=True
    ):
        """
        Split a shift that may span into Sabbath

        Args:
            check_in (datetime): Shift start time
            check_out (datetime): Shift end time
            sabbath_start_time (datetime, optional): Precise Sabbath start time
            use_api (bool): Whether to use UnifiedShabbatService for precise times

        Returns:
            dict: Split hours by period type
                {
                    'before_sabbath': Decimal,
                    'during_sabbath': Decimal,
                    'total_hours': Decimal,
                    'sabbath_start_used': datetime,
                    'api_used': bool
                }
        """
        # Ensure timezone aware
        if check_in.tzinfo is None:
            check_in = timezone.make_aware(check_in)
        if check_out.tzinfo is None:
            check_out = timezone.make_aware(check_out)

        # Convert to Israel timezone
        check_in_israel = check_in.astimezone(cls.ISRAEL_TZ)
        check_out_israel = check_out.astimezone(cls.ISRAEL_TZ)

        # Determine Sabbath start time
        api_used = False
        if sabbath_start_time:
            if sabbath_start_time.tzinfo is None:
                sabbath_start_time = timezone.make_aware(sabbath_start_time)
            sabbath_start_israel = sabbath_start_time.astimezone(cls.ISRAEL_TZ)
        elif use_api:
            # Try to use UnifiedShabbatService for precise Sabbath start time
            try:
                from integrations.services.unified_shabbat_service import (
                    get_shabbat_times,
                )

                friday_date = check_in_israel.date()
                if friday_date.weekday() != 4:  # Not Friday
                    # Find the Friday of this shift
                    days_to_friday = (4 - friday_date.weekday()) % 7
                    friday_date = friday_date + timedelta(days=days_to_friday)

                # Get precise Sabbath times from API using new unified service
                shabbat_times = get_shabbat_times(friday_date)
                sabbath_start_str = shabbat_times.get("shabbat_start")

                if sabbath_start_str:
                    # Parse the API response (already in correct ISO format)
                    sabbath_start_utc = datetime.fromisoformat(
                        sabbath_start_str.replace("Z", "+00:00")
                    )
                    sabbath_start_israel = sabbath_start_utc.astimezone(cls.ISRAEL_TZ)
                    api_used = True
                    logger.info(
                        f"🌅 Using UnifiedShabbatService Sabbath start: {sabbath_start_israel}"
                    )
                else:
                    raise ValueError("No Sabbath start time in API response")

            except Exception as e:
                logger.warning(
                    f"⚠️ Failed to get precise Sabbath time from API: {e}, using fallback"
                )
                # Fallback to default calculation
                friday_date = check_in_israel.date()
                if friday_date.weekday() != 4:  # Not Friday
                    days_to_friday = (4 - friday_date.weekday()) % 7
                    friday_date = friday_date + timedelta(days=days_to_friday)

                # Use seasonal defaults as fallback
                month = friday_date.month
                if 5 <= month <= 9:  # May through September - summer time
                    sabbath_hour = cls.SUMMER_SABBATH_START_HOUR
                else:
                    sabbath_hour = cls.DEFAULT_SABBATH_START_HOUR

                sabbath_start_israel = cls.ISRAEL_TZ.localize(
                    datetime.combine(
                        friday_date, time(sabbath_hour, 30)
                    )  # Adding 30 minutes for more accuracy
                )
        else:
            # Use default time (seasonal calculation)
            friday_date = check_in_israel.date()
            if friday_date.weekday() != 4:  # Not Friday
                # Find the Friday of this shift
                days_to_friday = (4 - friday_date.weekday()) % 7
                friday_date = friday_date + timedelta(days=days_to_friday)

            # Determine if summer or winter time
            month = friday_date.month
            if 5 <= month <= 9:  # May through September - summer time
                sabbath_hour = cls.SUMMER_SABBATH_START_HOUR
            else:
                sabbath_hour = cls.DEFAULT_SABBATH_START_HOUR

            sabbath_start_israel = cls.ISRAEL_TZ.localize(
                datetime.combine(
                    friday_date, time(sabbath_hour, 30)
                )  # Adding 30 minutes for more accuracy
            )

        # Calculate hours
        total_hours = Decimal(str((check_out - check_in).total_seconds() / 3600))

        # If shift ends before Sabbath starts, all hours are before Sabbath
        if check_out_israel <= sabbath_start_israel:
            return {
                "before_sabbath": total_hours,
                "during_sabbath": Decimal("0"),
                "total_hours": total_hours,
                "sabbath_start_used": sabbath_start_israel,
                "api_used": api_used,
            }

        # If shift starts after Sabbath starts, all hours are during Sabbath
        if check_in_israel >= sabbath_start_israel:
            return {
                "before_sabbath": Decimal("0"),
                "during_sabbath": total_hours,
                "total_hours": total_hours,
                "sabbath_start_used": sabbath_start_israel,
                "api_used": api_used,
            }

        # Shift spans across Sabbath start - need to split
        before_sabbath_seconds = (
            sabbath_start_israel - check_in_israel
        ).total_seconds()
        before_sabbath_hours = Decimal(str(before_sabbath_seconds / 3600))
        during_sabbath_hours = total_hours - before_sabbath_hours

        return {
            "before_sabbath": before_sabbath_hours.quantize(Decimal("0.01")),
            "during_sabbath": during_sabbath_hours.quantize(Decimal("0.01")),
            "total_hours": total_hours.quantize(Decimal("0.01")),
            "sabbath_start_used": sabbath_start_israel,
            "api_used": api_used,
        }

    @classmethod
    def calculate_split_overtime(
        cls, total_hours, sabbath_hours, daily_norm=Decimal("8.6")
    ):
        """
        Calculate overtime distribution for split shifts

        Args:
            total_hours (Decimal): Total hours worked
            sabbath_hours (Decimal): Hours worked during Sabbath
            daily_norm (Decimal): Daily norm (default 8.6 hours)

        Returns:
            dict: Detailed breakdown of hours by category
                {
                    'regular_hours': Decimal,           # Regular hours before Sabbath (100%)
                    'overtime_before_sabbath_1': Decimal,  # First 2 OT hours before Sabbath (125%)
                    'overtime_before_sabbath_2': Decimal,  # Additional OT before Sabbath (150%)
                    'sabbath_regular': Decimal,         # Sabbath hours within daily norm (150%)
                    'sabbath_overtime_1': Decimal,      # First 2 OT hours in Sabbath (175%)
                    'sabbath_overtime_2': Decimal       # Additional OT in Sabbath (200%)
                }
        """
        before_sabbath_hours = total_hours - sabbath_hours

        result = {
            "regular_hours": Decimal("0"),
            "overtime_before_sabbath_1": Decimal("0"),
            "overtime_before_sabbath_2": Decimal("0"),
            "sabbath_regular": Decimal("0"),
            "sabbath_overtime_1": Decimal("0"),
            "sabbath_overtime_2": Decimal("0"),
            # Ensure all expected keys exist with defaults
            "total_hours": total_hours,
            "total_regular": Decimal("0"),
            "total_overtime": Decimal("0"),
            "total_sabbath": Decimal("0"),
        }

        # First, fill hours before Sabbath
        if before_sabbath_hours > 0:
            # Regular hours (up to daily norm)
            result["regular_hours"] = min(before_sabbath_hours, daily_norm)
            remaining = before_sabbath_hours - result["regular_hours"]

            if remaining > 0:
                # First 2 overtime hours (125%)
                result["overtime_before_sabbath_1"] = min(remaining, Decimal("2"))
                remaining -= result["overtime_before_sabbath_1"]

                if remaining > 0:
                    # Additional overtime (150%)
                    result["overtime_before_sabbath_2"] = remaining

        # Then, handle Sabbath hours
        if sabbath_hours > 0:
            # How many hours until we reach daily norm?
            hours_worked_so_far = before_sabbath_hours
            hours_to_norm = max(Decimal("0"), daily_norm - hours_worked_so_far)

            # Sabbath hours within daily norm (150%)
            result["sabbath_regular"] = min(sabbath_hours, hours_to_norm)
            remaining_sabbath = sabbath_hours - result["sabbath_regular"]

            if remaining_sabbath > 0:
                # Calculate total overtime hours BEFORE entering Sabbath
                # This includes ALL overtime worked before Sabbath starts
                overtime_before_sabbath_total = (
                    result["overtime_before_sabbath_1"]
                    + result["overtime_before_sabbath_2"]
                )

                # Check if we've already used up the first 2 overtime hours slot
                # The first 2 overtime hours FOR THE ENTIRE DAY get the lower rate
                overtime_slot_1_available = max(
                    Decimal("0"), Decimal("2") - overtime_before_sabbath_total
                )

                # Assign Sabbath overtime hours based on available slots
                result["sabbath_overtime_1"] = min(
                    remaining_sabbath, overtime_slot_1_available
                )
                remaining_sabbath -= result["sabbath_overtime_1"]

                if remaining_sabbath > 0:
                    # All remaining is 200% Sabbath overtime
                    result["sabbath_overtime_2"] = remaining_sabbath

        # Calculate summary totals
        result["total_regular"] = result["regular_hours"] + result["sabbath_regular"]
        result["total_overtime"] = (
            result["overtime_before_sabbath_1"] + result["overtime_before_sabbath_2"] +
            result["sabbath_overtime_1"] + result["sabbath_overtime_2"]
        )
        result["total_sabbath"] = result["sabbath_regular"] + result["sabbath_overtime_1"] + result["sabbath_overtime_2"]

        # Round all values
        for key in result:
            result[key] = result[key].quantize(Decimal("0.01"))

        return result

    @classmethod
    def calculate_payment_for_split_shift(cls, breakdown=None, hourly_rate=None):
        """
        Calculate payment based on split shift breakdown

        Args:
            breakdown (dict, optional): Hours breakdown from calculate_split_overtime
            hourly_rate (Decimal, optional): Base hourly rate

        Returns:
            dict: Payment calculation
                {
                    'regular_pay': Decimal,
                    'overtime_before_sabbath_pay': Decimal,
                    'sabbath_pay': Decimal,
                    'sabbath_overtime_pay': Decimal,
                    'total_pay': Decimal,
                    'details': dict  # Detailed breakdown
                }
        """
        from decimal import Decimal
        
        # Protection against None parameters
        if breakdown is None:
            breakdown = create_empty_breakdown()
        else:
            # Ensure all legacy keys exist to prevent KeyError
            for k in LEGACY_KEYS:
                breakdown.setdefault(k, Decimal("0"))
        
        if hourly_rate is None:
            hourly_rate = Decimal("0")
            
        details = {}

        # Regular hours (100%)
        regular_pay = breakdown.get("regular_hours", Decimal("0")) * hourly_rate
        if breakdown.get("regular_hours", 0) > 0:
            details["regular"] = {
                "hours": breakdown.get("regular_hours", Decimal("0")),
                "rate": hourly_rate,
                "multiplier": Decimal("1.0"),
                "pay": regular_pay,
            }

        # Overtime before Sabbath
        overtime_before_pay = Decimal("0")

        # First 2 OT hours (125%)
        if breakdown.get("overtime_before_sabbath_1", 0) > 0:
            ot1_pay = (
                breakdown.get("overtime_before_sabbath_1", Decimal("0")) * hourly_rate * Decimal("1.25")
            )
            overtime_before_pay += ot1_pay
            details["overtime_125"] = {
                "hours": breakdown.get("overtime_before_sabbath_1", Decimal("0")),
                "rate": hourly_rate,
                "multiplier": Decimal("1.25"),
                "pay": ot1_pay,
            }

        # Additional OT (150%)
        if breakdown.get("overtime_before_sabbath_2", 0) > 0:
            ot2_pay = (
                breakdown.get("overtime_before_sabbath_2", Decimal("0")) * hourly_rate * Decimal("1.5")
            )
            overtime_before_pay += ot2_pay
            details["overtime_150"] = {
                "hours": breakdown.get("overtime_before_sabbath_2", Decimal("0")),
                "rate": hourly_rate,
                "multiplier": Decimal("1.5"),
                "pay": ot2_pay,
            }

        # Sabbath hours
        sabbath_pay = Decimal("0")

        # Sabbath within daily norm (150%) - increment sabbath_regular for sabbath pieces
        if breakdown.get("sabbath_regular", 0) > 0:
            sabbath_reg_pay = (
                breakdown.get("sabbath_regular", Decimal("0")) * hourly_rate * Decimal("1.5")
            )
            sabbath_pay += sabbath_reg_pay
            details["sabbath_150"] = {
                "hours": breakdown.get("sabbath_regular", Decimal("0")),
                "rate": hourly_rate,
                "multiplier": Decimal("1.5"),
                "pay": sabbath_reg_pay,
            }

        # Sabbath overtime
        sabbath_overtime_pay = Decimal("0")

        # First 2 Sabbath OT hours (175%)
        if breakdown.get("sabbath_overtime_1", 0) > 0:
            sabbath_ot1_pay = (
                breakdown.get("sabbath_overtime_1", Decimal("0")) * hourly_rate * Decimal("1.75")
            )
            sabbath_overtime_pay += sabbath_ot1_pay
            details["sabbath_overtime_175"] = {
                "hours": breakdown.get("sabbath_overtime_1", Decimal("0")),
                "rate": hourly_rate,
                "multiplier": Decimal("1.75"),
                "pay": sabbath_ot1_pay,
            }

        # Additional Sabbath OT (200%)
        if breakdown.get("sabbath_overtime_2", 0) > 0:
            sabbath_ot2_pay = (
                breakdown.get("sabbath_overtime_2", Decimal("0")) * hourly_rate * Decimal("2.0")
            )
            sabbath_overtime_pay += sabbath_ot2_pay
            details["sabbath_overtime_200"] = {
                "hours": breakdown.get("sabbath_overtime_2", Decimal("0")),
                "rate": hourly_rate,
                "multiplier": Decimal("2.0"),
                "pay": sabbath_ot2_pay,
            }

        total_pay = (
            regular_pay + overtime_before_pay + sabbath_pay + sabbath_overtime_pay
        )

        return {
            # Main payment categories
            "regular_pay": regular_pay.quantize(Decimal("0.01")),
            "overtime_before_sabbath_pay": overtime_before_pay.quantize(
                Decimal("0.01")
            ),
            "sabbath_pay": sabbath_pay.quantize(Decimal("0.01")),
            "sabbath_overtime_pay": sabbath_overtime_pay.quantize(Decimal("0.01")),
            "total_pay": total_pay.quantize(Decimal("0.01")),
            "details": details,
            
            # Legacy key aliases for backward compatibility
            "base_regular_pay": regular_pay.quantize(Decimal("0.01")),
            "overtime_125_pay": breakdown.get("overtime_before_sabbath_1", Decimal("0")) * hourly_rate * Decimal("1.25"),
            "overtime_150_pay": breakdown.get("overtime_before_sabbath_2", Decimal("0")) * hourly_rate * Decimal("1.5"),
            "sabbath_bonus_pay": sabbath_pay.quantize(Decimal("0.01")),
            "holiday_bonus_pay": Decimal("0"),  # Not used in shift splitting
            "total_salary": total_pay.quantize(Decimal("0.01")),  # Alias for total_pay
        }
