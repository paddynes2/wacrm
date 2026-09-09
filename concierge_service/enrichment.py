"""Phone discovery through the deployed Treg routed contract, never verification.

Catalogue read 2026-09-09: /catalog/endpoints/treg.people.phone.find.
No paid probe was performed. Host owns budget reservations and corroboration.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from urllib.parse import urlsplit

from .providers import ProviderError, _base, _number, _request, _text

ENDPOINT = "treg.people.phone.find"


def _identity(prospect):
    name = _text(prospect.get("name"), "prospect name", 200)
    company = _text(prospect.get("company"), "prospect company", 300)
    identity = {"prospect_id": _text(prospect.get("id"), "prospect id", 200), "name": name, "company": company}
    profile = prospect.get("profile_url")
    if profile:
        try:
            url = urlsplit(profile)
        except (TypeError, ValueError):
            raise ProviderError("invalid LinkedIn identity URL") from None
        if (url.scheme != "https" or url.hostname not in {"linkedin.com", "www.linkedin.com"}
                or not re.fullmatch(r"/in/[^/]+/?", url.path) or url.query or url.fragment
                or url.username or url.password or url.port not in (None, 443)):
            raise ProviderError("phone lookup requires a public LinkedIn person URL or company domain")
        body = {"linkedin_url": profile}
        identity["profile_url"] = profile
    else:
        domain = _text(prospect.get("domain"), "prospect company domain", 253).lower()
        if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain):
            raise ProviderError("invalid company domain")
        body = {"domain": domain, "full_name": name}
        identity["domain"] = domain
    return identity, body


def _do_not_call(value):
    if isinstance(value, dict):
        return any((key in {"doNotCall", "do_not_call", "dnc"} and item is True) or _do_not_call(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_do_not_call(item) for item in value)
    return False


def enrich(prospect: dict, config: dict) -> dict:
    provider = config.get("provider")
    if provider == "fixture":
        return {"phone": None, "source": "fixture:synthetic-phone-miss", "evidence": {"synthetic": True},
                "phone_status": "missing", "cost_usd": 0, "errors": []}
    if provider != "treg":
        raise ProviderError("unsupported phone provider")
    identity, body = _identity(prospect)
    token = _text(config.get("token"), "treg token", 2000)
    cap = _number(config.get("max_cost_usd"), "phone lookup budget", 0.0001)
    base = _base(config.get("base_url", "https://treg.to"), {"treg.to"})
    headers, data = _request(config, "POST", base + "/call/" + ENDPOINT, {
        "Content-Type": "application/json", "X-Treg-Token": token,
        "X-Treg-Route-Max-Cost": f"{cap:.4f}", "X-Treg-Route-Strict-Filters": "1"}, body)
    output, metadata = data.get("output"), data.get("_treg")
    if (not isinstance(output, dict) or "phone" not in output or not isinstance(metadata, dict)
            or metadata.get("outcome") not in {"hit", "miss"}):
        raise ProviderError("invalid phone response envelope")
    normalized = {k.lower(): v for k, v in headers.items()}
    raw_cost = normalized.get("x-treg-cost-micro", metadata.get("charged_micro"))
    try:
        if isinstance(raw_cost, bool) or raw_cost is None or str(int(raw_cost)) != str(raw_cost):
            raise ValueError()
        cost = _number(int(raw_cost), "settled phone lookup cost") / 1_000_000
    except (TypeError, ValueError):
        raise ProviderError("missing or invalid phone lookup settlement") from None
    raw_phone = output["phone"]
    if raw_phone is not None and not isinstance(raw_phone, str):
        raise ProviderError("invalid phone result")
    errors = []
    if cost > cap:
        errors.append("Settled phone lookup charge exceeds requested cap; pause enrichment.")
    phone = raw_phone if isinstance(raw_phone, str) and re.fullmatch(r"\+[1-9][0-9]{7,14}", raw_phone) else None
    status = "provider_unverified" if phone else "missing"
    if raw_phone and not phone:
        status = "unresolved_format"
        errors.append("Provider phone is not E.164; country code was not guessed.")
    if metadata["outcome"] == "miss" and raw_phone:
        phone, status = None, "unresolved"
        errors.append("Phone result contradicts provider miss outcome; review evidence.")
    if _do_not_call(data):
        phone, status = None, "do_not_call"
        errors.append("Provider marks a contact do-not-call; no eligible phone returned.")
    if normalized.get("x-treg-ignored-filters"):
        phone, status = None, "unresolved"
        errors.append("Provider ignored identity filters; corroboration required.")
    evidence = {"requested_identity": identity, "request": body, "output": output, "raw": data.get("raw"),
                "served_by": metadata.get("served_by"), "tried": metadata.get("tried", []),
                "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "identity_sha256": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
                "ownership_verified": False, "whatsapp_reachability_verified": False,
                "contact_permission_verified": False}
    return {"phone": phone, "source": "treg:" + str(metadata.get("served_by") or ENDPOINT),
            "evidence": evidence, "phone_status": status, "cost_usd": cost, "errors": errors}
