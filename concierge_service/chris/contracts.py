"""Closed wire contracts shared with the WACRM command boundary."""
import datetime as dt
import hashlib
import json
import re
from uuid import UUID
from zoneinfo import ZoneInfo

MAX_BODY = 32 * 1024
class ChrisError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status

def require(condition, code="invalid_contract", status=400):
    if not condition:
        raise ChrisError(code, status)

def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_key")
        result[key] = value
    return result

def parse(raw):
    require(isinstance(raw, (str, bytes)), "invalid_json")
    require(len(raw.encode("utf-8") if isinstance(raw, str) else raw) <= MAX_BODY, "body_too_large", 413)
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: require(False, "non_finite"))
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, ChrisError):
            raise
        raise ChrisError("invalid_json") from exc

def canonical(value):
    try:
        def normalize(item):
            if type(item) is float and item.is_integer(): return int(item)
            if isinstance(item,dict): return {key:normalize(value) for key,value in item.items()}
            if isinstance(item,list): return [normalize(value) for value in item]
            return item
        value=normalize(value)
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ChrisError("invalid_json") from exc

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def text(value, maximum=500, minimum=1):
    require(isinstance(value, str) and minimum <= len(value) <= maximum and not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value))
    return value

def uid(value):
    try:
        require(isinstance(value, str) and str(UUID(value)) == value and UUID(value).version == 4, "invalid_uuid")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ChrisError("invalid_uuid") from exc
    return value

def integer(value, maximum=2**53-1, minimum=0):
    require(type(value) is int and minimum <= value <= maximum, "invalid_integer")
    return value

def stamp(value):
    try:
        require(isinstance(value,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})',value),'invalid_timestamp')
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.tzinfo is not None, "invalid_timestamp")
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ChrisError("invalid_timestamp") from exc

def keys(value, expected, optional=()):
    require(isinstance(value, dict) and set(expected) <= set(value) <= set(expected) | set(optional))

COMMANDS = {
 "brief.propose": ["text"], "brief.save_proposal": ["proposal_id", "brief"], "brief.activate": ["proposal_id"],
 "research.start": [], "workspace.pause": ["reason"], "workspace.resume": [],
 "autonomy.set": ["enabled", "scope_kinds", "displayed_authority_revision"],
 "settings.update": [], "principal.challenge": [], "principal.unbind": ["reason"],
 "person.exclude": ["person_id", "reason"], "person.defer": ["person_id", "not_before", "reason"],
 "person.identity_attest": ["person_id", "phone_e164", "evidence_refs", "attestation_text"],
 "permission.record": ["person_id", "kind", "source_ref", "scope_text", "granted_at", "business_sender_identity", "attestation_text"],
 "permission.revoke": ["permission_id", "reason"], "pursuit.takeover": ["pursuit_id", "reason"],
 "pursuit.resume": ["pursuit_id", "reviewed_thread_watermark"], "message.draft": ["pursuit_id", "text"],
 "message.approve": ["action_id", "displayed_digest"], "action.reconcile": ["action_id"],
 "action.cancel": ["action_id", "reason"], "projection.retry": ["projection_id"], "connection.refresh": []}
OWNER = {"brief.save_proposal", "brief.activate", "workspace.resume", "autonomy.set", "settings.update", "principal.challenge", "principal.unbind", "person.identity_attest", "permission.record", "pursuit.resume", "message.approve"}
KINDS = {"invite", "reply", "permission_clarification", "followup", "group_create", "group_introduction", "principal_reply"}
SETTINGS = {"timezone", "research_enabled", "principal_messages_enabled", "daily_micro_usd", "job_micro_usd", "daily_operations", "daily_invites", "daily_total"}

def brief(value):
    keys(value, ["objective", "principal_display_name", "principal_public_context", "timezone"], ["candidate_archetypes", "geography_include", "geography_exclude", "explicit_exclusions", "approved_claims", "confidentiality_rules", "known_relationship_policy"])
    text(value["objective"], 4000); text(value["principal_display_name"], 120); text(value["principal_public_context"], 4000, 0)
    try:
        ZoneInfo(value["timezone"])
    except (KeyError, ValueError, TypeError):
        raise ChrisError("invalid_timezone") from None
    for key, cap in (("candidate_archetypes", 12), ("geography_include", 50), ("geography_exclude", 50), ("explicit_exclusions", 50), ("confidentiality_rules", 50)):
        if key in value:
            require(isinstance(value[key], list) and len(value[key]) <= cap)
            for item in value[key]: text(item, 300)
    if "known_relationship_policy" in value:
        require(value["known_relationship_policy"] in {"wacrm", "strict_first_degree"})
    require(isinstance(value.get("approved_claims", []), list) and len(value.get("approved_claims", [])) <= 50)
    for claim in value.get("approved_claims", []):
        keys(claim, ["id", "text", "evidence_ref", "public"])
        text(claim["id"]); text(claim["text"], 1000); text(claim["evidence_ref"])
        require(type(claim["public"]) is bool)
    return value

def command(value):
    keys(value, ["schema_version", "command_id", "expected_revision", "command", "payload"])
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "upgrade_required", 409)
    uid(value["command_id"]); integer(value["expected_revision"])
    name, p = value["command"], value["payload"]
    require(isinstance(name, str) and name in COMMANDS)
    keys(p, COMMANDS[name], SETTINGS if name == "settings.update" else ())
    for key, item in p.items():
        if key.endswith("_id"): uid(item)
        elif key in {"enabled", "research_enabled", "principal_messages_enabled"}: require(type(item) is bool)
        elif key in {"displayed_authority_revision", "reviewed_thread_watermark"} or key.startswith("daily_") or key == "job_micro_usd": integer(item)
        elif key in {"not_before", "granted_at"}: stamp(item)
        elif key == "brief": brief(item)
        elif key == "scope_kinds": require(isinstance(item, list) and len(item) == len(set(item)) and set(item) <= KINDS)
        elif key == "evidence_refs":
            require(isinstance(item, list) and 1 <= len(item) <= 20)
            for ref in item: text(ref)
        elif key == "kind": require(item == "contact")
        else: text(item, 8000 if name == "brief.propose" else 16000 if key == "text" else 500)
    canonical(value)
    return value

def actor(value):
    keys(value, ["user_id", "role", "request_id"])
    uid(value["user_id"]); uid(value["request_id"])
    require(value["role"] in {"owner", "admin", "agent", "viewer"})
    return value
