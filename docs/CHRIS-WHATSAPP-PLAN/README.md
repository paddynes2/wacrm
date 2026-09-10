# Chris in WhatsApp: implementation contract

Status: BUILD PLAN, not an implementation or live-launch acceptance.
Prepared: 10 September 2026. Executable baseline: WACRM `e4d0525`; checked-out documentation baseline: `657ab22`.

## The product

A customer tells Chris what economic endeavour they are pursuing. Chris reasons about who could advance it, finds people resourcefully, researches their relevance, establishes a trustworthy contact route, and asks the person on WhatsApp whether they want an introduction to the customer. If the person agrees to a WhatsApp group, Chris creates a group containing exactly Chris, the customer and that person, writes a useful introduction, and hands over.

The primary outcome is **a verified introduction in the intended three-person group**. It is not a sent invitation, a positive reply, a booked meeting or a self-reported model success. Multiple candidates progress concurrently. The customer's mandate authorizes routine candidate selection; there is no recurring approval of every research result or introduction candidate.

Chris's commercial judgement and research method come from the reviewed Fleet behaviour. The product runs independently: its own accounts, secrets supplied by its host, persistence, worker, WhatsApp identity and UI. No Fleet process, OS notebook, Patrick-specific private dossier, peer agent, AgentMail inbox or personal browser session is a runtime dependency. RevenueBase is explicitly out of scope.

## Read and implement in this order

1. [Verified source audit](01-SOURCE-AUDIT.md): what exists, what was actually read and tested, and what remains unverified.
2. [Product decisions and user journeys](02-PRODUCT-AND-JOURNEYS.md): the customer and prospect experiences, including the difficult branches.
3. [Contracts, persistence and state](03-CONTRACTS-AND-STATE.md): data, commands, invariants, ownership, concurrency and compatibility.
4. [Chris reasoning and research](04-CHRIS-REASONING.md): portable behaviour, tools, dossiers, ranking and budget control.
5. [WhatsApp, consent and recovery](05-WHATSAPP-AND-RECOVERY.md): inbound interpretation, exact identity, introduction saga and uncertain sends.
6. [WACRM UI and API](06-WACRM-UI-AND-API.md): routes, components, roles, principal chat and CRM projection.
7. [Ordered implementation tasks](07-IMPLEMENTATION-TASKS.md): dependency order, file ownership, outputs and verification.
8. [Acceptance matrix](08-ACCEPTANCE-MATRIX.md): adversarial and ordinary scenarios with observable assertions.
9. [Provider contracts and external constraints](09-PROVIDERS-AND-CONSTRAINTS.md): primary sources, version boundaries and setup facts.
10. [Execution and release runbook](10-EXECUTION-RUNBOOK.md): autonomous build, missing-dependency fallbacks, recovery and completion evidence.
11. [Fresh-session prompt](FRESH-SESSION-PROMPT.md): the complete handoff instruction.

`source-manifest.json` pins actual file bytes. Behaviour snapshots under `reference/` are provenance for the plan, not product instructions to execute verbatim. `04-CHRIS-REASONING.md` specifies the adapted product behaviour and its deliberate differences.

[Plan validation](PLAN-VALIDATION.md) records the completed checks. Run `python docs/CHRIS-WHATSAPP-PLAN/verify-plan.py --source-root <worktree>` at build start; its CRLF-aware comparison distinguishes Windows checkout formatting from real source drift.

## Definitions that settle scope

| Term | Exact meaning |
|---|---|
| Account | Existing WACRM tenant UUID from authenticated server context. Never supplied as authority by a browser or model. |
| Principal | One verified customer identity and WhatsApp number per account in this release. Patrick is the initial customer, not a hard-coded product identity. |
| Chris | The product-owned assistant, using a dedicated connected WhatsApp account distinct from the principal. |
| Brief | Versioned economic objective, public principal context, exclusions and operating constraints. One active brief per account; history retained. |
| Mandate | Customer-authorized scope for future research and, separately, future eligible external actions. Host-owned and revocable. |
| Contact permission | Evidence that the recipient may be contacted through this WhatsApp business identity. Discovery, enrichment and principal authorization do not establish it. |
| Introduction permission | Recipient agreement to this introduction to this named principal. |
| Group permission | Recipient agreement to a group with Chris and that principal, including visibility of their number to the principal. |
| Introduced | Exact group membership and the substantive outbound introduction message independently verified and durably recorded. |
| Build complete | All specified software, offline provider contracts, acceptance tests and local UI verification complete. |
| Live accepted | Separate controlled test against a real configured account, authorized test recipients and verified provider observations. Not established by this plan. |

## Binding choices, not hidden assumptions

This plan makes explicit engineering/product choices wherever the user did not supply a preference. They are decisions for implementation, not claims about existing code or provider guarantees. Do not ask the user to choose architecture, libraries, routes or retry policies again.

- Extend the existing WACRM Next.js application and Python concierge service. Use the existing SQLite workspaces/jobs schema without SQL or Supabase migrations in this release. Introduce a versioned `chris_v1` namespace in each workspace document. This is a bounded single-host first release, not an unbounded distributed service.
- Add a new Chris workflow and UI while preserving tested legacy dogfood/calendar behaviour. Share provider primitives, validators and CRM helpers; do not fork the entire application or rewrite the legacy reducer.
- Pin Unipile **v1** for the implementation because that is the existing executable adapter. Do not mix v2 paths or response shapes into it. Treat v1 live contract confirmation as a capability requirement. A provider incompatibility produces a disabled capability with evidence, not speculative endpoint guessing.
- Use Exa search and contents as the initial standalone public research adapter, existing Treg phone enrichment as optional secondary enrichment, and existing configured model transports. No RevenueBase, Fleet tools, logged-in LinkedIn browsing or generic shell/browser automation in the product agent.
- Use host-controlled structured model turns with a strict one-step action schema. The model proposes research, judgements and prose. Code owns scheduling, recipient identity, permissions, arithmetic, state transitions and dispatch.
- The console supports complete onboarding and operation; a verified principal's WhatsApp thread supports briefing, progress, pause and ordinary follow-through. The authenticated console remains the authority surface for enabling external autonomy and changing identity/provider binding.
- Default to research enabled when configured and a valid brief is active; external autonomy starts off. Building the switch and its dispatcher is in scope. Activating real sending, spending, provisioning or account registration during the build is not implied by an autonomous coding request.
- No calendar, meeting, billing, public signup, payment collection, public deployment, new RLS policy or automatic database migration is required for the core product outcome. Existing optional calendars must continue to pass their tests.

## The material business constraint

The ideal “find any number and immediately send the first commercial WhatsApp” journey cannot be assumed available. WhatsApp's published Business Messaging Policy requires recipient contact permission; the regular Messenger route is not established here as an exemption or a guarantee of permitted automation. Unipile connectivity does not confer that permission. See [the researched policy and implementation consequence](09-PROVIDERS-AND-CONSTRAINTS.md).

The software therefore supports autonomous research for all eligible candidates and autonomous WhatsApp introductions for contact-eligible candidates. Unknown contact permission is a visible acquisition gap, not fabricated opt-in and not a reason to halt other research. An inbound prospect, a prospect who has opted in through an existing customer channel, or a properly evidenced imported permission can enter the automated invitation journey. Do not quietly substitute email outreach or buy a new source to hide this gap.

## Build acceptance, all required

- The end-to-end fixture journey starts with a fresh brief and discovers a person through actual search/read tool calls in a controlled replay, produces an evidenced thesis, invites an eligible recipient, interprets their answer, obtains any missing group permission, creates/verifies a three-person group, sends/verifies the substantive introduction, projects the result into WACRM and stops ordinary proactive follow-ups.
- Research continues while other people are awaiting replies, permission, identity resolution, provider recovery or manual takeover.
- No untrusted message, source page, model result, browser-supplied tenant ID or old approval can create authority or a verified receipt.
- Crash/restart, duplicate inputs, delayed echoes, unknown provider responses, stale brief revisions and concurrent STOP/pause inputs satisfy the acceptance matrix.
- The first-run, active, empty, waiting, paused, offline, partly successful, storage-pressure and recovery UI states work on desktop and mobile.
- All baseline tests remain green; new tests prove behaviour at persistence and transport boundaries, not just function return shapes. Build, typecheck and lint results are recorded separately.
- A fresh session produces implementation commits, `BUILD-RESULTS.md`, test output references and any external setup gaps. It does not stop after scaffolding, mocks alone, a pretty screen or a plan update.

## Updating this plan

If code has changed concurrently, compare the manifest, read the changed implementations and preserve improvements. Reconcile factual drift into a short build decision log before editing overlapping code. Do not endlessly chase the concurrent Fleet branch: the captured behaviour is the explicit reference for this release. A newly discovered provider restriction must tighten capability readiness and be recorded; it cannot be silently replaced by an invented successful path.
