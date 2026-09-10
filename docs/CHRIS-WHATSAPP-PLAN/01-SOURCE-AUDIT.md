# Verified source audit

## Provenance and verification boundary

Source read: `C:/wacrm-dogfood`, documentation HEAD `657ab22`, executable checkpoint `e4d0525`. The isolated plan worktree is `C:/wacrm-chris-plan-20260910`, branch `codex/chris-wa-plan-20260910`. Other WACRM worktrees and the concurrent Fleet session were left intact. Hashes in `source-manifest.json` are authoritative for the reviewed bytes; commit names alone do not capture concurrent local edits.

On 10 September 2026, the existing checkout passed:

```text
C:/wacrm-dogfood/.local/venv/Scripts/python.exe -m pytest concierge_service/tests -q -p no:cacheprovider
246 passed in 14.93s

npm test -- --run
97 test files passed; 978 tests passed; 6.48s
```

These are baseline tests, not proof the planned workflow exists. No production deployment, real phone ownership, provider account linkage, live WhatsApp dispatch, paid research, group membership or live model quality was verified. Historical acceptance documents were used for navigation only. A schema file existing is not proof that the schema is installed in a live database.

The OS system-map search for `whatsapp outreach concierge chris` identified `products/wa-outreach`, `apps/external/wa-apps`, and existing outreach components. The standalone executable was traced to the separate WACRM repository; it must not be added to the OS Git repository.

## Executable findings

Line numbers are landmarks at the manifest snapshot, not promises after implementation.

| Source | Observed behaviour | Consequence |
|---|---|---|
| `concierge_service/store.py:26` | WAL SQLite, `workspaces` JSON documents and unique account/job-key jobs; `BEGIN IMMEDIATE`; 15-second busy timeout. | Reuse persistence and transaction convention. Do not hold its writer lock over network calls. Bound document growth explicitly. |
| `concierge_service/engine.py:143` | Strict manually dispatched command allowlist; discovery, research, qualification, phone enrichment, invitation and introduction require separate commands. | This is useful machinery, not a continuous autonomous scout. Add a durable orchestration loop. |
| `engine.py:344` | Brief updates increment revision, cancel jobs and invalidate prospects. | Preserve stale-result fencing. Distinguish research-affecting changes from display-only preferences in the new workflow. |
| `engine.py:369` | Live invitation requires qualified prospect, operator-verified phone and contact scope. | Do not delete gates to make the demo advance. Add evidence-backed identity and permission ingress. |
| `engine.py:399`, `:419`, `:447` | Bound direct inbound and manual outbound; exact STOP/decline words; manual outbound triggers takeover. Equal timestamps are nudged. | Expand semantic handling without trusting model authority; preserve timestamps and add stable observed order instead of fabricating chronology. |
| `engine.py:939` | Leased jobs, model work outside transaction, budget reservations and stale-result checks exist. Job kinds are discover/research/research_phone/turn. | Extend this infrastructure; do not replace it with a process-local timer or a separate unpersisted agent loop. |
| `engine.py:1071` | Prospect deduplication uses profile or name/company. | Add account-scoped aliases and ambiguity handling; names alone are insufficient. |
| `concierge_service/research.py:9` | The assessor explicitly judges supplied evidence and has no public research tools. | Actual web search/read, retained sources, iterative questions and a critic must be implemented. |
| `providers.py:93` | Discovery is fixture or Treg people search, capped and single-page with a cursor warning. | Add open-web search strategy and explicit continuation. Avoid repeatedly charging for the identical exhausted query. |
| `providers.py:201` | Existing OpenAI-compatible/Anthropic transports generate one JSON response; no persistent Chris/tool loop. | Extend the existing transport with structured step contracts and bounded host execution. Do not assume Fleet's runtime is already present. |
| `enrichment.py:53` | Treg phone lookup retains hit/miss and cost metadata, rejects malformed phone/do-not-call cases; output remains unverified. | Keep it optional. A number returned by enrichment is neither ownership proof nor contact permission. |
| `providers.py:296` | Account verification checks exact ID and WHATSAPP type, not full connection lifecycle/owner identity. | Introduce account-owner binding and independently reported health capabilities. |
| `providers.py:303` | Cursor pagination has hard caps and cyclic-cursor rejection. | Preserve fail-closed completeness; a cap is an incomplete result, never the end of history. |
| `providers.py:335` | Attendee extraction excludes self. | Three-person verification must separately prove connected self plus exactly two external identities. |
| `providers.py:350` | Conversation parsing assumes particular sender IDs and textual message fields; retains raw messages. | Add normalized event types and an attendee-ID resolver. Handle media/system messages without corrupting the tenant's other threads. |
| `concierge_service/ingestion.py` | Sync validates account-wide history before mutation and matches known direct chats. Group/principal routes are not first-class. | Partition by owned chat, ingest complete batches with a replay barrier, persist cursors and add verified principal/group ownership. |
| `reviewed_transport.py:20`, `:57` | Action freezes identity/text/revision; persisted claim precedes mutation; response/membership/text are checked; uncertainty blocks replay. JSON POSTs currently create chats/send messages. | Preserve safety properties. Replace wire format with documented v1 multipart and separate group creation from substantive intro. |
| `live_execution.py:111`, `:183` | Preflight inspects overlapping historical threads; network work can occur under SQLite transaction. | Do not let an unrelated principal chat block every future candidate. Release DB locks during I/O and fence at dispatch. |
| `concierge_service/api.py` | Shared private bearer API; serial worker visits accounts; ordinary factory has no live authorization callbacks. Readiness combines message/calendar callback presence. | Add granular readiness, heartbeats and bounded fair task execution. Do not report live WhatsApp readiness because a calendar callback exists. |
| `concierge_service/host.py` | Explicit authorized host injection exists. | Keep product authority injection explicit. Do not install an always-allow callback or import the OS confirm gate into standalone runtime. |
| `concierge_service/concierge_core/state.py:266` | Core introduction already requires separate introduction/group permissions and a pending-reply check. Calendar stages are richer than the requested essential product. | Keep legacy tests and use a versioned new pursuit reducer rather than deleting old states. |
| `src/app/api/concierge/dogfood/route.ts:75` | Server derives account, enforces same origin and agent role, validates body; CRM copy follows browser POST. | Reuse boundaries, add command-specific authority rules and automatic projection independent of a browser. |
| `src/lib/concierge/dogfood.ts` | Strict command validation and private bridge; GET no-store; request timeout 30 seconds. | New long-running operations must return accepted jobs, not wait for web research/group recovery in a route. |
| `src/lib/auth/account.ts` | Existing owner/admin/agent/viewer roles resolved through authenticated profile and account-bound Supabase client. | Consume existing authentication and RLS; do not modify them for this build. |
| `src/lib/concierge/dogfood-reconcile.ts` | Account/phone-bound contact projection, idempotent outcome notes, direct-message mirroring. | Reuse its data ownership checks and create a durable projection queue. Group outcome remains a linked artifact, not a fake direct conversation. |
| `src/lib/concierge/inbox.ts` | Compound provider/chat/message IDs, duplicate-content checking, account-bound conversation; group messages skipped. | Preserve compound identity and truthful direction. Add group display in Chris view without misattributing group participants to a contact. |
| `src/lib/whatsapp/meta-api.ts:15` | Meta outbound helpers already refuse when `WACRM_BRIDGE_URL` is configured. Six send types have guard tests. | This protection already exists. Expand the standalone guard condition if needed and retain it across all callers; do not claim an unguarded second sender without checking. |
| `src/lib/whatsapp/send-message.ts:239` | Standalone native send path is blocked. | The normal Chris composer must route through Chris dispatch; do not reactivate native Meta sending. |
| `src/components/concierge/dogfood.tsx` | Operator-heavy forms; job-dependent polling can miss new idle inbound activity. | Build simple Chris pages and continuous bounded polling independent of current queue state. Preserve the advanced dogfood simulator. |
| `supabase/migrations/022_contact_phone_dedup.sql` | Defines partial unique account/normalized-phone index and duplicate merge. | Do not propose a missing uniqueness migration from old docs. Verify prerequisites read-only; never automatically execute this destructive historical migration. |
| `supabase/migrations/036_conversation_contact_dedup.sql`, `037_webhook_broadcast_reliability.sql` | Conversation and message idempotency conventions. | Reuse installed constraints when present; projection readiness must report incompatibility rather than silently merging live data. |

## Chris extraction and intentional adaptation

Reviewed source paths under `apps/internal/agent-fleet/resources/`:

- `company/agents/chris/AGENTS.md`
- `behaviours/connector-method.md`
- `knowledge/matching-method.md`
- `knowledge/introduction-orchestration.md`
- `knowledge/meeting-brief.md`
- `company/knowledge/people-dossier-format.md`
- `policies/connect/research.yaml`

The portable principles are: current economic objective governs relevance; broad discovery precedes expensive enrichment; multiple candidates progress; own only host-registered prospects and exact threads; retain dossiers; distinguish evidence/inference/interest; critic challenges weak claims without a rejection quota; reciprocal benefit is preferred, not mandatory; at most two useful unanswered follow-ups; respect declines and takeover; count host-verified introductions.

Intentional changes for this product: principal mandate replaces Fleet's per-candidate Patrick decision; WhatsApp replaces AgentMail; a verified group introduction replaces a joint email as completion; existing WACRM contacts and configured imports replace the private canonical OS roster; principal identity is dynamic; Fleet colleagues, meeting/diary duties and personal notebook access are removed. A strict first-degree exclusion option requires actual roster evidence, not a claim that WACRM contains every LinkedIn connection.

The actual Fleet research policy and `tools/agent-reach/agent_reach.py` were inspected. The implementation depends on OS environment paths, local tools and multiple external readers. Its research method is portable; copying the executable wholesale would violate standalone ownership. Exa supplies a concrete initial independent adapter. Browser-only or paywalled evidence remains a visible gap.

## Unknowns with a build-safe resolution

| Unknown | Resolution without asking the coding user |
|---|---|
| Concurrent Chris edits after the snapshot | Implement this captured behaviour; log a drift comparison once at build start. Do not auto-sync prompts at runtime. |
| Real number registration, recyclability, supported provider account | Implement pairing/status/error journeys with fixtures; leave live capability false until provider identity is observed. Never assume a purchased number works. |
| Actual Unipile v1 attendee/sender variants and group privacy failure payload | Strict normalizer + captured contract fixtures + unknown-schema quarantine. Live contract probe remains read-only until a separately authorized test exists. |
| Permission for first contact | Preserve unknown, keep research moving; accept only evidenced supported permission routes. |
| Model quality on realistic commercial briefs | Implement replay and qualitative evaluation corpus; report offline determinism separately from live model evaluation. No unapproved paid evaluation. |
| Existing Supabase indexes and projection authorization | Read-only prerequisite check under existing service access if available. Otherwise fixture verification and projection capability disabled with precise setup action. |
| Hosting scale and future public billing | Bounded single-host release. No cloud queue, new billing or public launch design disguised as a dependency. |

## Avoid these attractive but incorrect shortcuts

Do not equate a short persona prompt with Chris; copy Fleet runtime; bind the assistant to Patrick's number; infer opt-in from a scraped phone; treat “yes” without its exact question as group consent; count `ChatStarted` as a successful introduction; retry a timed-out create-chat; use identical text as the sole receipt correlation; validate history only after sending; run a network call with SQLite's writer lock; advance from partially replayed history; let the browser's presence drive CRM correctness; or flatten an uncertain external result into a generic retryable 503.
