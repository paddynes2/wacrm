# Contracts, persistence and state

## Ownership and module boundaries

WACRM owns authenticated accounts, principals' application roles, canonical contacts, contact notes and ordinary inbox projection. The Python service owns Chris's brief revisions, research, permissions as evidence, pursuit state, jobs, action outbox and provider receipts. Models own no authoritative state. The browser requests commands and displays projections; it cannot declare a message sent or supply its tenant identity.

Keep existing `workspaces` and `jobs` SQLite tables. Add an optional `chris_v1` object to the existing workspace JSON; initialize lazily inside the existing transaction. Do not run new SQL migrations, change legacy document keys or alter `concierge_core/state.py` semantics. Legacy jobs and Chris jobs use different namespaced keys. New handler refuses an unknown future schema version with `upgrade_required` and no mutations.

New files under `concierge_service/chris/`:

| File | Responsibility |
|---|---|
| `contracts.py` | Closed command/event/action schemas; canonical encoding, bounds, enum validation. |
| `state.py` | Pure reducer and eligibility predicates; no network or clocks read implicitly. |
| `service.py` | Account-scoped command transactions, report/view assembly, existing-store integration. |
| `scheduler.py` | Durable jobs, leases, fences, priorities, retry classification, fairness. |
| `agent.py` | Structured reasoning turns and tool loop, schema validation and critique. |
| `research.py` | Public discovery strategy, source retention, evidence checks and dossiers. |
| `search_provider.py` | Exa adapter with narrow request allowlist and bounded normalized outputs. |
| `identity.py` | Provider/self/principal/prospect bindings, aliases, duplicate and consent-subject checks. |
| `permissions.py` | Host-owned authority, contact/introduction/group evidence and revocation. |
| `ingestion.py` | Owned-chat sync, event normalization, replay barrier and principal routing. |
| `dispatch.py` | Frozen outbox actions, short-transaction dispatch boundary, verification and reconciliation. |
| `introductions.py` | Durable group-create/verify/intro-send/verify saga. |
| `projection.py` | Durable WACRM outbox, acknowledgements, redacted operational metrics. |
| `blobs.py` | Content-addressed retained source/dossier/transcript blobs under explicit data root. |
| `settings.py` | Validated defaults, per-account effective limits and granular readiness. |

These are responsibility boundaries, not a requirement to create empty abstractions. Implement real methods as their tasks arrive; no generic plugin framework or duplicate ORM.

## Encoding and identifiers

Use UUIDv4 for internal entity IDs and command IDs; UTC RFC3339 timestamps with explicit offset at ingress, normalized to UTC for storage. Keep original provider timestamp and provider ID verbatim in evidence. `observed_seq` is an account-local monotonic integer allocated inside the transaction; it orders observation/processing, not a fabricated provider chronology. Money uses integer micro-USD, never floating point. Durations and caps use named validated integer constants.

Provider message identity is `(provider_name, connection_generation, account_id, chat_id, provider_message_id)`. Attendee IDs and WhatsApp provider IDs occupy distinct typed fields. Never compare them without a resolved mapping. Canonical JSON is UTF-8, sorted keys, no non-finite numbers, duplicate JSON keys rejected, explicit allowlist, no `default=str`. SHA-256 protects immutable action/evidence content. No canonicalized action may omit recipient, text, group subject or relevant revision.

Data root is derived from the explicit absolute `CONCIERGE_DB_PATH` parent under `chris-blobs/`; never from an arbitrary user/model path. Blob name is only a validated lowercase SHA-256. Write bounded content to a same-directory temporary file, flush, atomically replace by hash, then commit its reference. A crash before DB commit can leave an unreachable blob, not a false state event. Hash mismatch is corruption and blocks dependent actions. No automatic garbage collection/deletion during the first build.

## Workspace shape

```text
chris_v1 = {
 schema_version: 1, revision: int, event_seq: int,
 created_at, mode: simulation|live,
 brief_versions: {brief_revision: Brief}, active_brief_revision: int|null,
 principal: PrincipalBinding|null, connection: ConnectionBinding|null,
 authority: Authority, settings: Settings,
 people: {person_id: Person}, identity_aliases: {typed_alias: [person_id]},
 pursuits: {pursuit_id: Pursuit}, threads: {thread_key: Thread},
 permissions: {permission_id: Permission}, suppressions: {identity_key: Suppression},
 actions: {action_id: Action}, introductions: {intro_id: Introduction},
 commands: {command_id: CommandResult}, tool_runs: {tool_run_id: ToolRun},
 projection_outbox: {projection_id: Projection},
 events: [Event], health: Health, storage: StorageAccounting
}
```

All account lookups begin with existing validated tenant UUID. No top-level mutable “current account” global. Do not return source bodies, tokens or all transcripts in the overview response. Separate paginated views and entity detail.

### Brief

`revision, objective (1..4000 chars), principal_public_context (0..4000), principal_display_name (1..120), candidate_archetypes (0..12 strings, each <=300), geography_include/exclude (0..50), explicit_exclusions (typed person/domain/organization/free-text), approved_claims (id,text,evidence_ref,public:boolean), confidentiality_rules, known_relationship_policy, timezone (valid IANA), created_by, created_at, source_command_id, content_digest`.

No objective => no discovery. Absence of archetypes/geography is not an error: Chris derives useful search strategies without silently saving inferred restrictions. `approved_claims` must distinguish principal-attested public statements from externally verified facts. A principal can attest their own offer, not a prospect's interest. Presentation changes do not require requalifying everyone; changes to objective, targeting, exclusions, claims or principal identity do. Revision remains monotonic for every save; store a separate `research_revision` for relevance invalidation.

### Person and dossier

`person_id, display_name, company_name, company_domain, roles[], canonical_profile_urls[], identity_evidence_refs[], phone_candidates[], preferred_language, timezone_evidence, known_relationship_check, source_registration, dossier_ref, dossier_version, created_at, updated_at`.

Every phone candidate: `e164, normalized_provider_id|null, provenance_refs[], verification_status (unverified|corroborated|operator_attested|invalid|ambiguous), verified_at|null, expires_at|null, do_not_contact, reason`. All evidence ages are explicit. E.164 syntax validation does not verify ownership. Use a maintained parser already available if present; otherwise add a narrowly pinned library only after checking package availability and license. Do not invent country codes for national-format numbers.

Dossier is an immutable versioned JSON blob with concise rendered Markdown: `brief_research_revision, objective, why_this_person, principal_benefit, possible_recipient_benefit, why_now_or_enduring_reason, facts[{claim_id,text,source_ids,verified_at}], inferences[{text,basis_claim_ids}], unknowns[], risks[], approach_thesis, critic{verdict,reasons,required_fixes}, next_research_questions[]`. It contains no authoritative send stage, consent or outcome.

### Pursuit

`pursuit_id, person_id, origin_brief_revision, current_research_revision, state, state_revision, owner='chris', registered_source_id, qualification (pending|qualified|rejected|unresolved), reason_codes[], direct_thread_key|null, active_invitation_action_id|null, introduction_id|null, followup_count_verified, last_verified_outbound_at, last_inbound_seq, reply_required, human_takeover, not_before, closed_reason, updated_at`.

One active pursuit per resolved person per account. New briefs update/requalify that pursuit, never reset suppression, permission, lifetime unanswered follow-up counts or external action identity. Rejected research may be reconsidered on material new evidence, with reason. Explicit decline and opt-out require their own new applicable permission, not a fresh model verdict.

### Thread and event

Thread: `thread_key, kind (principal_direct|prospect_direct|introduction_group), provider_chat_id, provider_account_id, connection_generation, owner_entity_id, expected_participants[], participant_snapshot_ref, history_coverage, sync_state, last_complete_sync_at, last_observed_seq, replay_generation, normalized_event_refs[], latest_inbound_ref, latest_outbound_ref, manual_activity_ref|null`.

Event: `event_id, kind, actor_kind (principal|prospect|host|provider|model_proposal), actor_id, entity_id, observed_seq, occurred_at, received_at, source_ref, payload, schema_version`. Semantic decisions point to exact event IDs. Preserve edits/revocations as new events, not destructive edits of historical evidence. System events, reactions, media, deleted messages and text are distinct kinds.

### Permissions and authority

Permission: `permission_id, kind (contact|introduction|group|principal_communication), subject_provider_id, business_sender_identity, principal_id|null, pursuit_id|null, invitation_action_id|null, thread_key|null, evidence_event_ids[], evidence_spans[], scope_text, granted_at, expires_at|null, revoked_at|null, basis (verified_inbound|imported_record|operator_attestation), classifier_version|null, status (valid|pending|ambiguous|revoked|expired)`.

Authority: `revision, research_enabled, external_enabled, principal_messages_enabled, enabled_by_user_id, enabled_at, future_actions_from, allowed_action_kinds[], brief_revision, principal_binding_revision, connection_generation, limits_snapshot, paused, emergency_stop, reason`.

Authority records can only be written by authenticated commands with server-derived role or host configuration. Model/inbound prospects cannot write them. Verified principal WA commands may narrow/pause authority, never expand spending or switch on external autonomy. Consent is evidence-dependent and person-specific; permission IDs are references, not booleans asserted by a prompt.

### Action

`action_id, kind (invite|reply|permission_clarification|followup|group_create|group_introduction|principal_reply), pursuit_id|null, intro_id|null, created_at, status, frozen, digest, dispatch_generation, lease_owner, lease_until, budget_reservation_id, started_at|null, provider_response_ref|null, verification_refs[], last_error_code, next_reconcile_at, attempts`.

`frozen` includes `account_id, connection_generation, provider_account_id, self_provider_id, principal_binding_revision, principal_provider_id where relevant, recipients[], chat_id|null, group_subject|null, text, purpose, brief_revision, research_revision, pursuit_revision, authority_revision, permission_ids[], source_claim_ids[], history_watermark, not_before, expires_at`.

Status: `draft -> queued -> preflight -> started -> provider_accepted -> verified`. Alternatives: `cancelled`, `denied`, `failed_before_dispatch`, `unknown`, `reconciling`, `needs_attention`. `started` is persisted before the wire and never transitions back to queued. `provider_accepted` is not verified. Frozen content is immutable: changed text or recipients means a new action after cancelling the old unstarted one.

### Introduction

`intro_id, pursuit_id, principal_binding_revision, principal_id, prospect_id, expected_self_and_participants[3], consent_ids[], state, group_create_action_id, group_chat_id|null, participant_verification_ref|null, substantive_action_id|null, completion_event_id|null, created_at, verified_at|null, last_failure`.

One introduction for this pursuit/principal pairing. A database claim and semantic key prevent parallel creation. Group subject uses short first names plus “Introduction”, maximum 80 characters, no sensitive thesis or opportunity details. Duplicate subjects are legal; subject is never identity.

### Tool run and projection

ToolRun: `run_id, pursuit_id|null, tool_name, input_digest, normalized_input, status, lease/fence, cost_reservation_micro_usd, operation_allowance_reserved, provider_request_id|null, estimated_cost_micro_usd|null, reported_cost_micro_usd|null, output_ref|null, error_class, started_at, completed_at`. Unknown charge retains reservation. Same active input returns existing run. Completed lookup reuse follows explicit freshness, not repeated spending.

Projection: `projection_id, account_id, entity_id, source_event_id, payload_digest, kind (contact|dossier_note|direct_messages|introduction_note|tombstone), payload, status, attempts, next_attempt_at, acknowledged_at, last_error`. Projection IDs derive from immutable source event IDs. A failed CRM write cannot trigger a WhatsApp resend. A deleted/opted-out contact tombstone prevents automatic recreation.

## Command envelope

```json
{
  "schema_version": 1,
  "command_id": "UUID",
  "expected_revision": 7,
  "command": "brief.activate",
  "payload": {"proposal_id": "UUID"}
}
```

HTTP boundary rejects unknown keys, duplicate JSON keys, oversized UTF-8 body (>32 KiB), invalid UUID, non-integer revision, invalid dates/enums and control characters. Server derives `actor_user_id, actor_role, account_id`; they are not accepted in browser payloads. Private bridge attaches an authenticated actor envelope based on the existing server session, not model text.

Same `(account, command_id)` and same canonical command returns stored status/result. Same ID/different digest returns 409 `idempotency_conflict`. Revision mismatch returns 409 `revision_conflict` with safe current revision, not automatic overwrite. Long work returns 202 with entity/job IDs in under two seconds; status polling reads persisted state. Successful command whose projection is delayed remains successful with a separate projection warning.

Command allowlist and role matrix are in `06-WACRM-UI-AND-API.md`. Event and command schemas are tested against a shared JSON fixture corpus in Python and TypeScript. Generate type declarations if useful; do not maintain unrelated permissive schema versions.

## Pursuit reducer

| State | Entry requirement | Next allowed progression |
|---|---|---|
| `discovered` | Host-registered retained public discovery source | `researching`, `excluded` |
| `researching` | Budgeted owned research job | `qualified`, `rejected`, `research_blocked` |
| `qualified` | Critic accepted relevance at current research revision | `contact_unresolved`, `ready_to_invite`, `excluded` |
| `contact_unresolved` | Identity, contact permission or relationship check unresolved | research/permission evidence; then `ready_to_invite` |
| `ready_to_invite` | All host checks currently pass | queued action; no “approached” until verified |
| `awaiting_reply` | Verified invitation or follow-up | reply, permitted follow-up, `closed_no_response` |
| `conversing` | Unanswered verified inbound in owned direct thread | reply or permission clarification; no unrelated follow-up |
| `awaiting_group_permission` | Introduction interest but group scope missing | clarification or `ready_to_introduce` |
| `ready_to_introduce` | Current principal mandate + exact recipient intro/group permission | introduction saga |
| `introducing` | Group saga claimed | `introduced`, `recovery_needed`, `paused` |
| `introduced` | Verified substantive message in exact group | historical outcome; scoped reactive clarification only |
| `deferred` | Explicit bounded defer instruction | re-evaluate at due time, do not resurrect invalid permissions |
| `human_takeover` | Verified manual activity or explicit principal takeover | explicit reviewed resume; no automatic reply |
| `declined` / `suppressed` / `excluded` | Applicable stop condition | no dispatch; only separately evidenced valid resolution |
| `research_blocked` / `recovery_needed` | Specific dependency failure | targeted repair, independent prospects proceed |

Pause is an orthogonal account/pursuit flag, not a destructive loss of the underlying state. Persist concrete reasons rather than one generic “blocked” bucket. Pure reducer refuses illegal events and duplicate outcome creation. Presentation counts derive from verified state.

## Concurrency and dispatch boundary

Reuse existing jobs table with kind `chris.<kind>` and keys including account, entity, operation, relevant revision and planned generation. `BEGIN IMMEDIATE` transactions are short and contain no HTTP/model/FS source-reading work. Claim due jobs with a lease and fencing generation in the document; any result must compare the exact generation and current revisions before commit.

Default scheduler: two-second tick, four bounded I/O workers overall, maximum one outbound mutation in flight per account, two read-only jobs per account, round-robin tenant selection. Leases last 120 seconds and can heartbeat every 20 seconds; external call deadline is at most 45 seconds for read/model and 30 seconds for mutation. Do not reclaim a started external action into a second send when its lease expires; schedule reconciliation only. A delayed worker cannot commit after a newer generation takes over.

Priorities: suppression/ingestion, uncertain-action reconciliation, principal controls, pending prospect replies, finishing permitted introductions, due meaningful follow-up, shortlist research, new discovery, nonurgent projection/backfill. Prevent starvation with weighted round-robin and oldest-ready age; every ten non-research jobs allow one eligible research job when there is capacity. Absolute STOP/identity/authority gates still precede all dispatch.

Before network mutation: refresh owned thread outside transaction; acquire transaction; re-read authority, suppression, permission, identity, latest inbound, lease generation and complete-sync watermark; persist `started`; commit; invoke exactly once. Pause/STOP committed before `started` prevents dispatch. A STOP that arrives after `started` can race with the remote request; no implementation can recall bytes already sent. Record this explicitly and stop subsequent actions. Do not claim a distributed atomic transaction with WhatsApp.

## Resource defaults and persistence limits

Chosen initial single-host bounds: 500 nonarchived research candidates per account, 20 new candidate registrations per discovery pass, 100 rows per list page, 20,000 normalized message events and 16 MiB serialized workspace document. Source text is stored in bounded blobs (20,000 characters each), not duplicated into every model prompt or workspace event. Messages larger than 16,000 characters are stored truncated for display with original bounded blob reference and `truncated=true`; truncation cannot grant consent.

At 8 MiB document size pause new discovery and surface storage attention; at 12 MiB pause new outbound and new research, reserve the remaining capacity for in-flight receipts/STOP/reconciliation. At the hard limit refuse new work and report unhealthy durable storage; never acknowledge inbound as persisted if it is not. Startup disk write failure disables dispatch. Export/host capacity adjustment is an explicit operational action; do not silently prune consent, suppression or started-action evidence to make space. These are transparent first-release capacity limits, not claims of unlimited SaaS scale.

No process-local object is sufficient to prove authority, idempotency, charges or receipts. Crash tests must destroy/recreate the Engine/Service instance and reopen the database, not merely call the same in-memory object twice.
