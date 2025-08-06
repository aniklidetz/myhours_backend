from decimal import Decimal, ROUND_HALF_UP

EIGHT_HOURS_6 = Decimal("8.6")


def calc_overtime(total_hours: Decimal) -> Decimal:
    """Calculate overtime hours based on Israeli labor law (>8.6 hours)"""
    if not isinstance(total_hours, Decimal):
        total_hours = Decimal(str(total_hours))
    
    return (total_hours - EIGHT_HOURS_6).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    ) if total_hours > EIGHT_HOURS_6 else Decimal("0.00")