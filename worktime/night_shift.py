from datetime import datetime, time, timedelta

import pytz

NIGHT_START = time(22, 0)  # 10 PM
NIGHT_END = time(6, 0)  # 6 AM

# Israel timezone for proper night shift calculation
ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")


def night_hours(start: datetime, end: datetime) -> float:
    """
    Calculate night shift hours between start and end times.
    Night shift is defined as 22:00 to 06:00 in local Israel time.

    Args:
        start (datetime): Work start time (timezone-aware)
        end (datetime): Work end time (timezone-aware)

    Returns:
        float: Number of night shift hours worked
    """
    if start >= end:
        return 0.0

    # Convert to Israel timezone for proper night shift calculation
    if start.tzinfo is not None:
        start_local = start.astimezone(ISRAEL_TZ)
        end_local = end.astimezone(ISRAEL_TZ)
    else:
        # If no timezone info, assume it's already in Israel timezone
        start_local = ISRAEL_TZ.localize(start)
        end_local = ISRAEL_TZ.localize(end)

    total = 0.0
    cur = start_local

    # Process in 30-minute increments for accuracy
    while cur < end_local:
        nxt = min(cur + timedelta(minutes=30), end_local)
        t = cur.time()

        # Check if current time is in night shift period
        if t >= NIGHT_START or t < NIGHT_END:
            total += (nxt - cur).total_seconds() / 3600

        cur = nxt

    return round(total, 2)
