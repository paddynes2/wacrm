# Standalone dogfood verification — 2026-09-09

Integrated code checkpoint: `e4d0525`, branch
`codex/standalone-dogfood-20260909`, checkout `C:/wacrm-dogfood`.
Local entry: http://127.0.0.1:8316/dogfood. The private health endpoint on 8317
reports `standalone-concierge`, `simulation`, worker enabled. The app was restarted
from the fresh `.local/venv` after final code integration. No build remains running.

## Verified implementation

- WACRM-owned standalone service, extracted state/calendar rules and durable worker;
  no runtime Fleet import or OS path dependency.
- Explicit outbound brief, synthetic or Treg candidate discovery, queued sourced
  qualification, separate unverified phone research, reviewed CRM promotion.
- Typed sandbox messages run the conversation orchestrator; real model adapters
  remain explicit per-account configuration. Scripted fixture replies are labelled.
- Account-bound Unipile polling, source IDs and deduplication, manual takeover,
  opt-out, queued follow-up, pause/retry and stale-result cancellation.
- Scoped introduction/calendar consent and exact reviewed payloads; explicit
  working hours, partial availability, exception requests, booking-link fallback,
  booking, reschedule and cancellation.
- CRM transcript and outcome notes use idempotent verified projections; group and
  calendar events are excluded from the direct inbox. Amendment history remains
  append-only and survives the report's normal recent-event display limit.
- Optional host-authorized live WhatsApp and Google Calendar execution is wired
  through the private API. It remains inactive in the normal launcher. Exact
  payloads, durable pre-write claims, account identity and read-back are checked.
- Outcome/effort/cost reporting, data export and read-only legacy inspection/import.
  Imported original evidence is retained, and canonical identity mapping preserves
  permanent opt-out suppression across replacement pursuits.

## Results

| Check | Result |
|---|---|
| Frontend suite | 97 files, **978 tests passed** |
| Python suite in fresh virtual environment | **246 tests passed** |
| TypeScript | Passed, including final production build |
| Scoped ESLint | Passed on changed UI, API, CRM and native-send files |
| Production build | Passed at `e4d0525` in isolated `C:/wacrm-dogfood-build` |
| Final real local HTTP journey | **54 requests passed** against final restarted app |
| Browser desktop | Brief, discovery, automatic reply, introduction, booking, reschedule, partial access, exception and booking-link preparation passed |
| Browser mobile | 390×844, no horizontal overflow; keyboard controls and saved-calendar/draft hydration passed; no browser errors in final checks |
| Runtime dependencies | Fresh venv installation from pinned runtime dependencies passed; no global packages/Fleet required |

The HTTP test creates unique retained local fixtures. It verifies automatic worker
progress, qualification, canonical CRM contact reuse, three correctly labelled direct
messages, introduction, booking/cancellation, one cancellation outcome note after
repeated reconciliation, STOP, cross-origin refusal and another account's isolation.
The final run uses the clean virtual environment. An intermediate dev run returned
a Next JSON parsing error during ongoing integration; subsequent stable runs passed.

Adversarial tests include duplicate/reordered events, changed brief/evidence,
simultaneous workers, expired leases, takeover/STOP before execution, provider account
changes, malformed responses, budget exhaustion, prompt-injection attempts, rejected
host authorization, payload tampering, uncertain provider writes and simulated process
death after a write. Provider writes in these tests terminate in fake HTTP functions.

Build notices remain for the existing middleware convention and Edge/static-generation
behavior. No migration or broad dependency upgrade was introduced to remove them.

Screenshot: [mobile calendar](../.local/qa/mobile-calendar.png). Additional desktop
evidence is in `.local/qa/`. Screenshots and local execution databases are gitignored.

## Not established by these results

No Wabi number was purchased, registered or paired; no Unipile account, OAuth tokens,
paid research/model credentials or live host authorization was installed. No actual
message or invitation was sent. The old Wabi trial's ownership is unverified.
No real discovery accuracy, model quality, recipient delivery, attended meeting,
useful introduction, customer acquisition or commercial viability is claimed.

Unknown/ambiguous/group chats and media remain assigned to human review; current
polling does not autonomously attach group/principal conversations to a prospect.
Research assesses provider search records rather than claiming independent website
verification. Sparse/uncertain external effects require reconciliation before reuse.
The SQLite worker is a single-host dogfood design. Public self-service onboarding,
production hosting, multi-host scheduling, billing and production-scale isolation
acceptance are not delivered by this local experiment.

The original `C:/wacrm-product` checkout and its Fleet ledger remain preserved.
Supabase was not reset. Local source commits have not been merged or deployed publicly.
Use [the runbook](STANDALONE-DOGFOOD.md) and [live acceptance steps](LIVE-ACCEPTANCE.md)
for the next controlled experiment.
