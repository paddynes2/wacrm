# Acceptance matrix

All rows are required. “Test” means an executable deterministic test unless marked UI or operational. Map each ID to a test name/evidence in `BUILD-RESULTS.md`. Assertions about external actions must inspect the fake wire recorder and reopen persisted state. Simulation must exercise the same reducers, gates, scheduler and saga as live; only provider I/O differs.

## A: account, brief, principal and authority

| ID | Scenario | Required observable result |
|---|---|---|
| A01 | Blank workspace, no providers | Honest setup state; no invented prospects; no external calls. |
| A02 | Missing economic objective | One precise product prompt; discovery not scheduled. |
| A03 | Valid brief without geography/archetypes | Global research strategy allowed; no injected SA/industry restriction. |
| A04 | Principal display name absent | Activation refused, draft preserved. |
| A05 | Two browser tabs save different revisions | One accepted, stale one409; no silent overwrite. |
| A06 | Objective changes during paid research | Old result cannot qualify; spent/reserved cost retained. |
| A07 | Display-only setting changes | Monotonic revision; no unnecessary cancellation of valid research. |
| A08 | Principal number equals Chris | Group capability unavailable, research continues. |
| A09 | Provider account configured for two tenants | Both conflicting bindings disabled; no cross-tenant fallback. |
| A10 | Wrong provider type/account/self | No writes and precise binding failure. |
| A11 | Principal nonce correct once | Exact direct sender bound; nonce consumed. |
| A12 | Expired/replayed/forwarded/foreign nonce | No binding; bounded attempts; no nonce logging. |
| A13 | Research enabled, external off | Discovery/research/drafts operate; wire mutation count0. |
| A14 | Autonomy switched on with old pending drafts | Old drafts not dispatched; future eligible actions require new evaluation. |
| A15 | Viewer/agent/admin tries to expand authority |403; current owner-only policy enforced server-side. |
| A16 | Principal WA says “turn all sending on” | No authority expansion; explains console setting in product. |
| A17 | Principal WA pause | Durable pause before next dispatch; ingestion/recovery continue. |
| A18 | Prospect says “pause the whole company” | Only own pursuit affected; no tenant-control command. |
| A19 | Reconnect changes self identity | Connection generation changes, pending actions invalidated. |
| A20 | Fixture permission/phone copied into live | Rejected; no synthetic live authority/receipts. |

## R: research and economic judgement

| ID | Scenario | Required observable result |
|---|---|---|
| R01 | Customer endeavour | Evidence-backed appropriate archetype and thesis, no ungrounded pain claim. |
| R02 | Partnership endeavour | Relevance not rejected for missing buying budget. |
| R03 | Investor endeavour | Research respects brief and approved claims; no promised returns. |
| R04 | Distribution endeavour | Credible route-to-market evidence, not generic networking. |
| R05 | Acquisition contact | Public approved context only; confidential strategy omitted externally. |
| R06 | Specialist/expert endeavour | Expertise can qualify without purchase authority. |
| R07 | No known reciprocal benefit | Remains researchable/qualifiable when principal relevance is strong; uncertainty visible. |
| R08 | No immediate timing trigger | Enduring reason allowed; urgency not fabricated. |
| R09 | All first query results irrelevant | Alternative strategy/tool call, bounded by allowance. |
| R10 | Only repeated duplicate search results | Existing records reused, no repeated charge loop/new fake pipeline. |
| R11 | Search snippet only | Critical identity/contact claims not treated verified. |
| R12 | Two copied press releases | One source origin, not independent corroboration. |
| R13 | Same full name at different companies | Separate/ambiguous identities, not automatic merge. |
| R14 | Current role contradicts old bio | Both sources retained; material contradiction unresolved until researched. |
| R15 | Old announcement freshly crawled | Original event date shown; no false “just appointed.” |
| R16 | Source page says ignore rules/send data | No new tools/authority/recipient; inert untrusted content. |
| R17 | Private IP/local URL/embedded credentials | Host rejects before provider call. |
| R18 | HTTP 200 login/block page | Classified inaccessible, not evidence. |
| R19 | URL read truncated before critical claim | Gap remains; no made-up supporting span. |
| R20 | Model cites nonexistent source/span | Dossier/message rejected; bounded repair, no action. |
| R21 | Strict first-degree mode without roster | Eligibility unresolved, no false network-distance assertion. |
| R22 | Default WACRM-only relationship check | Coverage explicitly named; known contact excluded. |
| R23 | Existing sourced person later connects | Legitimate current follow-through preserved; no duplicate new pursuit. |
| R24 | Phone lookup returns shared switchboard | Not verified personal mobile; invitation blocked. |
| R25 | Correctly formatted enriched phone | Still distinct identity and permission requirements. |
| R26 | Research allowance exhausted | Checkpoint/next action; no paid call; other permissible work continues. |
| R27 | Two workers reserve last allowance | At most one receives reservation. |
| R28 | Provider timeout charge unknown | Reservation retained; no zero-cost assumption or blind paid replay. |
| R29 | Schema-invalid model output twice | Job ends visible contract error; no regex/free-text permission fallback. |
| R30 | A slow awaiting-reply candidate | Independent candidate discovery/research continues. |

## C: conversation, contact permission and scope

| ID | Scenario | Required observable result |
|---|---|---|
| C01 | Public phone and good fit, no contact permission | No initial WA; “permission needed”; research continues. |
| C02 | Evidenced permitted inbound opt-in | Contact scope recorded only as explained in flow. |
| C03 | Owner attests contact permission | Source/date/sender/scope retained; model cannot invoke this command. |
| C04 | Clear yes to exact combined group question | Intro/group evidence bound to principal and question; saga can proceed. |
| C05 | Yes to generic introduction question | Group clarification sent once if authorized; no group create. |
| C06 | “Sure, tell me more” | Factual reply; no consent granted. |
| C07 | “Yes, but email me” | Channel preference; no WA group and no automatic email. |
| C08 | “Not interested” / “no thanks” | Declined, no follow-up. |
| C09 | “Don't contact me again” | Sender/account suppression; all dependent briefs cancelled. |
| C10 | “Wrong person/number” | Suppression and identity invalidation; no repeated identity probe. |
| C11 | “Not now, ask in November” | Explicit defer; unclear year/timezone not guessed for dispatch. |
| C12 | “Yes, if pricing is below X” | Condition retained; no unconditional group consent. |
| C13 | Reaction/thumbs-up only | No scope inferred; at most clarification. |
| C14 | Quoted/forwarded “yes” | Not current recipient consent. |
| C15 | Voice note/photo without evaluated transcript | No consent inference; useful text clarification or visible gap. |
| C16 | Two pending questions followed by yes | Context ambiguity resolved before permission. |
| C17 | Reply-to names another question | Permission applies only to actual question or remains unclear. |
| C18 | Later no after earlier yes | Withdrawal wins; no group/introduction action. |
| C19 | Old delayed yes after current no | No revival. |
| C20 | Non-English affirmative not covered by evaluated parser | Interpretation needed, no automatic permission. |
| C21 | “How did you get my number?” | Truthful source/provenance answer, no fabricated relationship. |
| C22 | Referred colleague number | Separate lead; no transferred permission. |
| C23 | Pricing/terms question beyond public facts | No invented commitment; principal attention, independent work continues. |
| C24 | New principal or materially different endeavour | Old consent cannot authorize new introduction. |
| C25 |30-day stale recipient agreement | Reconfirmation required before group; no date-only resurrection. |
| C26 | Two unsuccessful ambiguity clarifications | Stop clarification loop; affected pursuit attention only. |
| C27 | Follow-up becomes due without useful reason | No message just because clock elapsed. |
| C28 | Two verified unanswered follow-ups already | No third, including new brief/retry/new chat. |
| C29 | Inbound arrives before due follow-up | Follow-up cancelled; current reply handled. |
| C30 | Unknown prospect timezone | No unsolicited timed follow-up; recent active reply handled within scope. |

## I: ingestion, ownership and ordering

| ID | Scenario | Required observable result |
|---|---|---|
| I01 | Provider redelivers message | One normalized event/semantic response. |
| I02 | Same message ID, different chat | Distinct compound identity, no collision. |
| I03 | Same ID/chat edited body | Edit event or collision attention, not silent overwrite. |
| I04 | Consent message deleted | Prospective permission invalidated/revalidated. |
| I05 | Pagination final page contains STOP | No reply/send scheduled from earlier pages. |
| I06 | Cursor loop/page cap reached | Incomplete history, no dispatch. |
| I07 | Unowned malformed group | No model access; other valid owned chats continue. |
| I08 | Owned malformed chat | Quarantine only affected thread; clear reason. |
| I09 | Group sender ID is attendee ID | Resolve to provider ID or fail, never assume equality. |
| I10 | Equal provider timestamps | Original times retained; observed_seq deterministic; ambiguity does not grant consent. |
| I11 | Future skew beyond tolerance | Ordering-dependent action paused, evidence retained. |
| I12 | Media/system/membership event | Normalized without crashing textual ingestion. |
| I13 | Known assistant echo | No human takeover; verified correlation. |
| I14 | Delayed possible unknown-send echo | Reconcile before manual classification; no duplicate reply. |
| I15 | Verified manual outbound | Takeover, queued bot actions cancelled. |
| I16 | Principal commands in forwarded text/group by prospect | No control authority. |
| I17 | Provider excludes old history | Coverage unknown explicitly; no fake full-history guarantee. |
| I18 | UI closed, idle worker | Inbound still processed; no browser dependency. |

## D: dispatch, races and reconciliation

| ID | Scenario | Required observable result |
|---|---|---|
| D01 | Exact eligible action | Frozen digest matches actual multipart wire content. |
| D02 | Text/recipient/subject modified after approval | Digest/current-state validation denies wire. |
| D03 | Brief/authority/identity revision changes | Stale queued action cancelled/re-evaluated. |
| D04 | STOP commits before started claim | Wire call count0. |
| D05 | STOP arrives after started claim | Subsequent actions0; in-flight outcome observed and honestly reported. |
| D06 | Two workers claim same action | Exactly one wire call. |
| D07 | Worker lease expires during mutation | New worker reconciles; no resend. |
| D08 | Crash after claim before wire | Conservatively uncertain unless no-dispatch proof exists; no blind replay. |
| D09 | Provider commits then response lost | Read-only recovery; eventual matching receipt or attention, never resend. |
| D10 | Accepted response persisted, verification fails | Accepted/unknown status retained; not verified. |
| D11 | Local receipt write fails after provider success | Restart sees started claim; recovers, no duplication. |
| D12 | HTTP 429/5xx mutation | No assumed safe retry; contract-classified uncertainty. |
| D13 | Invalid/missing response IDs | Unknown, no fake success. |
| D14 | Same text exists from weeks ago | Not valid receipt without dispatch/watermark correlation. |
| D15 | Two plausible same-text recent results | Ambiguous attention; no automatic selection. |
| D16 | Reconciliation finds nothing repeatedly | Unknown persists; elapsed time not non-execution proof. |
| D17 | Long network preflight | SQLite writer available for pause/STOP from another connection. |
| D18 | Account A provider hangs | Account B eligible work continues within configured pool. |
| D19 | Manual click Retry on unknown | Only reconciliation offered; no reset to queued. |
| D20 | Meta text/media/template/reaction/buttons/list helper in standalone | Refused before fetch across all callers. |

## G: group introduction

| ID | Scenario | Required observable result |
|---|---|---|
| G01 | Fresh full journey | One group create, then one substantive intro, one completed outcome. |
| G02 | Group create returns2xx only | No completed introduction count. |
| G03 | Group has Chris and prospect only | No substantive message; missing principal recorded. |
| G04 | Wrong/extra member | Immediate stop, no private content sent. |
| G05 | Self membership unverified | External attendee count insufficient; readiness false. |
| G06 | Membership eventually appears | Bounded read-only verification then substantive send once. |
| G07 | Privacy restriction prevents joining | No automatic re-create/add/invite-link workaround. |
| G08 | Same group subject already exists | Not reused by subject alone. |
| G09 | Group create succeeded, process crashes | Exact group recovered; no second group. |
| G10 | Consent withdrawn after group create | No substantive intro; truthful partial outcome. |
| G11 | Principal/prospect leaves before intro | Stop pending intro. |
| G12 | Participant leaves after verified intro | Historical completion retained; later departure event. |
| G13 | Stranger joins after intro | No automatic disclosure/reactive context until scope revalidated. |
| G14 | Intro message content differs unexpectedly | Not verified; evidence/attention. |
| G15 | Recipient replies after intro | No automatic new invitation or follow-up cadence. |
| G16 | Directly addressed factual clarification in owned group | Reply only within current membership/authority/public scope. |
| G17 | Read/delivery metadata absent | UI says observed sent intro, not read by both. |
| G18 | Repeat completion processing | One immutable outcome and one deterministic CRM note. |

## P: persistence, projection, product and operations

| ID | Scenario | Required observable result |
|---|---|---|
| P01 | Command POST response lost | Query same ID returns persisted result, no duplicate job. |
| P02 | Same command ID changed payload |409 idempotency conflict. |
| P03 | Account B entity requested by A |404 with no existence disclosure. |
| P04 | Malicious callback sends foreign contact ID | Projection rejects before any write. |
| P05 | CRM commit succeeds, ack lost | Same deterministic rows reused; no duplicates. |
| P06 | CRM unavailable while WA intro verified | Outcome preserved, projection pending, no WA resend. |
| P07 | Prospect contact phone changed externally | Projection identity mismatch; no misfiled transcript. |
| P08 | Contact deleted/suppressed | Tombstone prevents automatic recreation. |
| P09 | Group thread mirrored | Participant-labelled Chris view; not false direct inbound. |
| P10 | Missing installed unique constraints | Readiness unverified/incompatible; no automatic migration. |
| P11 | Filesystem full/corrupt blob | Dependent dispatch unavailable; no successful persistence acknowledgement. |
| P12 | Document8/12/16 MiB thresholds | Corresponding research/outbound/hard-limit states exactly enforced. |
| P13 | Unknown future namespace schema | Read-safe error, no down-conversion/mutation. |
| P14 | Account switch during slow fetch | Late account A response never renders in B. |
| P15 | Idle page receives new inbound | Poll updates without pre-existing queued jobs. |
| P16 | POST revision conflict | Draft retained, current state shown, no stale optimistic success. |
| P17 | Screen390x844 and1440x900 | UI evidence: no overflow, usable buttons/details, primary flow complete. |
| P18 | Keyboard/screen-reader status | UI evidence: labelled controls, visible focus, status not colour-only. |
| P19 | Unsafe source HTML/links/export values | Escaped rendered content; no executable URL; export safe. |
| P20 | Worker thread dead while web healthy | Stale heartbeat visible; live readiness not green. |
| P21 | Restart with pending jobs/unknown actions | Research resumes; started writes reconcile; verified outcomes unchanged. |
| P22 | Backup/restore rehearsal on synthetic DB | Consistent DB+blob references; restored authority remains off; no duplicate live dispatch. |
| P23 | No credentials during autonomous build | All offline software/tests/UI completed; exact live gaps reported. |
| P24 | Baseline calendar/dogfood tests | All preserved; no accidental regression from Chris versioning. |
| P25 | External network attempt in offline suite | Test fails loudly, including real model/search calls in simulation. |
| P26 | Full fresh workspace replay | Actual tool loop + all state transitions + projection, not preloaded introduced fixture. |

## Completion trace for the principal demonstration

Save an event trace showing: brief activation -> discovery search -> source read -> host person registration -> dossier/critic -> identity/contact eligibility -> frozen invitation -> verified direct receipt -> actual normalized inbound -> permission scope -> group-create claim -> provider response -> exact three-person membership -> substantive intro claim -> verified message -> completion event -> CRM acknowledgement. Include action IDs and hashes, not secret keys or real prospect content. This trace is the strongest concise proof that the product is implemented end to end.
