"""Google Calendar REST adapter with explicit account and mutation boundaries.

Verified 2026-09-09 against developers.google.com/workspace/calendar/api/v3/
reference/{freebusy/query,events/insert,events/patch,events,calendarList/get}.
Retains Fleet CalendarReader's ownership, complete coverage and read-back checks.
No OAuth discovery, environment secrets, automatic refresh or enabled send gate.
"""
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import quote
from uuid import uuid4

from .providers import _request, _text, ProviderError
from .concierge_core import calendar as core
from .concierge_core import amendment
from .concierge_core.state import _digest

BASE = "https://www.googleapis.com/calendar/v3"


class GoogleCalendar:
    def __init__(self, account_id, token_provider, calendar_ids, *, http=None):
        self.account_id = _text(account_id, "expected primary calendar identity", 500)
        if not callable(token_provider) or not isinstance(calendar_ids, list) or not calendar_ids:
            raise ValueError("Explicit token provider and permitted calendars required")
        self.calendar_ids = tuple(_text(v, "calendar id", 500) for v in calendar_ids)
        if len(set(self.calendar_ids)) != len(self.calendar_ids):
            raise ValueError("Duplicate calendar binding")
        self.token_provider, self.http = token_provider, http

    def request(self, method, path, body=None, extra_headers=None):
        token = _text(self.token_provider(), "OAuth token", 4000)
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json", **(extra_headers or {})}
        return _request({"http": self.http}, method, BASE + path, headers, body)[1]

    def validate_account(self, account_id):
        if account_id != self.account_id:
            raise ValueError("Calendar account binding mismatch")
        primary = self.request("GET", "/users/me/calendarList/primary")
        if primary.get("id") != self.account_id or primary.get("primary") is not True or primary.get("deleted"):
            raise ValueError("OAuth primary calendar identity differs from configured account")

    def calendar(self, calendar_id):
        if calendar_id not in self.calendar_ids:
            raise ValueError("Calendar is not in the host binding")
        return quote(calendar_id, safe="")

    def read_freebusy(self, *, participant_id, account_id, calendar_ids, start, end):
        _text(participant_id, "participant", 500)
        if not isinstance(calendar_ids, list) or not calendar_ids or len(calendar_ids) > 50:
            raise ValueError("Explicit bounded calendar list required")
        for cid in calendar_ids:
            self.calendar(cid)
        span = core.Interval(start, end)
        self.validate_account(account_id)
        payload = self.request("POST", "/freeBusy", {"timeMin": span.start.isoformat(), "timeMax": span.end.isoformat(),
                                                       "items": [{"id": cid} for cid in calendar_ids]})
        core.parse_freebusy(payload, calendar_ids, start, end)
        self.validate_account(account_id)
        return {"account_id": account_id, "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source_ref": "googlecalendar:freebusy:" + _digest(payload), "payload": payload}

    def read_event(self, *, account_id, calendar_id, event_id):
        cid = self.calendar(calendar_id)
        eid = quote(_text(event_id, "event id", 1000), safe="")
        self.validate_account(account_id)
        payload = self.request("GET", f"/calendars/{cid}/events/{eid}")
        if payload.get("id") != event_id or payload.get("attendeesOmitted") is True:
            raise ValueError("Calendar event identity or attendee completeness mismatch")
        self.validate_account(account_id)
        return {"account_id": account_id, "calendar_id": calendar_id, "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source_ref": "googlecalendar:event:" + _digest(payload), "event": payload, "payload": payload}

    def prepare_create(self, calendar_id, request):
        self.calendar(calendar_id)
        proposal = request["proposal"]
        checked = core.stage_booking(proposal, proposal["attendees"], proposal["summary"])
        if checked != request:
            raise ValueError("Booking request changed")
        body = {"id": uuid4().hex, "summary": proposal["summary"],
                "start": {"dateTime": proposal["start"]}, "end": {"dateTime": proposal["end"]},
                "attendees": [{"email": email} for email in proposal["attendees"]]}
        plan = {"operation": "create", "account_id": self.account_id, "calendar_id": calendar_id,
                "body": body, "request": deepcopy(request), "event_id": body["id"]}
        return {**plan, "digest": _digest(plan)}

    def prepare_amendment(self, proposal):
        amendment._validate(proposal)
        own = proposal["ownership"]
        if own["account_id"] != self.account_id:
            raise ValueError("Amendment account mismatch")
        self.calendar(own["calendar_id"])
        etag = _text(proposal["before"].get("etag"), "event ETag", 500)
        after = proposal["after"]
        body = {"status": after["status"]} if proposal["operation"] == "cancel" else {
            "start": {"dateTime": after["start"]}, "end": {"dateTime": after["end"]}}
        plan = {"operation": proposal["operation"], **own, "body": body,
                "etag": etag, "proposal": deepcopy(proposal)}
        return {**plan, "digest": _digest(plan)}

    def execute(self, plan, *, authorize, claim, complete, failed, preflight, mutation_guard):
        """Host-only: exact approval, durable one-time claim and result callbacks.

        claim must commit before returning True and reject previously attempted IDs.
        failed must durably retain uncertainty; no provider mutation is retried here.
        No default callback can authorize execution.
        """
        if not all(callable(f) for f in (authorize, claim, complete, failed, preflight, mutation_guard)):
            raise ValueError("Explicit authorization and durable execution callbacks required")
        frozen = deepcopy(plan)
        if _digest({k: v for k, v in frozen.items() if k != "digest"}) != frozen.get("digest"):
            raise ValueError("Calendar action digest mismatch")
        if frozen.get("account_id") != self.account_id:
            raise ValueError("Calendar action account mismatch")
        cid = self.calendar(frozen["calendar_id"])
        if frozen.get("operation") not in {"create", "reschedule", "cancel"}:
            raise ValueError("Unsupported calendar mutation")
        if frozen["operation"] == "create":
            proposal = frozen["request"]["proposal"]
            checked = core.stage_booking(proposal, proposal["attendees"], proposal["summary"])
            expected = {"id": frozen["event_id"], "summary": proposal["summary"],
                        "start": {"dateTime": proposal["start"]}, "end": {"dateTime": proposal["end"]},
                        "attendees": [{"email": email} for email in proposal["attendees"]]}
            if checked != frozen["request"] or expected != frozen["body"]:
                raise ValueError("Booking body differs from approved request")
        else:
            expected = self.prepare_amendment(frozen["proposal"])
            if expected != frozen:
                raise ValueError("Amendment body differs from prepared request")
        if authorize(deepcopy(frozen)) is not True:
            raise ValueError("Exact calendar action is not authorized")
        preflight()
        if claim(deepcopy(frozen)) is not True:
            raise ValueError("Calendar action already attempted or claim unavailable")
        invoked = False
        try:
            with mutation_guard():
                preflight()
                self.validate_account(self.account_id)
                if frozen["operation"] == "create":
                    method, path, headers = "POST", f"/calendars/{cid}/events?sendUpdates=all", {}
                else:
                    method, path, headers = "PATCH", f"/calendars/{cid}/events/{quote(frozen['event_id'], safe='')}?sendUpdates=all", {"If-Match": frozen["etag"]}
                invoked = True
                response = self.request(method, path, frozen["body"], headers)
                if response.get("id") != frozen["event_id"]:
                    raise ValueError("Calendar mutation receipt identity mismatch")
                receipt = self.read_event(account_id=self.account_id, calendar_id=frozen["calendar_id"], event_id=frozen["event_id"])
                if frozen["operation"] == "create":
                    verified = core.verify_booking(frozen["request"], receipt["event"])
                else:
                    verified = amendment.verify_amendment(frozen["proposal"], read_event=lambda **kw: receipt)
                if not verified:
                    raise ValueError("Calendar read-back does not prove approved mutation")
                result = {"id": frozen["event_id"], "event": receipt["event"], "source_ref": receipt["source_ref"],
                          "account_id": self.account_id, "calendar_id": frozen["calendar_id"], "event_verified": True}
                complete(deepcopy(frozen), deepcopy(result))
                return result
        except Exception:
            failed(deepcopy(frozen), "unknown" if invoked else "not_sent")
            raise
