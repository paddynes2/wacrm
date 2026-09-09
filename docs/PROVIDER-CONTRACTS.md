# Standalone dogfood provider contracts

Implementation: `concierge_service/providers.py`. Offline verification:

```powershell
python -m unittest discover -s concierge_service/tests -p test_providers.py -v
```

All credentials are explicit arguments supplied by the server. This module never reads
OS files or environment variables. Configuration must remain server-owned, never a
recipient-controlled request field. `config['http']` accepts a test function
`(method, url, headers, body) -> (status, headers, decoded_json_object)`.
The production transport uses Python's standard library with bounded response size,
60-second timeout, no redirects and no automatic retries. Errors omit provider response
bodies and credentials. The host must reserve budget before a paid call, persist actual
cost afterward, and retain an uncertain reservation if the request's result is unknown.

## Discovery

`discover(brief, limit, config)` returns `prospects`, `cost_usd`, `provider`, `errors`.
Limits must be integers 1 through 100. Fixture results are explicitly synthetic, carry
`example.invalid` URLs and no phone numbers. They prove workflow only.

Treg configuration requires `provider='treg'`, `token`, and `max_cost_usd`. Optional
`filters` accepts only `q`, `company_domain`, `title`, `full_name`, `country`, `location`,
as strings, and `keywords` as a list of 1..20 strings. Otherwise the audience becomes `q` and geography becomes
`location`. The request goes to `https://treg.to/call/treg.people.search`; the per-call
cap is sent in `X-Treg-Route-Max-Cost`. Settlement is recorded from the micro-dollar
header or envelope. An over-cap charge remains visible and adds an error for the host
to pause research. Missing settlement is an error, not zero cost.

This is one page, with no verified cursor-input contract. A returned `next_cursor`
produces an explicit partial-result warning. Provider errors never become an empty
successful shortlist. Identity normalization deduplicates by profile or name/company.
All candidates remain unqualified pending corroboration. No phone numbers are inferred.

The implemented wire contract and row mapping were cross-checked against
`OS/packages/treg-client/treg_client/__init__.py`, its recorded `search_pos.json`, and
`OS/tools/lead-source/treg_adapter.py`. Those source fixture tests passed (43 tests across
the transport and existing discovery adapters). This is local contract evidence, not a
fresh paid-provider result or current price guarantee. The historical $0.05-per-row
comment is deliberately not used as a price promise.

On 2026-09-09, unauthenticated GETs to the deployed
[`/catalog/endpoints/treg.people.search`](https://treg.to/catalog/endpoints/treg.people.search)
and [`/catalog/search?q=people%20search&limit=2`](https://treg.to/catalog/search?q=people%20search&limit=2)
both returned HTTP 200 and still explicitly exposed this routed endpoint, its POST
method, supported filters, envelope, and per-call cap header. This contradicts the
general `/docs` prose saying no automatic routing. The more specific deployed catalogue
corroborates the recorded response fixtures. It also specifies `keywords` as a list;
this adapter preserves that shape instead of copying the old adapter's string coercion.
Catalogue availability does not establish successful paid execution for this account.

Icypeas extraction is not wired here: its existing adapter imports OS intake and learning
paths. Its token pagination and `lastJobTitle`/`lastCompanyName` mapping were inspected,
but no phone-enrichment contract was found in either inspected discovery adapter.
Phone ownership and new Wabi/Unipile compatibility remain live acceptance questions.

## Phone enrichment

`concierge_service.enrichment.enrich(prospect, config)` returns `phone`, `source`,
`evidence`, `phone_status`, `cost_usd`, `errors`. The host reserves budget before calling.
Configuration requires `provider='treg'`, an explicit `token`, and `max_cost_usd`.
The fixture provider returns a labelled synthetic miss, never a manufactured phone.

An unauthenticated GET to the deployed
[`treg.people.phone.find` catalogue entry](https://treg.to/catalog/endpoints/treg.people.phone.find)
on 2026-09-09 returned HTTP 200. Its `routing.contract` explicitly declares POST,
`linkedin_url` or `domain` plus `full_name` as supported identity variants, and an
`output.phone` field containing a provider-formatted string or null for a miss.
Optional output fields include `line_type` and `country_code`. The implementation sends
the verified routed endpoint with the whole-call cap and strict-filters header.
No paid call was made; tests use synthetic contract responses, not purported live hits.

Each lookup binds a prospect ID, name and company plus a public LinkedIn person URL or
company domain. Evidence records the exact request, requested identity digest, output,
raw provider evidence, serving child and observation time. A returned E.164 number is
`provider_unverified`; non-E.164 formats remain unresolved and no country is guessed.
Do-not-call metadata suppresses the returned phone. Ignored identity filters similarly
prevent presenting an eligible phone. Provider settlement remains recorded even when
it exceeds the requested cap, and the host must pause further work on returned errors.

The proxy's catalogue is the primary source for this normalized contract. Its child
LeadMagic catalogue also exposes a recorded null-phone miss, but no positive phone hit
was purchased or used as evidence here. Live coverage, correct ownership, WhatsApp
reachability and permission to approach still require independent corroboration.

## Model generation

`generate(brief, prospect, messages, config)` returns `text`, `intent`, `cost_usd`,
`provider`, `usage`. The intents are `reply`, `interest`, `decline`, `optout`,
`scheduling`, `review`. An intent is an interpretation for host validation, never
permission, agreement or execution evidence. The fixture provider is scripted and
labelled synthetic in usage. It is not a quality substitute for a real model trial.

Real providers require `api_key` and the exact operator-selected `model`. No model name
or price is guessed. OpenAI uses `/v1/chat/completions` with JSON-object output and
`max_completion_tokens`; Anthropic uses `/v1/messages` with the version header and
`max_tokens`. Unsupported model features surface as errors; no silent model fallback.
Only complete text responses containing precisely the expected JSON fields pass.
Tool calls, truncated responses, malformed JSON and oversized text are refused.

The system instruction treats all supplied context as data, forbids invented evidence
and commitments, and grants no tools. Code still owns consent and sending decisions.
Optional `input_usd_per_million` and `output_usd_per_million` calculate costs from token
usage. Without known rates, cost is `None`. Anthropic cache usage stays unpriced rather
than silently treating cache writes or reads as ordinary tokens. The host must pause or
retain reserved budget whenever cost is unknown.

Request contracts were checked against the official [OpenAI Chat reference](https://developers.openai.com/api/reference/resources/chat)
and [Anthropic Messages reference](https://platform.claude.com/docs/en/api/http/messages/create).
No model inference or paid provider request was made during implementation.

## Unipile WhatsApp reads

`UnipileClient(base_url=..., api_key=..., account_id=..., http=None)` has three public
read methods: `verify_account()`, `list_chats()`, `fetch_conversation(chat_id)`.
The host URL must be HTTPS on Unipile's domain; provider-assigned ports are allowed.
Credentials cannot fall through to an unrelated LinkedIn account.

Identity verification requires the exact bound account and `type='WHATSAPP'`. It does
not establish delivery or registration success. Chat and attendee ownership, complete
bounded pagination, direction, timestamps and membership are checked. Unknown group
senders remain unknown. An outbound echo's manual origin remains unknown until the host
matches its message ID to the dispatch ledger. Media stays in raw evidence; content is
not invented. Membership is checked again after reading.

The 20-page, 100-row bounds are local verification bounds, not provider limits or proof
of complete historical WhatsApp retention. Incomplete, cyclic or malformed pages fail.
The checks preserve the inspected Fleet `transports/whatsapp.py` and adversarial tests,
with explicit account/client injection replacing Fleet paths and global configuration.

This adapter intentionally exposes no sending method. Live execution must use the
product's separately reviewed dispatch path with frozen recipients, current state,
authorization, suppression, exact membership checks and uncertain-effect reconciliation.

## Inert reviewed transport boundary

`reviewed_transport.execute_reviewed` implements the exact request/read-back boundary,
and is inactive in the default service. The optional host composition connects it
through `live_execution.execute_decision`. It requires all five
host callbacks: `gate(canonical, send_fn)`, `validate_current(frozen)`,
`inspect_thread(snapshot, frozen)`, `claim(digest, frozen)`, and
`record(digest, frozen, status, evidence)`. Missing callbacks refuse before provider I/O.
The latter four must explicitly return `True`; implicit `None` does not pass a gate.

The host must enforce human authorization, kill/suppression/caps, current conversation
revision and consent, complete recipient history, atomic single-use claims, and durable
started/verified/unknown records. Hold the same dispatch lock used for inbound/takeover
across final checks and execution. No callback default grants authority. The canonical
action binds sender, recipients and the full product payload using the existing HR12
allowlist. An optional OS-side integration must use `confirm_send.guarded_send`, not
invent an alternative approval token or silently arm a permission flag. That integration
is outside the standalone runtime; otherwise its ledger/redactor/CRM paths would
reintroduce OS coupling.

This boundary was checked against the actual canonical gate, its bound-key validation,
replay lock and pre-send record, plus Fleet's WhatsApp request and read-back implementation.
An authorized callback can issue at most one POST per callable, and durable claims must
prevent cross-process replay. Read-back must confirm the exact chat members, message ID,
direction and text. Provider timeouts, missing receipts and failed read-back remain
uncertain; no automatic retry occurs. A verified provider message is still not evidence
that the recipient received or read it. Tests terminate every POST in a fake HTTP client.

`live_execution.execute_decision` now supplies state/history validation and durable
started/verified/unknown ledger callbacks. `host.create_authorized_app` connects exact
reviewed API actions to that executor only when a real host authorization mechanism is
explicitly supplied. No such mechanism was installed in this session. Implementing this
boundary does not itself authorize any live send.

## Google Calendar

`calendar_provider.GoogleCalendar` verifies the expected primary calendar account,
explicit calendar allowlist, complete free/busy coverage and event identity. Tokens
come only from a host-supplied callable. Booking, reschedule and cancellation plans
bind the exact HTTP method, URL including `sendUpdates=all`, payload and ETag where
applicable. Host authorization, durable claim, final preflight and read-back are
mandatory. Uncertain writes remain blocked from replay; sparse cancellation
responses never become fabricated full verification.

The live Engine calendar path and optional host API composition were tested against
fake Google-shaped responses. No OAuth account or real calendar was mutated. Source
contracts: [free/busy](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query),
[event creation](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert),
[event patch](https://developers.google.com/workspace/calendar/api/v3/reference/events/patch),
[event resource](https://developers.google.com/workspace/calendar/api/v3/reference/events),
[calendar identity](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList/get).

## Source attribution

This implementation adapts local OS provider contracts, not a third-party SDK copy.
No license file was present in the inspected OS treg/unipile package directories; this
does not imply a new license grant. Preserve this provenance when moving these files.
WACRM's existing root MIT license and upstream attribution remain unchanged.
