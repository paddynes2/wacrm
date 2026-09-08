# Concierge continuation — 2026-09-08

## Scope contract

Goal: close every independently implementable local gap between the existing CRM and a
daily-use concierge, while retaining exact external-action approvals and tenant isolation.
No live sends, purchases, credentials, auth/RLS, migrations, billing or deployment config
are changed. Integration code can be implemented and exercised with injected providers.

Acceptance: durable draft-only follow-up sequences; conservative inbound next-action
planning; background processing with retries and stop-on-reply; source-grounded prospect
import; truthful connection readiness; working native UI and repeatable local tests.

Verification: module adversarial cases, account-bound API tests, full WACRM suite/build,
Fleet targeted regression, real local HTTP journeys and desktop/mobile browser checks.

## Checkpoints

1. Existing scope and repository contracts inspected. Canonical Fleet concierge guards,
   existing provider readers and native WACRM contact store will be reused.
2. Durable SQLite queue implemented: leases, retries, pacing, caps, cancellation and
   draft-only worker. Follow-ups require the exact preceding job's verified receipt;
   an unrelated earlier message or identical pending text cannot unlock the next step.
3. Prospects page imports reviewed source-backed CSV into canonical contacts/notes.
   Readiness page reports configuration, simulation and live verification separately.
4. Operations page creates/enrolls/pauses sequences, runs due drafts, shows inbound
   suggestions, prepares editable AI replies and registers existing-chat watches.
   Worker starts with the local launcher and can only read/stage, never approve/send.
5. Live exact-action confirmation delegates to existing Fleet approval checks. It was
   tested for refusal and isolation, not exercised against a real provider. It does not
   arm transports, change credentials or add grants.
6. Reconciliation chunks long histories and writes deterministic receipt-backed outcome
   notes. Native international phone formatting is normalized without guessing country.
7. Redteam fixes: counterpart hours no longer alter principal hours; stale/replayed jobs
   cannot advance sequences; batch enrollment reports partial outcomes; long histories
   no longer permanently fail after 1,000 messages; UI header translation keys fixed.
8. Calendar amendment preparation/recheck/verification core added in
   `fleet/concierge_amendment.py`. It binds the existing event, ownership, participants
   and requested change; refuses stale evidence and changed attendees; never accepts
   a missing event as proof of cancellation. This is a tested backend library, not yet
   wired to the app's reschedule/cancel buttons or a provider mutation adapter.

## Verified checkpoints

- WACRM full suite: 948 tests pass; TypeScript and scoped lint pass.
- Fleet final concierge/transport/calendar/queue/runtime/amendment regression: 372 tests pass.
- Real local HTTP: original journey 61 requests; new operations journey 36 requests.
- Browser: imported Morgan QA with source notes, created sample sequence, reconciled
  two verified outcome notes, checked desktop Operations and mobile Connections/Operations.
- Existing production framework warnings remain; no credential/config/deployment edits.
- Final production build succeeds with all new routes. Both HTTP journeys passed again
  after restarting the final runtime. Existing test data survived the restart.
- App integration commit `fffc123`; engine integration `a4e6e74cb`; amendment library
  `cbd665c1f`. Local commits only. Shared OS documentation updated separately.

## Explicit boundaries

The app still runs locally and delivery remains simulated. Owned number and provider
calendar/WhatsApp connections need setup and live acceptance. Conversation watches poll
known provider chats; they do not discover every new chat or deploy a public webhook.
Incoming suggestions are conservative rules; AI generation uses a configured account
provider on request, then an editable review. This is not an unattended LLM conversation
agent. Sequences prepare drafts, not an armed bulk-send campaign. Stops are durable;
re-enrollment after a stop requires a future explicit reactivation flow. Pausing leaves
already-staged decisions for review/discard. Manual drafting while human-owned still
requires resuming the concierge or using the WhatsApp client.

Prospecting supports sourced CSV import, not paid discovery or an owned Apollo database.
Import checks fewer than 10,000 existing contacts; concurrent native imports cannot be
globally deduplicated without a normalized-phone database constraint. Queue history is
bounded in the UI, while predecessor execution lookup is direct. Public billing, hosted
rollout, production scale verification and self-service OAuth are not completed.
