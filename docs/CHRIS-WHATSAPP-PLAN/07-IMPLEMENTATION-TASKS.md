# Ordered implementation tasks

This is the build order. Complete each dependency and its assertions before moving dependent work forward. Keep `BUILD-RESULTS.md` current with task ID, commit, tests, evidence and any external-only gap. A task is not done because its file exists. Every new runtime path must be reachable from an actual command, worker or page.

## T00: isolate and verify baseline

Inputs: entire plan, current WACRM source, `source-manifest.json`, repository instructions. Create a new isolated WACRM worktree from the plan branch/commit. Preserve other dirty worktrees and the concurrent Fleet session. Compare hashes and current implementations; record meaningful drift, reuse improvements and resolve overlap locally. Do not copy secrets or runtime databases into source control.

Run existing Python/TS tests once; record differences against246/978 baseline without assuming counts cannot change. Read installed Next route/layout docs. Determine current test/start scripts from `package.json` and standalone runbook. No external sends/paid requests. Deliver build ledger and clean scope statement. Depends: none.

## T01: shared contracts and failure vocabulary

Create `concierge_service/chris/{__init__,contracts,settings}.py`, `src/lib/chris/contracts.ts` and shared synthetic JSON fixtures under `concierge_service/tests/fixtures/chris/contracts/`. Implement envelope parsing, unknown/duplicate-key rejection, UUID/time/money/size constraints, canonical digest and failure codes from03/05/06. Use UTF-8 byte limits consistently, not JS character count on one side and bytes on the other.

Acceptance: Python/TS accept/reject the same corpus, including non-finite/duplicate keys, Unicode, oversized bodies, invalid enum and foreign actor fields. Nothing sends. Depends:T00.

## T02: versioned persistence, blobs and idempotent commands

Create `chris/service.py`, `chris/blobs.py`; minimally integrate optional namespace with existing Store load/save and jobs. No DDL changes. Add account-local revision/event sequence, immutable command result ledger, blob atomic-write/hash verification and document capacity accounting. Ensure legacy Engine ignores new namespace without losing it on save.

Acceptance: restart round trip, rollback on failure, same-command replay, conflicting digest409, tenant isolation, unknown schema fail-closed, corruption and disk-full paths. Existing246 Python tests remain green. Depends:T01.

## T03: principal and provider identity

Create `chris/identity.py`; add strict Unipile normalization methods beside existing client without breaking legacy signatures. Implement connection generation, exact self/account binding, no shared provider account across tenants, principal nonce proof and distinct-three-identity checks. Add account registry validation across configured account mappings; collision disables both mappings until host fixes it.

Acceptance: principal nonce consumed once only in exact direct chat; stale/forwarded/forged nonce fails; wrong self/tenant/type/status disables writes; same assistant/principal rejected; duplicate person/profile/phone handled explicitly. No provider account creation required to complete software task. Depends:T02.

## T04: pure pursuit reducer and permissions

Create `chris/state.py` and `chris/permissions.py`. Implement transition table, orthogonal pauses, brief versions/research invalidation, owned pursuit registration, suppression, contact evidence and exact intro/group scope. Owner authority switch covers future actions only; untrusted paths cannot call it. Keep legacy core/calendar reducer unchanged.

Acceptance: state/property tests for all03 invariants; brief change never resets decline/follow-ups; wrong principal consent fails; toggling autonomy does not drain older drafts; absence of configured authorizer denies external action. Depends:T03.

## T05: persistent fair worker

Create `chris/scheduler.py`, integrate into `api.py` lifecycle behind explicit Chris initialization. Lease jobs in existing jobs table, reserve budgets atomically, bounded workers, account fairness, priorities, heartbeats, deadlines, cancellation and generation fencing. Persist future timers, do not rely on frontend visits or in-memory sleeps. Preserve legacy job execution and isolate namespaces.

Acceptance: kill/restart, delayed result fencing, stale brief result discard with charge retained, account A failure doesn't starve B, duplicate scheduler runs don't duplicate actions, storage pressure stops new work. Depends:T04.

## T06: standalone public research provider

Create `chris/search_provider.py`, bounded provider fixture transport, source retention and normalizer. Implement only documented Exa search/contents. Add host account configuration parsing without editing `.env` or deployment config. Existing Treg remains optional. Explicit per-operation allowances and price reservations; unknown cost never zero.

Acceptance: exact request-body/headers contract, inaccessible200 page, partial contents, rate limit, malformed/empty, redirect identity, private URL rejection, charge uncertainty and duplicate active request reuse. Offline network is intercepted; tests fail on unexpected live HTTP. Depends:T02,T05.

## T07: real Chris reasoning loop

Create `chris/agent.py`, `chris/research.py` and adapted prompt file. Extend existing model generation transport narrowly for typed step output while retaining legacy callers. Implement tool allowlist, task context truncation/provenance, broad query strategies, host registration, targeted reads, critic, dossiers and ordinal ranking. Persist tool run/evidence after each completed step.

Acceptance: six endeavour fixtures use search and read capabilities, no fake progress; relevant candidates with unknown reciprocal benefit survive; stale facts, same-name and injection cases fail appropriately; schema repair is bounded. Configured live models optional during build, fixture replay mandatory. Depends:T06,T04.

## T08: owned inbound replay and normalization

Create `chris/ingestion.py`, reuse v1 pagination/account primitives. Add principal/prospect/group routing, typed event normalization, complete-chat replay barrier, stable IDs, attendee-ID resolver, edits/deletes, manual-outbound/possible-echo separation and incremental watermarks. Poll independently of jobs/UI. Unowned malformed group cannot stop valid owned chat.

Acceptance: duplicate/out-of-order/multipage/STOP-at-final-page, source timestamp preservation, media, unknown schemas, group membership change, delayed self echo and tenant-bound speaker cases. No response enqueued before batch completion. Depends:T03,T05.

## T09: semantic conversation and permission interpreter

Implement04 classifier contract and05 evidence validator; route deterministic STOP/decline first. Track unanswered question IDs and conditions. Generate factual answers, short permission clarification, explicit defer, and bounded useful follow-ups. Principal control messages share service commands with narrow allowed scope; no autonomy expansion from WA.

Acceptance: all reply rows in02 and C-series08; exact combined question yes advances, generic yes does not; conditional/multilingual/quoted/reaction ambiguity never grants permission; independent prospects keep moving. Depends:T07,T08,T04.

## T10: frozen outbox and v1 wire encoder

Create `chris/dispatch.py`. Reuse proven freeze/claim/receipt concepts from reviewed_transport but keep new action schema separate from the legacy OS-compatible gate. Implement documented v1 multipart text-only requests, short DB dispatch boundary, external-authority injection and current-state checks. Persist started before wire. Introduce no unconditional authorizer.

Acceptance: byte-level multipart repeated recipients/Unicode/newlines; changed recipients/text/subject/revision denied; dispatch once across processes/restarts; STOP-before-start prevents call; timeout-after-start unknown; no writer lock held during HTTP; Meta helpers remain blocked in standalone. Depends:T04,T05,T08.

## T11: uncertain-action reconciliation

Implement read-only reconciliation by provider message ID or narrow correlated observation. Persist bounded retry schedule, ambiguous candidates and attention. Recover accepted responses/started claims after process death. Distinguish failed-before-dispatch from unknown. UI command cannot reset started action.

Acceptance: crash after provider mutation before local response, crash after acceptance before verification, delayed sync, matching old text, duplicate plausible groups, foreign sender/group and lost database write. No second mutation in any unknown case. Depends:T10.

## T12: introduction saga and true completion

Create `chris/introductions.py`. Wire qualified/permission-ready pursuits to exactly one saga. Neutral group-create message, exact three-identity membership verification, substantive introduction generation from approved evidence, fresh preflight, receipt and single completion event. Handle membership delay/privacy mismatch/withdrawal/extra member/leave without duplication.

Acceptance: full fixture completes only after substantive receipt; group-only case not counted; privacy restriction no auto-add or recreate; existing group recovered after crash; later departure retains truthful historical introduction. Depends:T09,T11.

## T13: private/public application API

Implement06 API routes, per-command roles, private bridge actor envelope, paginated reads, command status and granular readiness. Consume existing auth helpers; do not modify auth/RLS. Use short202 jobs. Bound errors, same-origin and account-owned IDs. Add exact private projection lookup/ack endpoints needed byT14: `GET /workspace/{account}/chris/projections/{id}`, `POST /workspace/{account}/chris/projections/{id}/ack` (digest+result only, authenticated).

Acceptance: role/IDOR/cross-origin/schema/body limit, expired session, duplicate command, projection error separated from successful command, live-readiness conjunction and heartbeat detection. Depends:T02,T04,T05.

## T14: automatic CRM projection

Create `chris/projection.py`, `src/lib/chris/projection.ts`, `/api/internal/chris/projection/route.ts`. Implement callback-as-wake, service payload/digest verification, existing service-client account scoping, deterministic contact/note/message writes and acknowledgements. Use existing account/phone/conversation/message constraints. Preserve contact tombstones and group-vs-direct distinction.

Acceptance: browser closed full completion still projects; callback tenant forgery fails; service-role client cannot cross-account write through adapter; crash-after-CRM-before-ack idempotent; missing index/config precise unready status; CRM downtime does not resend WhatsApp. No migration or secret editing. Depends:T12,T13.

## T15: onboarding, principal chat and settings

Implement pages/components in06. Onboarding parses/proposes/saves brief; dedicated number/nonce state; research and external autonomy separately explained; exact scope/limits; distinct principal; global geography when unspecified; explicit timezone. Console chat supports objective/status and all narrow principal controls even without live WA connection.

Acceptance: first-run no-config, simulation banner, active research without WhatsApp, safe drafts, conflicting tabs, switch future-only, pause, expired challenge/session, keyboard/mobile. No provider IDs or internal gate acronyms in ordinary flow. Depends:T13,T09.

## T16: people, conversations and introductions

Implement lists/detail, cited dossiers, known-relationship coverage, gaps, direct thread, participant-labelled group view, partial saga, attention/reconciliation and contextual WACRM links. Continuous polling when idle; monotonic revisions. Native composer routes to Chris action. Show exact claimed outcome and current operating status.

Acceptance: loading/empty/error/offline/stale, pagination,50-person list, long names/Unicode/URLs, uncertain send without Retry Send, human takeover/resume, opt-out, source injection escaped, partial CRM projection visible. Depends:T14,T15.

## T17: whole-system replay and crash harness

Create `concierge_service/tests/test_chris_e2e.py` and restart/race suites; TS route/integration fixtures. Replay from blank workspace through search/read/discovery/thesis/invitation/reply/group consent/group/create/intro/CRM. Destroy and recreate process objects at each external boundary. Verify wire call counts and persisted receipts, not only mock-called assertions.

Acceptance: all08 required IDs mapped to tests or explicit manual UI evidence; at least one two-account scenario, one two-worker race and one late STOP. A superficial deterministic stub that returns “introduced” without real host progression fails. Depends:T16.

## T18: full verification and browser QA

Run Python suite, npm tests, typecheck, lint and production build as declared in runbook. Start isolated simulation service/application using approved local port conventions or OS-assigned test ports; avoid canonical occupied services. Browser QA at390x844 and1440x900: first-run, active pipeline, ambiguous permission, partial group, verified intro, pause/offline. Save screenshots and route observations; fix issues before completion.

No live recipients, credentials or phone registration needed. Do not run a scripted UI happy path that activates real external sends. QA fixtures must live in simulation DB. Depends:T17.

## T19: operational completion and handoff

Implement redacted diagnostics, export, storage thresholds, stale worker/lease detection, account reconnect states and read-only live-preflight command. Document backup/restore, pausing, unknown action recovery, projection repair, missing-provider setup and failure boundaries. Update existing product runbook minimally to point at Chris. Provide `BUILD-RESULTS.md`, changed file map, verification results, test coverage matrix and external-only readiness gaps.

Commit scoped implementation in the isolated worktree, no forced push/merge/public deployment. Do not edit OS docs or the concurrent Fleet checkout to make the product work. A fresh coding session should finish all software work and leave activation off unless separate explicit live authorization already exists. Depends:T18.

## Task sequencing and scope controls

T06/T08/T13 have partly independent work after their dependencies, but no parallel writers may own the same files. Use subagents only if applicable session instructions permit; this plan does not require them. Keep central schemas/reducer/dispatcher under one integration owner. Do not split shared persistence semantics among concurrent editors without a stable contract.

Every discovered issue is handled in the same build if required for these journeys. Fix baseline regressions caused by the work. Pre-existing unrelated failures are recorded with reproduction; do not refactor unrelated code to inflate completeness. When an external constraint prevents real operation, implement the precise unavailable/recovery path and continue all independent tasks; never stop at “needs keys” before finishing the software.

## Explicit non-goals for this implementation

RevenueBase integration; Fleet runtime dependency; new number purchase/reseller; scraping authenticated LinkedIn sessions; sending through alternative channels; custom auth/roles/RLS; SQL migrations; billing/subscriptions; public signup; deployment changes; automatic calendar booking; negotiations; voice/video generation; general group moderation; shared assistant number across unrelated tenants; distributed multi-host worker; a generic agents/plugin platform. These are not hidden prerequisites for the specified three-person introduction product.
