"""Explicit recipient-local business-day pacing, with no timezone inference."""
import datetime as dt
from zoneinfo import ZoneInfo


def next_followup(verified_at, timezone, verified_followups):
    if not timezone or verified_followups >= 2: return None
    local = dt.datetime.fromtimestamp(verified_at, ZoneInfo(timezone))
    remaining = 3 if verified_followups == 0 else 7
    while remaining:
        local += dt.timedelta(days=1)
        if local.weekday() < 5: remaining -= 1
    return local.timestamp()
