# WhatsApp ingestion, consent, dispatch and recovery

## One provider generation, one identity boundary

Implement against the currently used Unipile v1 adapter. Normalize responses into a product contract at that boundary. Never let v2 field names leak into the reducer. Verify the configured account, connection status and self identity at startup, after reconnect and before write readiness. Provider ID or account-owner changes invalidate binding generation and all dependent queued actions.

The connected self must differ from principal and prospect. Verify all IDs, not display names. Canonical E.164 can generate a candidate `digits@s.whatsapp.net`, but only observed provider identity establishes the actual binding. Unknown alternate WhatsApp identity forms (including unresolved internal/LID forms) remain unresolved; do not manufacture a phone mapping by string substitution.

## Owned-thread ingestion

1. List configured account chats with complete cursor handling. Read enough metadata to classify ownership before parsing every message.
2. Owned direct chat: exact connected account plus sole external attendee mapped to a registered prospect or verified principal. A familiar name or chat subject is insufficient.
3. Owned group: exact persisted introduction group ID and saga, with verified participant mapping. Unowned groups are never supplied to Chris's model.
4. Load each owned chat independently. A malformed unowned conversation cannot stop all owned replies. An owned malformed chat is quarantined with a reason; other chats continue.
5. Persist the complete normalized batch and update the replay watermark atomically before scheduling any response derived from it. Never answer the first page while a later page contains STOP or a manual response.
6. Use provider message compound IDs for deduplication. Same ID with changed content is an edit/collision event requiring explicit handling, not a duplicate silently ignored. Keep provider time and observed time separately.
7. After the complete batch commits, run suppression/withdrawal/takeover first, then semantic reply classification and scheduling.

Polling is the required initial ingress:60-second normal account sync, explicit on-demand owned-thread refresh before any dispatch, bounded per-chat backfill. No public webhook endpoint or deploy configuration is required. A future authenticated webhook is a wake hint and still needs message/thread normalization; it cannot grant authority or bypass replay checks. Do not invent a webhook signature scheme from a provider that has not documented it.

Incremental sync retains an overlap window and stable message IDs. `all_history=true` only means requested pagination finished, not proof of the provider's full retention. Record `coverage_start, coverage_end, initial_sync_complete, truncated, cursor_status`. Live first contact needs trustworthy ownership/suppression records and sufficient existing direct-thread review; unknown/truncated relevant history disables dispatch. No account-wide “we read everything” assertion based solely on a20-page cap.

Normalize text, media, reaction, system/membership, edit, delete and unsupported events. A textless photo does not crash account sync. Consent-bearing edited/deleted messages lose prospective applicability until revalidated. A delayed old yes cannot override a later observed no. In contradictory or unordered messages, cessation wins until clarification. Future provider timestamps within60seconds are marked skewed; larger skew quarantines ordering-dependent actions without deleting evidence.

## Manual outbound and assistant echoes

Match outbound echoes first against persisted verified/accepted/started actions using exact account, chat, sender, provider ID when known, dispatch interval and payload. A known echo is not manual takeover. Unknown possible echo from an uncertain send enters reconciliation. Only sufficiently identified manual activity triggers takeover; ambiguous origin pauses that pursuit without labelling the principal as author.

A manual action can occur in the physical WhatsApp app without WACRM. Latest provider history is therefore necessary immediately before dispatch. After a manual reply, cancel queued bot drafts and stop bot follow-up until deliberate resume. Principal sent messages in a group may be context for that group; do not interpret them as instructions granting scope to every prospect.

## Consent evaluation algorithm

Contact eligibility is a separate pre-invitation requirement. It is never obtained retroactively by the first unsolicited commercial invitation. See provider/policy constraints.

For introduction/group permission, require all:

1. Exact registered recipient is the inbound speaker in the owned direct thread.
2. A verified outbound question names the exact principal. The group question identifies Chris and principal and explains number visibility.
3. The reply unambiguously answers that question, by reply-to reference or uncontested conversational context. If several pending questions exist, resolve context or ask again.
4. Meaning is affirmative without unresolved conditions/negation. “Yes, email me” does not authorize a WhatsApp group.
5. Evidence is real inbound text, not a quoted/forwarded fragment, reaction, model statement or manually inserted synthetic live record.
6. No later withdrawal, opt-out, identity correction, incompatible principal/brief change or expiration applies.

Principal consent comes from the active mandate and verified principal binding; no need to ask them for each candidate. Recipient permissions are bound to principal, pursuit, sender identity and relevant invitation, and expire after30days without group creation as an explicit product default. A newly changed substantive thesis needs revalidation; never assume consent to an unrelated endeavour.

When interest is clear but group scope missing, generate one concise clarification. When repeated ambiguity remains after two clarification attempts for the same question, pause that pursuit with evidence and continue research. Never badger the prospect with an automated interpretation loop.

## Frozen action and wire contract

Existing v1 reference documents multipart/form-data:

```text
POST /api/v1/chats
X-API-KEY: <host secret>
multipart fields:
  account_id=<configured Unipile account>
  attendees_ids=<first exact external provider ID>
  attendees_ids=<second exact external provider ID, groups only>
  subject=<frozen short group subject, groups only>
  text=<frozen text>

POST /api/v1/chats/{exact_chat_id}/messages
multipart fields:
  text=<frozen text>
```

Use repeated `attendees_ids` fields, not a JSON-encoded array string, comma-separated list or `attendees_ids[]` unless a verified contract explicitly requires it. Boundary is generated by the multipart serializer; do not manually hard-code Content-Type without its boundary. Implement a small bounded text-only encoder with byte-level tests or reuse a pinned existing dependency if available. Preserve Unicode and exact line breaks in the digest/payload.

For existing-chat sends, validate account association before using chat ID. Do not send an extra undocumented `account_id` field simply because the old wrapper did. For new-chat response expect v1 `object=ChatStarted`, `chat_id`, `message_id`; malformed/missing fields after dispatch mean unknown, not safe failure. New direct chat and group create are distinct action kinds with different participant counts.

No automatic retries on mutation HTTP timeout, connection reset after request started, 5xx or ambiguous response. A retryable business error requires proof of no remote mutation under the provider contract; default unknown otherwise. Read-only fetches can retry up to three times with exponential backoff and bounded jitter, respecting Retry-After. Do not rotate providers/accounts/numbers to evade restrictions.

## Introduction saga

States and durable next action:

| Saga state | Durable evidence | Allowed next action |
|---|---|---|
| `planned` | Frozen participants, current consent and substantive draft | Claim exactly one group-create action. |
| `creating_group` | `group_create` started claim | Await response or reconcile; never another create. |
| `group_create_unknown` | Started claim, response/error evidence | Read-only correlation of chats/messages; otherwise attention. |
| `group_created` | Exact chat/message IDs from provider | Verify chat and participants, including self. |
| `membership_pending` | Partial or not-yet-synced membership | Bounded read-only retries; no substantive message. |
| `membership_failed` | Missing/wrong/extra participant or privacy restriction | Stop saga; show exact issue; do not create another group or add unapproved people. |
| `group_verified` | Self + exact principal + exact prospect, current account | Recheck all current permissions; stage substantive message. |
| `introducing` | Substantive action started | Verify exact message or reconcile. |
| `introduction_unknown` | Ambiguous substantive result | Read-only message reconciliation, no resend. |
| `introduced` | Exact substantive message and membership receipt | Emit one completion event and one projection; stop proactive follow-ups. |
| `cancelled_after_create` | Withdrawal/takeover/identity change after group exists | No intro; preserve group history and truthful partial outcome. |

Use a neutral group-creation message: “I've created this group for the introduction you agreed to. I'll add the introduction shortly.” It contains no confidential thesis. Creation itself exposes group membership/phone numbers, so all applicable group consent must exist before this call, even though substantive content follows verification.

Verify membership immediately after create with bounded eventual-consistency reads (1,3,10,30,60 seconds scheduled durably, no sleeping HTTP request). Wrong or extra participant is an immediate failure; a temporarily missing expected participant may be pending until the bounded window expires. Do not delete/recreate or auto-add members in v1. The v2 documentation's warning that participant operations can succeed without changing membership reinforces the need for observation, but is not a v1 endpoint contract.

Verify connected self membership explicitly through chat/account and attendee evidence supported by the v1 schema. If v1 omits self from attendees, resolve connected account owner plus its observed group participation/read-only status through verified fields. If those fields cannot prove participation, mark membership unverified; do not pretend external attendee count alone proves three people.

Substantive message verification: exact account/chat, outbound authored by connected self, exact provider message ID, normalized-equivalent text under a tested provider normalization rule, dispatch window and current group membership. Do not strip arbitrary characters to make content match. Receipt means observed persisted message, not necessarily delivered/read by each person. UI wording must distinguish sent/observed from delivered/read metadata when actually available.

## Unknown-delivery reconciliation

Before every mutation, persist an action ID, full digest, exact thread/participants, prior message watermark, monotonic attempt generation and wall-clock dispatch time. After any accepted response, persist raw bounded response and IDs before further network verification. Reconciliation survives restart.

If message ID exists, retrieve that message and exact conversation, verify all identity/content constraints and record receipt. If response ID was lost, search only the owned direct chat or narrowly bounded candidate new groups created during the dispatch interval. Correlation requires account, exact members, self sender, dispatch window, text and absence of pre-existing matching message before the watermark. Group title/text alone is insufficient. More than one plausible result => `needs_attention`, no automatic choice.

If nothing is found, repeated absence is still not proof the request never executed: provider sync may be delayed or history incomplete. Read-only checks at10seconds,1minute,5 minutes,30 minutes and then attention. Background daily observation may resolve later; no second mutation is authorized by elapsed time. Expose a reconciliation UI with observed candidates and evidence. A human can explicitly abandon the local pursuit, but cannot mark it delivered without a verified receipt. A separate retry, if ever offered after externally proven non-execution, is a fresh action under current authority and an explicit recorded resolution, not a reset of `started`.

## Suppression and pauses

Global for the configured business sender/account: explicit no-contact, wrong number, verified platform block/restriction where known. Pursuit-scoped: no to this proposed introduction, condition/defer, manual takeover. A broad opt-out from one pursuit suppresses other briefs contacting that same resolved destination. Do not expose cross-tenant suppression membership or share private contact lists across tenants; each tenant has its own dedicated sender.

Emergency stop and external-autonomy disable are checked at claim and dispatch boundary. Ingestion, opt-out storage and uncertain-result reconciliation continue while paused. No new follow-up, group creation or principal summary can bypass pause just because it has a different purpose label. Administrative in-console status remains available without external writes.

## Provider account and group failure taxonomy

Persist stable codes and customer wording: `connection_unavailable`, `account_identity_changed`, `recipient_identity_unresolved`, `contact_permission_missing`, `group_permission_missing`, `history_incomplete`, `manual_takeover`, `recipient_restricted`, `membership_unverified`, `membership_mismatch`, `dispatch_unknown`, `content_mismatch`, `provider_schema_changed`, `rate_limited`, `storage_unavailable`, `authority_changed`.

Do not display raw secrets, hostnames containing credentials or full provider payloads in customer errors. Retain bounded redacted diagnostic evidence for the owner. A failure code belongs to an affected capability/entity; a single person's privacy settings do not mark the entire product broken.
