# Wabi and Unipile live dogfood acceptance

The executable software checks below do not establish recipient interest, working
number registration, successful delivery or commercial value. Each stage records its
own evidence. Synthetic fixtures never count as live outcomes.

## Number setup still required from the account owner

1. Obtain a fresh Wabi number. Check its actual renewal term and ability to receive the
   registration/recovery challenges needed for this account. No current availability or
   compatibility is asserted by the code.
2. Register that number as a WhatsApp account using the regular app path the owner chose,
   if supported by the actual app/device arrangement. Keep the personal account separate.
   This plan does not require Meta business verification or Business API onboarding.
3. Complete any ownership challenge manually and retain renewal/recovery access.
4. Set Chris's identity transparently as the principal's AI assistant.
5. Link that WhatsApp account in Unipile using the account owner's active session. Record
   the resulting Unipile account ID and provider-assigned API base URL. Do not reuse a
   generic account ID which might identify a LinkedIn seat.
6. Supply the product's server-owned account mapping through the documented deployment
   configuration flow. Do not paste credentials into a conversation or browser form.

These steps are pending external setup, not actions completed by this build.

## Executable read-only readiness probe

From the product checkout with Python installed:

```powershell
python -m concierge_service.ingestion --base-url https://YOUR-HOST.unipile.com:YOUR-PORT/api/v1 --account-id YOUR-UNIPILE-ACCOUNT-ID
```

Use the exact URL Unipile assigned. The command requests the API key through a hidden
terminal prompt, never a command-line argument, never writes it, and makes GET requests
only. It verifies the account's exact identity and WhatsApp type, then complete bounded
chat-list ownership. The result explicitly reports `live_delivery_verified=false`.
It prints no message contents, phone numbers or credentials. No account is created,
registered, linked or mutated by this probe.

The product's readiness command records `connections.verified_at`. That is a connection
check timestamp. It must not be presented as delivery verification.

## Polling reconciliation

`sync_account(engine, account)` uses the explicitly scoped Unipile client. It validates
all returned chats before applying messages. Complete provider pagination is required;
provider retention may still be partial. It matches only a unique existing configured
prospect identity (corroborated phone or established provider ID). It never creates a
prospect from an unknown chat or assigns an ambiguous number to a person.

Unknown chats are recorded for review. A principal-only chat cannot identify which
prospect the principal is discussing; it remains unclaimed. The current engine binds a
single recipient chat, so group ingestion remains explicitly unclaimed for review until
the engine accepts independently verified principal/group chat bindings. Multiple
unbound chats matching the same prospect also remain unclaimed. Opaque unresolved group
senders require review.

Normalized incoming events go through `Engine.ingest`; unmatched own-account outbound
goes through `Engine.manual_outbound` for takeover. Textless media remains textless and
requires human review. A recorded non-simulated outbound receipt must match message,
prospect, provider account, chat and text to qualify as an assistant echo. `is_sender`
alone does not establish manual origin or an assistant receipt.

Successful polling persists account/chat checkpoints and `last_sync`. These checkpoints
are audit/recovery state, not offsets used to skip unknown provider history. Replays
depend on engine idempotency. If a process exits halfway through applying validated
messages, completed engine transactions stay durable and a repeat sync safely retries
the rest. Failed evidence reads preserve the prior successful checkpoint and record an
explicit error; they do not record a successful sync. No unauthenticated webhook path
is introduced.

## Controlled live experiment

Before authorizing real actions, record the exact offer, audience, exclusions, supported
claims, prospect evidence, follow-up limits and research/model budget. Start with a
controlled recipient and the principal; prospect pilot waves follow only after transport
and behaviour acceptance.

| Check | Required evidence |
|---|---|
| First approach | Authorized exact recipient/body, provider receipt, recipient confirms receipt |
| Incoming reply | Bound account/chat/message ID, timestamp, actual sender and retained text |
| Reconnect | New reply reconciles once after reconnect/restart |
| Human takeover | Manual outbound cancels queued agent actions; Chris remains paused |
| Opt-out | Refusal recorded and further drafts/actions cancelled |
| Introduction | Both parties' scoped agreement and exact membership read-back |
| Calendar | Availability checked, accepted times/zones, actual event read-back |
| Amendment | Changed/cancelled event verified, or explicitly assigned to the principal |
| Outcomes | Useful introduction/meeting held, operator minutes and settled costs |

Connection readiness and polling are implemented read paths. Sending and live calendar
effects require the separately authorized dispatch path and live acceptance evidence;
this document does not grant sending permission or claim that those effects occurred.

## Discovery and phone enrichment limitations

Treg's specific deployed catalogue was read without credentials on 2026-09-09 and still
exposes `treg.people.search` as a routed endpoint. The generic docs contradict that
description; see [provider contract evidence](PROVIDER-CONTRACTS.md). No paid provider
query was made. Catalogue existence does not demonstrate useful results for this audience.

The inspected existing people-search adapters return identity/company/profile fields,
not a verified phone-enrichment contract. The product therefore records missing phones
and requires attributable enrichment evidence. A future phone provider must be evaluated
on actual person-to-number attribution, freshness, coverage and cost; a formatted number
or a provider's generic “verified” flag cannot stand in for that evaluation.

Calibrate on ten manually reviewed candidates, then consider five initial approaches
and up to twenty total only within the authorized pilot. These are proposed learning
cohorts, not statistically validated market evidence or guaranteed safe sending volumes.
