"""Identity proof is distinct from syntax, commercial relevance and consent."""
import hashlib
import hmac
import re
import secrets
import phonenumbers
from .contracts import require
from .state import cancel_unstarted

PHONE = re.compile(r"\+[1-9][0-9]{7,14}$")

def phone(value):
    require(isinstance(value, str) and PHONE.fullmatch(value), "international_phone_required")
    try:
        parsed = phonenumbers.parse(value, None)
        require(phonenumbers.is_possible_number(parsed), "international_phone_required")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        require(False, "international_phone_required")

def challenge(state, now):
    nonce = secrets.token_urlsafe(24)
    state["challenge"] = dict(digest=hashlib.sha256(nonce.encode()).hexdigest(), expires=now + 600, attempts=0,
                              connection_generation=(state["connection"] or {}).get("generation"))
    return nonce

def claim_principal(state, *, nonce, sender, chat, now, direct, forwarded=False):
    c = state.get("challenge")
    require(c is not None, "challenge_expired", 409)
    c["attempts"] += 1
    require(c["attempts"] <= 5 and now <= c["expires"] and direct and not forwarded, "challenge_invalid", 409)
    connection = state["connection"] or {}
    require(c["connection_generation"] == connection.get("generation") and connection.get("self_provider_id") != sender, "principal_not_distinct", 409)
    require(hmac.compare_digest(c["digest"], hashlib.sha256(nonce.encode()).hexdigest()), "challenge_invalid", 409)
    revision = (state["principal"] or {}).get("revision", 0) + 1
    state["principal"] = dict(provider_id=sender, chat_id=chat, revision=revision, verified_at=now,synthetic=state.get('mode')=='simulation')
    state["challenge"] = None
    cancel_unstarted(state)
    return state["principal"]

def bind_connection(state, observation):
    require(observation.get("type") == "WHATSAPP" and observation.get("provider_account_id") and observation.get("self_provider_id"), "account_identity_unresolved", 409)
    previous = state["connection"] or {}
    changed = previous.get("self_provider_id") != observation["self_provider_id"] or previous.get("provider_account_id") != observation["provider_account_id"]
    generation = previous.get("generation", 0) + int(changed)
    state["connection"] = {**observation, "generation": generation}
    if changed:
        state["principal"] = None
        state["authority"]["external_enabled"] = False
        state["authority"]["revision"] += 1
        cancel_unstarted(state)
        for permission in state["permissions"].values(): permission["status"] = "revoked"
        state['identity_aliases'] = {}
        for person in state['people'].values():
            person.pop('provider_id',None)
            person.pop('provider_identity_receipt',None)
    return changed
