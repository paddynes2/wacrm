# Standalone concierge core extraction

Source: OS/Fleet commit `a4e6e74cb7da38ca3bbd84fe812cc609d57f607c`, under
`apps/internal/agent-fleet/fleet/`. Extracted on 2026-09-09. Original files remain
unchanged. This document records provenance, not a claim of live provider acceptance.

| Product module | Source | Boundary |
| --- | --- | --- |
| `concierge_core.state` | `concierge.py` | Validation, reducer, suppression and action checks |
| `concierge_core.calendar` | `concierge_calendar.py` | Timezones, proposals, fresh read checks and booking verification |
| `concierge_core.amendment` | `concierge_amendment.py` | Frozen reschedule/cancel proposals, rechecks and receipts |

The state API is `validate(event)`, `derive(observations)`,
`scoped_view(all_events, pursuit_id)`, `check_action(state, purpose, revision)`,
`_digest(value)` and `introduction_draft(state)`. The private Fleet `_scoped_view`
is exported as `scoped_view`. Fleet clock parsing is replaced by an equivalent
local standard-library parser. Calendar and amendment public names and signatures
are unchanged; their executable ASTs were compared with the source.

The core imports only Python standard-library modules. IANA timezone data must be
available to `zoneinfo`; on Windows the host generally supplies the `tzdata`
distribution. Tests use pytest; the core itself does not import pytest or Fleet.

## Host obligations

- Read an account's complete ordered observations before calling `scoped_view`.
  A person opted out in another pursuit on the same account stays suppressed.
- Persist observations, source evidence and message text outside the reducer.
  Validate and compare the current revision under the same transaction/lock as
  append. Enforce account-wide event-ID collision checks and replay idempotency.
- The reducer accepts host observations, not model authority. Consent remains
  scope-specific and evidence-linked. An initial contact requires eligibility
  evidence; an introduction additionally requires both parties' group agreement.
- Freeze and bind exact actions to approval. Check revision and identity again
  immediately before dispatch. Persist dispatch-start claims before contacting
  providers; uncertain outcomes require reconciliation and must not auto-retry.
- Verify introduction membership and booking read-back before creating verified
  observations. `derive` consumes trusted evidence; it does not call providers.
- Keep simulated effects and live effects in separately bound workspaces.
- Calendar readers must return account-bound, timestamped complete evidence.
  Missing or stale calendar coverage cannot establish availability. Amendment
  proposals and their digests do not authorize mutation.

## Preserved limits

The state reducer keeps the latest inbound per party by strictly increasing
provider timestamp. Equal timestamps are not a new latest message. The host must
not assume second-resolution messages constitute a complete conversation-memory
model. The source ledger reader, dispatcher and approval machinery were not
extracted: they require product storage/provider implementations and tests.

`stage_booking` retains the existing Google Calendar proposal identifier as its
contract. This is not a configured calendar integration. `booking_verified`
observations are a trusted host seam, so hosts must verify their evidence before
appending; receipt IDs alone are insufficient.

## Verification

116 tests passed on 2026-09-09 using Python 3.11 / pytest 8.3.4:

```powershell
$env:PYTHONPATH = "$PWD/concierge_service"
python -m pytest concierge_service/tests/test_core_state.py concierge_service/tests/test_core_calendar.py concierge_service/tests/test_core_amendment.py -q
```

Calendar and amendment suites were ported with import changes. State tests retain
the source's pure contracts and additionally cover cross-pursuit opt-out,
takeover/stale revisions, dispatch uncertainty, replay, reply reconciliation and
booking digests. They perform no external reads, sends or calendar mutations.
