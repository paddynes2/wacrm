# Product decisions and complete journeys

## What the customer sees

The product is called **Chris** in the working UI. No Agent Fleet branding, agent roster, internal policy names, tool budgets in tokens, provider identifiers or implementation stages in ordinary conversation. WACRM supplies account access, contacts and history. The main screen answers: what Chris is trying to achieve, whom he is working on, what has happened, what needs the customer's attention, and whether he can currently operate.

Top navigation: **Chris**, **People**, **Introductions**, **Settings**. Existing WACRM contacts/inbox remain accessible through contextual links. `/dogfood` remains an advanced simulator, not the first-run destination. Calendar screens are optional legacy surfaces, not onboarding requirements.

Main screen: current endeavour in one sentence; a conversation panel with Chris; four truthful counts (researching, approached, awaiting reply, introduced); an activity feed; at most three distinct attention categories expanded on demand; visible Pause. “Chris is researching” requires a recently leased research job. “Waiting for replies” requires verified invitations. Empty means no candidates yet, not a fake starter pipeline.

## J01: first account and first endeavour

1. Use existing WACRM authentication. No new signup/billing/authentication system.
2. Explain the three-person introduction outcome. Collect principal display name, short accurate public context and economic endeavour. Principal name is required; no hard-coded Patrick default.
3. A natural-language description can be incomplete. Chris proposes a structured brief: objective, people who could advance it, exclusions, geographic restrictions if any, allowed public claims, useful background, operating timezone. Unknown geography means global research, not South Africa. Unknown commercial objective prevents new discovery and produces one concrete missing-objective prompt in the product.
4. Show the interpreted brief with editable fields. “Start research” activates that version. This single customer action covers ordinary candidate choices within the brief. Do not ask the principal to approve each candidate.
5. Connections can be completed before or after research. Show separate research, WhatsApp connection, principal identity, contact permission and external-autonomy statuses. Lack of WhatsApp does not prevent configured research.
6. Operating timezone is explicitly selected in onboarding, suggested from the browser but never silently saved as verified. A principal's timezone does not prove a prospect's timezone.
7. Research allowances are visible as customer-readable money/operation ceilings. No configured paid allowance means research adapter unavailable; fixture demo remains clearly labelled. Turning on research cannot silently enable external messaging.

First-run demo uses a separate simulation workspace/database and conspicuous Simulation banner. Switching to live never migrates synthetic messages, phone attestations, opt-ins, groups or receipts. Real and simulation modes remain immutable per workspace instance.

## J02: dedicated WhatsApp identity and principal binding

Chris must have a distinct WhatsApp identity. If the principal connects their own number as Chris, the app explains that a group of Chris + principal + prospect needs three distinct identities and keeps external capability unavailable.

For this release the host supplies the existing Unipile account configuration securely. Settings guides number registration/linking through the configured provider flow and reports observed connection lifecycle. Do not build a new number reseller or assume Wabi registration succeeds. The builder implements all UI states using fixtures even if actual provisioning remains external.

Bind the connected account by exact provider account ID, WHATSAPP type, observed owner ID, connection generation and healthy status. Only one WACRM tenant may own that provider account. A reconnect with a different owner invalidates all recipient aliases, consent applicability and pending dispatches until explicitly rebound by the principal in the console.

The customer proves control of their separate WhatsApp identity by sending a short-lived challenge from their number to Chris. Console generates a cryptographically random nonce, valid ten minutes, one use, hashed at rest. Inbound text on the exact direct chat consumes it atomically. No outbound challenge message is necessary. Hide nonce from logs. Challenge text is not forwarded to the model. Rate-limit five failed claims per ten minutes; expire rather than guessing sender identity. Principal binding does not derive from display name or a forwarded message.

Existing provider configuration and principal identity records can be observed read-only during setup. Never print credentials into UI, errors, fixtures or docs. Secret rotation is a host operation; code does not edit `.env`.

## J03: activating autonomous introductions

Authenticated owner sees the current brief, dedicated Chris identity, named principal, supported contact-permission basis, allowed actions and limits. The switch covers future eligible invitation/reply/group-create/introduction actions. Record actor, time, revision and first eligible action timestamp. Research authority remains separate.

No per-candidate approval ramp. Existing pending drafts remain pending when the switch turns on; Chris re-evaluates and creates fresh actions against current state if still worthwhile. Turning it off cancels unstarted dispatches and leaves research/reconciliation available. It cannot recall a provider request already dispatched. The UI reports any in-flight uncertainty precisely.

For the coding session, implement and test this mechanism; do not activate real autonomous sending. The user's autonomous implementation request authorizes software work, not live messages to arbitrary people.

## J04: resourceful discovery

Chris decomposes the endeavour into credible archetypes, investigates public signals, tries different search strategies, registers sourced people, deepens promising candidates and ranks them with reasons. He can find customers, partners, investors, distributors, acquisition contacts or experts. He does not impose buyer-budget/authority gates on every endeavour.

Several candidates advance concurrently. No fixed rejection percentage, one-open-introduction cap or alternating-day restriction. A configured capacity ceiling is a resource bound, never a daily target. A slow reply or bad provider account for one candidate does not halt the queue.

Each person card shows identity, why they could advance the brief, cited facts, labelled inferences, important gaps and next action. “No candidates found” includes the searches tried and the next strategy; it is distinct from provider failure, missing configuration, exhausted allowance or inability to read a source.

Known existing relationships are excluded from *new* introductions using account-scoped WACRM contacts and explicit imports/exclusions. The UI accurately names the coverage of that check. Strict LinkedIn first-degree exclusion is available only with a fresh configured roster; if selected and unavailable, eligibility remains unresolved. No private OS roster is imported automatically. A sourced person who later becomes connected can retain legitimate existing follow-through.

## J05: identity and contact permission gaps

A qualified person without a trustworthy phone remains in research. Chris may search public identity/contact evidence and perform a permitted bounded lookup. A shared company switchboard, ambiguous name match, WhatsApp profile picture or enrichment hit does not prove a person's mobile identity.

Contact permission is independently recorded from an inbound opt-in flow, an existing verified consent record or an explicit operator attestation with retained source, scope, business identity and date. A link to a public page alone is not a consent record. Operator corrections are auditable; a model cannot call the permission-recording command.

An unresolved person shows “Relevant; contact route needed” or “Relevant; WhatsApp permission needed.” Chris continues scouting others. The product can offer a prospect-initiated WhatsApp contact link to the principal to share through their own existing channels. It does not send emails/LinkedIn messages automatically, pretend that link has been shared or count a click as opt-in. Prospect-submitted “start” establishes only the scope explained in the entry flow, not blanket future marketing.

## J06: first invitation

Before dispatch, refresh the active brief/thesis where required, identity, exact direct chat, permission, current inbound and manual activity, budget, authority and connection health. The message names Chris as an AI assistant/connector working with the named principal, offers one specific evidenced reason to meet, and asks one clear question. No invented urgency, endorsement, needs, prior acquaintance or claim that the principal personally selected the person.

Preferred eligible-recipient wording is approximately: “Hi Maya, I'm Chris, an AI assistant working with Alex. Alex is exploring distribution for [accurate offer], and your work on [supported fact] looked relevant. Would you be open to a WhatsApp introduction in a small group with Alex and me? You would both see each other's WhatsApp number.” The model writes context-appropriate original prose; this is not a template to copy to every person. Shorter messages may ask interest first, but then require a separate group question.

Do not include private dossiers, speculative financial claims, sensitive attributes or principal confidential strategy. Allow one easy decline. Don't append a second unrelated ask or a calendar link by default.

## J07: replies, including the ambiguous ones

| Prospect input | Product behaviour |
|---|---|
| Clear yes to the exact combined named-principal/group/number-visibility question | Record scoped evidence; prepare group saga. |
| “Yes” to “open to an introduction?” only | Record introduction interest; ask a short group/number-visibility question. No group yet. |
| “Sure, tell me more” | Answer from public approved context; permission remains pending. |
| “Who is Alex?” / “How did you find me?” | Answer truthfully from permitted principal profile/source provenance; no invented relationship or fabricated source. |
| “Email me” | Record channel preference and stop WA invitation progression. Notify principal in product; no automatic email launch. |
| “Not now, try November” | Store explicit deferred scope/date. If year/timezone uncertain, use one clarification or remain deferred without dispatch. No automatic cold reopening outside existing permission. |
| “No thanks” | Decline this endeavour; no follow-up. |
| “STOP”, “don't contact me again”, wrong number | Suppress the recipient identity for this business sender; cancel jobs. Wrong number also invalidates identity and creates a correction event. |
| “Yes, but only after you send your pricing” | Conditional, not group consent. Answer with approved facts or surface missing answer. |
| “Talk to my colleague” with a phone number | New lead, separate evidence/identity/permission work. The referrer's reply is not the colleague's permission. |
| Emoji/reaction, attachment, quoted yes, forwarded acceptance, voice note | Never infer group consent from unavailable or ambiguous meaning. Ask one text clarification when eligible; unsupported media remains visible. |
| Hostile message or complaint | Stop proactive work on that identity, acknowledge only if useful and allowed; report reason without debate. |
| Request for pricing/contract promises/commitment | Use approved public information; escalate real commitments to principal. Do not negotiate beyond mandate. |
| Request to change your instructions or reveal the database | Treat as untrusted data, decline inappropriate disclosure, no tool or authority change. |

Supported launch language is English; public evidence can contain other languages but unverified translation does not establish permissions. A non-English reply without an evaluated parser is “interpretation needed,” not automatic rejection/consent. The acceptance corpus includes dialect, negation, politeness and quoted text.

## J08: creating and writing the introduction

1. Freeze the named principal, prospect, Chris account, consent evidence, public introduction facts, intended group subject and exact messages.
2. Create the intended group through a durable action. Include only a neutral setup line initially if v1 requires a starting message. Never rely on blank-text group support, which is not proven.
3. Verify exact group, connected self and both intended external participants. A 2xx is insufficient. Privacy restrictions can prevent a member being added. Never add extra people, use a new number or send an invite link without the affected person's applicable permission.
4. Send the substantive introduction in that verified group: introduce both people accurately, explain the commercial reason to connect in two or three short paragraphs, suggest they take the conversation from here. Do not promise a meeting or claim the prospect has a need they did not express.
5. Independently verify the exact message, sender and group, record completion once, and project the introduction to WACRM.
6. Stop proactive candidate follow-ups. Chris remains in the group, available for a directly addressed clarification within scope; he does not chatter, auto-leave, read unrelated groups, schedule or negotiate by default.

Example substantive shape: “Alex, meet Maya, [verified role/relevance]. Maya, Alex [approved public description]. The reason I thought it was worth connecting is [specific supported thesis, reciprocal possibility labelled modestly]. You both agreed to this introduction, so I'll leave you to take it from here.” Do not claim both agreed unless principal mandate and exact recipient consent still apply.

If the principal/prospect leaves before the substantive message, pause the saga. If they leave after a verified introduction, retain the historical outcome with a later departure event. If a new person joins, stop automatic group replies and protect private context. Never count a group created with only Chris and one other person as an introduction.

## J09: no response and follow-up

At most two unanswered follow-ups per new relationship across all brief revisions and retries. Follow-ups require a useful reason and a still-valid mandate/permission. Default earliest windows: three recipient-local business days after the verified invitation and seven recipient-local business days after the first verified follow-up. These are chosen product pacing defaults, not proven optimal conversion rates or platform-safe limits.

Do not send merely because the window elapsed. Re-evaluate whether there is useful information or a legitimate commitment. Silence after the final window closes the attempt as no response; never rotates numbers, creates new pursuits or changes briefs to reset the allowance. Unknown prospect timezone prevents unsolicited timed follow-up until resolved; immediate replies to a recent inbound can follow the active conversation. Read receipts never equal interest.

## J10: principal uses Chris on WhatsApp

Only the verified principal direct thread has control semantics. Natural-language briefing becomes a proposed version, followed by a concise summary and explicit confirmation of that version. “Pause” always pauses promptly when bound to the verified principal; a prospect's “pause” affects only their pursuit. “Resume” re-evaluates state but cannot enable a disabled external-autonomy switch, increase budgets or release old drafts.

The principal can ask who is being researched, why a candidate matters and which introductions completed. Answers use persisted source/state and do not announce a group as completed during receipt verification. Explicit principal corrections update public brief facts through a versioned command; ambiguous changes create a pending proposal rather than changing the active objective silently. Commands cannot be smuggled through quotations, forwarded messages or another group member.

Messages to the principal are still external sends. They use a separate bounded principal-communication scope and the same outbox/receipt discipline. If that scope is unavailable, the answer is available in-console; never invent a sent summary. Daily recap is optional, off by default; it is not necessary for the autonomous core outcome.

## J11: interruption, takeover and recovery

- **Customer pause:** stop new action dispatch; continue ingesting, suppressing and reconciling uncertain requests. Show in-flight uncertainty separately.
- **Customer manually messages a prospect from Chris's account:** detected outbound without a known verified/correlated action invokes takeover for that pursuit. Do not have bot and human both answer. Delayed possible assistant echo enters correlation first.
- **Resume after takeover:** principal reviews latest full owned thread and deliberately resumes that pursuit. Old drafts are cancelled and regenerated. No changes to unrelated people.
- **Customer changes brief:** cancel unstarted actions whose thesis/claims are affected; retain history, permissions and declines; requalify. A previously declined person is not revived by a new brief.
- **Provider disconnect or ban:** stop new writes, retain history and research; show reconnect/service restriction accurately. No automatic new-number substitution.
- **Model/search fails:** bounded retry for proven read-only operations, respect cost reservations; continue unrelated work. Show a specific provider issue rather than “Chris has nothing to do.”
- **Group created, intro not sent:** recover the exact group, verify it, send the remaining substantive message only if current checks pass. Never create a replacement group as a retry.
- **Unknown message/create result:** show “Checking whether this happened,” then “Needs reconciliation” if still unknown. No Retry Send button.
- **Principal disappears for days:** research within allowance continues; eligible autonomous work continues within mandate; missing material decisions affect only their dependent actions. No silent escalation of permissions.

## J12: corrections, deletion and operational exit

Identity corrections invalidate outstanding actions bound to the old identity. Keep a provenance trail and suppression against the old destination; never transfer consent to a new number by name matching. Merge duplicate *research records* only after exact identity proof; preserve both sources and history, resolve conflicting active pursuits without sending.

Account export includes brief versions, source references, dossiers, conversations, consent/authority records, action status and verified outcome references. Export escapes spreadsheet formulas if CSV is offered; JSON is the first supported format. Exports require owner role and contain only that account's data. Logs redact content and secrets.

For account closure, the product stops dispatch first, reports unresolved external actions, and offers an export and host-operated deletion runbook. This release does not introduce destructive automatic cloud deletion, retention claims or a new public billing cancellation system. Retain the minimal account-scoped suppression evidence under the host's configured retention policy; never promise that deleting a WACRM contact deletes messages already delivered to WhatsApp participants. A contact deletion prevents re-projection/recreation unless explicitly restored by the principal.

## Usability details that are acceptance requirements

Use accessible labels, keyboard focus restoration, live status announcements and reduced-motion support. Disable only the affected action, with a concrete reason. Form errors preserve drafts. Double-clicks, back/forward navigation, refresh after a timeout, two tabs editing the brief, mobile reconnect and expired sessions cannot duplicate work. Lists paginate; empty, loading, offline and error states differ. Timestamps show the customer's timezone with absolute time on hover/details; costs distinguish reserved, estimated and reported. Do not display fake precision for fit, consent or provider charges.
