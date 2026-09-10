"""Host ceilings never constitute external authority."""
from .contracts import integer, require

MIB = 1024 * 1024
DISCOVERY_STOP = 8 * MIB
OUTBOUND_STOP = 12 * MIB
HARD_STOP = 16 * MIB
DEFAULTS = dict(timezone="UTC", research_enabled=True, principal_messages_enabled=False,
                daily_micro_usd=0, job_micro_usd=0, daily_operations=0, daily_invites=10, daily_total=100)

def effective(host=None):
    value = {**DEFAULTS, **(host or {})}
    require(set(value) <= set(DEFAULTS), "invalid_settings")
    for key in DEFAULTS:
        if key.startswith("daily_") or key == "job_micro_usd": integer(value[key])
    require(value["daily_invites"] <= 10 and value["daily_total"] <= 100, "host_limit_exceeded")
    return value
