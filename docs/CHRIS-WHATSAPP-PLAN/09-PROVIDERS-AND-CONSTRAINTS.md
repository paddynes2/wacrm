# Provider contracts, constraints and unknowns

Research date:10 September 2026. Sources below were opened and read through BrowserOS neo. They establish documented interfaces and constraints, not successful operation of a particular customer account. Never infer a live capability from a documentation example.

## Unipile v1 is the selected implementation contract

The existing source uses `https://{assigned-host}.unipile.com:{port}/api/v1`. Preserve host allowlisting and the assigned port. Keys stay server-side in account-bound configuration; do not expose them to the model or browser. The current client uses `X-API-KEY` and verifies account/type. The new adapter must additionally validate connection lifecycle and observed owner identity.

The v1 [Send messages guide](https://developer.unipile.com/docs/send-messages) documents creating direct/group chats through `/chats` and sending into known chats through `/chats/{chat_id}/messages`. Its examples use multipart form data. The [Start a new chat reference](https://developer.unipile.com/reference/chatscontroller_startnewchat) names `account_id`, `attendees_ids`, optional `text` and `subject`, and a `ChatStarted` response with chat/message IDs. Use the reference's `subject` field; the guide's prose also says “title,” so do not send an invented `title` parameter.

The guide supplies multiple WhatsApp attendee IDs as repeated form fields. It describes provider-native IDs, including phone-based WhatsApp IDs. A UI display name or Unipile internal attendee row ID is not interchangeable with that identifier. Existing chat sending should use the observed chat ID to avoid inadvertently creating a parallel direct chat.

Although the reference does not mark `text` required, its returned shape includes a starting message ID. This plan does **not** claim blank-text group creation works. The chosen neutral setup message resolves that uncertainty without disclosing the substantive thesis before membership verification. Group membership/number exposure still occurs at group creation, so consent is required before it.

Contract-test artifacts to create under `concierge_service/tests/fixtures/chris/unipile-v1/`:

```text
account_healthy.json / account_disconnected.json / account_wrong_owner.json
direct_chat.json / group_chat.json / group_read_only.json
attendees_with_self.json / attendees_external_only.json / attendees_internal_sender_ids.json
messages_text.json / messages_media_system.json / messages_edits.json
chat_started.json / message_created.json / malformed_success.json
privacy_restriction.json / delayed_membership.json / rate_limited.json
```

Synthetic contract fixtures must be labelled synthetic. Do not invent a provider field and call it a captured response. Exact wire schema for optional status/self/group metadata is verified against available v1 reference or actual read-only account observations at build time. Until a normalizer has proof of a field mapping, it rejects that unsupported variant and readiness states `provider_schema_changed`/`membership_unverified`. This is a fully implemented failure path, not permission to fake successful group membership.

## Do not mix Unipile v2 into v1

The currently published [v2 WhatsApp group guide](https://developer.unipile.com/v2.0/docs/manage-groups) uses different account-path APIs and SDK shapes. It documents participant operations, owner exit and read-only groups. It also warns that member additions/removals may return success without changing membership when the required group permissions are absent. This supports the product's independent verification requirement; it does not prove a corresponding v1 member-management endpoint exists.

This release does not implement automatic add/remove/exit group operations. If v1 is unavailable for the actual provider account, leave the v1 capability disabled and document the contract mismatch. Do not silently auto-upgrade all account IDs, paths, token shapes and payloads to v2. Implementing a full v2 adapter is a separate scope decision, not a fallback assembled from mixed examples. Offline implementation and all unavailable-state journeys must still be completed.

## Linking a WhatsApp account

The [Unipile v1 WhatsApp connection guide](https://developer.unipile.com/docs/whatsapp) documents QR and pairing-code flows, including a digits-only international pairing number parameter. Registration of the underlying WhatsApp number and linking it to Unipile are separate external steps. Neither establishes the separate principal's identity or permission to contact a prospect.

The existing product experiment mentions a fresh Wabi number on regular WhatsApp. This plan does not establish Wabi inventory, number suitability, OTP delivery, WhatsApp acceptance, portability, ownership duration or account health. No purchase is necessary to implement/test the product. If a real number is already configured, inspect its state without changing it; otherwise the account-linking UI remains an honest guided unavailable state. Never purchase/register/link an arbitrary number autonomously during the coding session.

## WhatsApp contact and automation constraints

WhatsApp's [Business Messaging Policy](https://whatsappbusiness.com/policy/) requires a recipient-provided number and permission for subsequent contact, and requires opt-outs to be respected. The policy applies to its Business App and Platform. Therefore a scraped/enriched phone number alone is not sufficient contact eligibility for the business outreach journey.

The [WhatsApp Messaging Guidelines](https://www.whatsapp.com/legal/messaging-guidelines) also cover regular Messenger, one-to-one chats and groups, addressing unwanted contact and harmful automated/adversarial activity. This review does not establish that using regular WhatsApp with Unipile exempts this commercial product from platform restrictions. Do not present a regular account, a small daily cap or a provider connection as a guarantee against account restriction.

The business-platform template/window rules are not automatically the wire protocol of the selected linked-account v1 adapter. Do not bolt Meta templates onto Unipile or claim that a different transport removes permission obligations. Existing Meta outbound remains disabled for Chris.

Implementation consequence: retain a distinct contact-permission evidence requirement before an invitation. Support prospect-initiated inbound contact and documented existing opt-ins. Research-only candidates with unknown permission remain useful pipeline entries. Report this material gap honestly when evaluating the business; do not conceal it behind a fabricated boolean or automatic cold message whose purpose is to ask for permission.

Applicable privacy/direct-marketing obligations vary with sender, recipient, geography and processing. This plan does not supply a legal determination or assert one global lawful basis. Store the host-configured contact-policy version and basis evidence; unknown applicable basis prevents the affected initial contact. The product's engineering can be built without pretending that every jurisdiction has been cleared. Do not use the model as legal authorization.

## Standalone public research: Exa

The [Exa Search reference](https://exa.ai/docs/reference/search) documents JSON `POST https://api.exa.ai/search`, key authentication, bounded result counts and optional content retrieval. The [Contents reference](https://exa.ai/docs/reference/get-contents) documents `POST /contents` with either `ids` or `urls`, not both. It distinguishes crawl freshness from publication date, deprecates `livecrawl` in favour of `maxAgeHours`, and describes returned cost figures as estimates rather than the billing source of truth.

Use minimal requests from04. Keep search/read functionality separated from synthetic model-generated summaries; evidence comes from retained extracted text and source metadata. Preserve estimated costs as estimated. Provider availability/configured allowance is an external input, not an excuse to return a fake research success.

Live configuration adds a validated Exa entry to account-specific provider configuration through the existing host configuration mechanism. No `.env` file or secret is edited by the builder. If no Exa credential/allowance exists, all fixture replay and UI still work, live research reports unavailable and no paid fallback provider is secretly selected.

## Existing Treg enrichment and model transports

Executable Treg contract was read in `concierge_service/enrichment.py` and `providers.py`. Preserve its strict input filters, explicit account-specific key, route cap and retained result metadata. Do not infer phone ownership, WhatsApp availability or consent from a hit. Provider errors/ignored filters/do-not-call flags remain meaningful.

Model provider choice remains the account's explicit existing configuration. The plan uses a strict JSON step protocol over existing transports, not a new undocumented SDK or product API. Model name, input/output price ceilings and supported structured response behaviour must be read from actual configured capability. Missing configuration leads to fixture-only operation; never auto-select/pay for a model during build.

Simulation mode is **not** sufficient proof of no paid calls: the current standalone documentation notes configured research/model adapters can still incur costs in simulation. The offline harness must explicitly replace all provider HTTP transports and reject unexpected external requests. Merely setting `WACRM_BRIDGE_MODE=simulation` is not the full test safeguard.

## Host prerequisites and chosen operating defaults

No new deployment edits are authorized by this plan. Implement validators and read-only readiness for these existing/new configuration inputs; document names without writing secrets:

| Input | Purpose | Missing behaviour |
|---|---|---|
| `CONCIERGE_DB_PATH` | Explicit absolute existing SQLite store | Startup refuses ambiguous persistence. |
| `WACRM_BRIDGE_MODE` | Immutable simulation/live execution namespace | Default simulation, but fixture transport also required for offline tests. |
| `WACRM_BRIDGE_TOKEN` / `WACRM_BRIDGE_URL` | Existing authenticated WACRM-to-service bridge | Useful disconnected UI; no external actions. |
| `CONCIERGE_UNIPILE_JSON` | Existing account-keyed provider binding | WhatsApp unavailable; research independent. |
| `CONCIERGE_MODELS_JSON` | Existing account-keyed model configuration | Live reasoning unavailable. |
| `CONCIERGE_DISCOVERY_JSON` | Existing discovery configuration, extended validated Exa type | Live discovery unavailable unless configured. |
| `CONCIERGE_CHRIS_SETTINGS_JSON` | New optional account-keyed nonsecret limits/policy settings | Safe below defaults; cannot enable autonomy. |
| `CONCIERGE_WACRM_INTERNAL_URL` | New explicit trusted base for projection callback | Projection queued, no browser-dependent substitute. |
| Existing Supabase server settings | Existing canonical CRM access | Projection unavailable; software tests use isolated fakes. |

External authority is stored through authenticated product commands, not enabled by a tracked configuration default. Optional settings may only supply maximum ceilings/default research behaviour; they cannot create live permission. Production operator values must be explicit before paid/external capabilities become ready.

Chosen initial ceilings when an owner enables eligible sending:10 new invitations/account/local day;50 ordinary prospect replies/day;10 group creations/day;10 substantive introduction messages/day;10 principal replies/day;100 total outbound messages/day; one initial invitation per resolved person and at most two unanswered follow-ups lifetime for that relationship. Count neutral group setup as an outbound message. The most restrictive total/purpose/recipient/provider bound wins. These conservative pilot settings are not a deliverability guarantee or a target to fill. Owner may lower them; raising host maximum is separate host configuration.

Paid-operation live default is zero until an existing approved host allowance is supplied. Synthetic replay fixtures explicitly configure a20USD/day test allowance and5USD/job ceiling using fake estimated/reported prices; no actual spend. This prevents a fresh session guessing a real commercial budget. Record rates by version; arithmetic uses micro-USD, reservations precede calls, and account daily windows use configured IANA timezone with UTC boundaries persisted at reservation. Clock rollback/DST cannot reset counters twice or restore consumed allowances.

Follow-up timing, consent age, research freshness, worker/concurrency and storage defaults are explicit in02–05. An account not ready for unsolicited timed work can still answer a recent legitimate inbound within current scope. Do not let a timing fallback manufacture timezone knowledge or override recipient limits.

## External acceptance that has not happened

The following remain unverified at planning time: real number ownership/registration, live Unipile v1 account/schema compatibility, actual group creation with both participants, real message receipt, group privacy failure variants, live model quality, paid-source billing reconciliation, installed production database constraints and contact-policy eligibility for a particular real prospect.

The builder must implement the software and test harness for all these paths, then report exactly which real observations are available. Missing external acceptance does not justify leaving the reducer, adapter, UI, recovery or fixture journey unfinished. It also does not justify declaring the live business model proven.
