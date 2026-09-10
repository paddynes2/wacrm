# WACRM application, commands and projection

## Route and component map

Read installed `node_modules/next/dist/docs/` before editing Next code. This checkout is Next16.2.12 and dynamic route `params` are awaited. Use existing auth/dashboard layout and component styling conventions; do not replace the shell or authentication system.

New pages under existing dashboard route group:

```text
src/app/(dashboard)/chris/page.tsx
src/app/(dashboard)/chris/people/page.tsx
src/app/(dashboard)/chris/people/[personId]/page.tsx
src/app/(dashboard)/chris/introductions/page.tsx
src/app/(dashboard)/chris/introductions/[introductionId]/page.tsx
src/app/(dashboard)/chris/settings/page.tsx
```

Create focused components in `src/components/chris/`: `workspace.tsx`, `onboarding.tsx`, `brief-editor.tsx`, `principal-chat.tsx`, `people-list.tsx`, `person-detail.tsx`, `introduction-detail.tsx`, `attention.tsx`, `settings.tsx`, `status.tsx`. Reuse existing design primitives and responsive layout. Do not add a visual framework. Unit/component tests focus on actionable state and wrong-action prevention; visual checks cover layout.

Libraries in `src/lib/chris/`: `contracts.ts`, `bridge.ts`, `view.ts`, `commands.ts`, `projection.ts`, `queries.ts`. Centralize typed response parsing; never cast arbitrary service JSON into UI state and render success from a truthy field.

Existing standalone route aliases can link/redirect to `/chris` after compatibility tests. Keep `/dogfood` explicitly reachable for simulation and legacy workflow. Hide irrelevant Meta/broadcast/flow setup from the primary Chris navigation while preserving unrelated WACRM functionality. Low-level Meta send helpers must remain blocked when either standalone mode or the concierge bridge is configured. A Chris direct-message composer creates a host-reviewed `reply` action, not a call to `/api/whatsapp/send`.

## Public application API

```text
GET  /api/chris                         overview + revision + readiness
POST /api/chris/commands                validated command envelope
GET  /api/chris/people?cursor=&limit=    paginated compact list
GET  /api/chris/people/{id}             account-owned dossier/state/thread summary
GET  /api/chris/introductions?cursor=   paginated verified/partial outcomes
GET  /api/chris/introductions/{id}      exact group saga and participant-labelled thread
GET  /api/chris/activity?after=&limit=  account event feed
GET  /api/chris/commands/{id}           persisted command result
GET  /api/chris/export                  owner-only bounded export/download
```

Routes require existing authenticated account context; all responses `Cache-Control: private, no-store`. GET viewer; mutations as below. POST verifies same-origin and existing rate-limit conventions. IDs from another account produce404 without leaking existence. Do not cache tenant data in a global shared variable. All filters/cursors validated, sorted stable by observed sequence plus ID. `limit`1..100, default25. Cursor is an opaque account-bound position, not raw SQL or trusted tenant data.

Return consistent errors `{error:{code,message,retryable,entity_id?,current_revision?}}`; never send secret-bearing provider detail. `retryable=true` permits retrying a command/status/reconciliation, not replaying external mutations. UI labels the exact repair. Bound network calls; long work returns202.

## Command payloads and roles

All use common `schema_version,command_id,expected_revision,command,payload`. Unknown keys fail. The private service revalidates the schema and actor envelope from trusted WACRM server. No public route forwards an arbitrary legacy `command` string.

| Command | Payload | Minimum role / effect |
|---|---|---|
| `brief.propose` | `{text}` <=8000 | agent; creates proposal, never activates objective from model alone |
| `brief.save_proposal` | `{proposal_id,brief}` exact Brief input | owner; bounded explicit edit |
| `brief.activate` | `{proposal_id}` | owner; active research revision, future mandate scope |
| `research.start` | `{}` | agent; enqueues within owner allowance |
| `workspace.pause` | `{reason}` <=500 | agent; narrows work, immediate durable flag |
| `workspace.resume` | `{}` | owner; reevaluates, never enables disabled external autonomy |
| `autonomy.set` | `{enabled,scope_kinds,displayed_authority_revision}` | owner; standing future authority; cannot mutate host maximum ceilings |
| `settings.update` | validated subset of timezone, selected lower limits, research_enabled, principal_messages_enabled | owner; host maximum and known prices enforced |
| `principal.challenge` | `{}` | owner; generates one short-lived inbound-control nonce |
| `principal.unbind` | `{reason}` | owner; disables affected dispatch, no provider account deletion |
| `person.exclude` | `{person_id,reason}` | agent; explicit scope, cancels dependent work |
| `person.defer` | `{person_id,not_before,reason}` | agent; no assumption of renewed permission |
| `person.identity_attest` | `{person_id,phone_e164,evidence_refs,attestation_text}` | owner; provenance, not consent |
| `permission.record` | `{person_id,kind:'contact',source_ref,scope_text,granted_at,business_sender_identity,attestation_text}` | owner; explicit permitted basis; cannot supply a fake provider receipt |
| `permission.revoke` | `{permission_id,reason}` | agent; narrowing only |
| `pursuit.takeover` | `{pursuit_id,reason}` | agent; pause bot |
| `pursuit.resume` | `{pursuit_id,reviewed_thread_watermark}` | owner; latest thread must still match |
| `message.draft` | `{pursuit_id,text}` <=16000 | agent; draft at host-selected destination |
| `message.approve` | `{action_id,displayed_digest}` | owner; exact current action only, same dispatcher gates |
| `action.reconcile` | `{action_id}` | agent; read-only provider checks only |
| `action.cancel` | `{action_id,reason}` | agent; cancel unstarted, cannot retract started request |
| `projection.retry` | `{projection_id}` | agent; idempotent CRM work, no WA sends |
| `connection.refresh` | `{}` | agent; read-only lifecycle check |

Admin can view and narrow/pause as an agent; only the principal's owner role can expand authority or change principal identity in this release. Consume current roles without editing RLS/auth. If existing account has no valid owner/principal mapping, external capability remains unavailable and research can be explored in simulation. Do not invent a principal from the first returned admin.

`permission.record` does not expose intro/group consent entry in normal live UI: those derive from actual bound recipient replies. Imported historical intro/group permissions are out of scope unless an explicit exact evidence import is later specified. Legacy simulation consent controls remain simulation-only.

## Private service API

Add `/workspace/{account}/chris` read overview, `/workspace/{account}/chris/commands` POST and paginated entity reads alongside existing `/dogfood` endpoints. Continue constant-time bearer check. WACRM attaches server-derived actor user/role and request ID in a strict internal envelope. Product service trusts only this authenticated server boundary, not any inbound WhatsApp message claiming a role.

Do not expose this API publicly or install a no-auth debug route. A configured host is an existing secret/configuration input; code must not edit deployment files. If bridge configuration absent, UI renders a useful disconnected state and fixture tests still pass.

Granular readiness response:

```text
mode, schema_supported,
research: {configured,enabled,budget_remaining,reason_codes[]},
whatsapp: {configured,connected,account_bound,self_verified,history_ready,contract_verified,reason_codes[]},
principal: {named,number_bound,distinct_from_chris,reason_codes[]},
authority: {research_enabled,external_enabled,paused,revision},
projection: {configured,prerequisites_verified,pending,oldest_pending_at,reason_codes[]},
worker: {running,last_heartbeat_at,oldest_ready_job_at,lag_seconds},
storage: {healthy,document_bytes,research_paused,outbound_paused},
live_acceptance: {verified:false|true,evidence_ref|null}
```

A research provider configured does not imply WhatsApp works. A working token does not imply number ownership. A running web process does not imply a healthy worker. `live_acceptance` can only derive from a separately recorded accepted live test, not from callbacks being present.

## Principal conversation

Console chat and verified principal WA thread feed the same brief-proposal/status service. Only console owner actions can expand authority. In WA, `pause`, `stop research` and `stop messaging` narrow scopes according to exact authenticated principal binding. Model interpretation creates a structured proposal; host validates scope and version. Ambiguous principal messages do not silently modify active objective. Quoted/forwarded control text never executes.

A request for status produces a concise persisted-state answer with relevant names, reasons, actual outcomes and concrete missing dependencies. It must not say “I messaged” for a draft or “you are connected” for a partial group saga. In-console chat supports full operation when principal WhatsApp messaging is unavailable.

## WACRM projection without an open browser

The Python service commits projection outbox entries in the same transaction as source events. Its scheduler POSTs bounded batches to a private WACRM route `/api/internal/chris/projection`; no browser poll is required for correctness. Host config supplies WACRM private base URL; if absent, entries remain pending. No new secret is generated or written during build. Authenticate with the existing private bridge token using constant-time comparison, reject oversized/unknown fields, and bind every payload to the account validated by the service. This route is not callable by the model or ordinary browser.

Callback body is exactly `{schema_version:1,account_id,projection_ids:[UUID...]}` with at most50 IDs and32KiB UTF-8. The host-configured URL permits HTTP only on loopback for local operation; remote use requires HTTPS and a fixed trusted origin. No query, fragment, embedded credential or caller-provided target is accepted. Never follow redirects carrying the bearer token. Both directions use bounded deadlines and no-store responses.

Server uses the existing Supabase service client pattern (`src/lib/automations/admin-client.ts` exports `supabaseAdmin`) without changing credentials or RLS. Keep account ownership checks explicit because a service client bypasses RLS. Before writes, resolve the exact account and active principal user mapping from existing profiles, verify every contact/conversation account relationship, and reject any foreign IDs. Never accept an arbitrary `user_id` from a provider or model as an author. The trusted private route receives only normalized projection facts, no arbitrary table names, SQL, role changes or send instructions.

Projection source verification: WACRM fetches the exact immutable projection payload by ID from the private service and compares digest/account before writing. The incoming callback is only a wake/batch-ID request, not unquestioned authority to insert supplied message content. This prevents generic internal callback payloads becoming a second truth source.

Contact creation: only qualified research with resolved contact identity; deterministic account/person ID pattern follows current dogfood promotion. Prefer existing account/phone match after explicit identity validation. Shared/ambiguous phone collisions remain unresolved; do not merge by name or overwrite contact ownership. Reuse unique-violation/read-existing handling and existing indexes. Suppressed/deleted contacts do not auto-recreate.

Dossier notes: deterministic source-version ID, concise why-this-person and product-local dossier link. Direct messages: preserve compound provider/chat/message ID, observed timestamps and correct speaker; only verified/observed messages enter inbox, never drafts or unknown sends. Same ID/different body is collision/edition attention, not blind overwrite.

Group: create a single deterministic introduction note on the prospect contact linking to the Chris group view. The group view reads participant-labelled normalized events from execution storage. Do not store principal/group text as if the prospect sent it in a one-to-one conversation. Outcome note says verified introduction date and actual observed evidence; delivered/read remains distinct.

Acknowledgement is persisted only after each deterministic projection succeeds. Crash after Supabase commit but before ack replays the same IDs and reads existing matching rows. Projection failure never rolls back a verified WhatsApp outcome or re-executes an external action. Retry read/CRM writes with bounded backoff and surface oldest pending age.

Existing SQL prerequisites are checked read-only if host access exists; otherwise readiness says unverified. Never execute historical dedup migrations, new SQL or auth changes to force the build green. Integration tests use a faithful fake or isolated existing test database with installed schema. Production schema repair belongs to separately authorized host work.

## Polling and interaction correctness

Overview/activity poll every5seconds while page visible,15 seconds when hidden, exponential retry up to60seconds on failure. Continue idle polling even with no queued jobs. Cancel fetches on unmount/account switch. Merge only nondecreasing server revisions; late responses must not regress the UI. Authentication expiration stops requests and preserves safe local drafts for reauthentication, not optimistic successful state.

Command IDs are generated once per user intent and reused on transport retry. Disable double submits, but idempotency must work even if the UI fails. On unknown POST result, query command ID before offering another action. On409 revision conflict, show latest state and preserve edited text; no silent stale overwrite. Pending action text/recipient/digest shown together where review is applicable.

Deep links are account-scoped and safe. External research URLs open with appropriate link isolation, no executable `javascript:`/data URLs. Render Markdown using existing safe renderer or escaped plain text; no raw model HTML. Accessible status chips use text as well as colour. Mobile cards show the primary reason and state without horizontal scrolling; details expand.
