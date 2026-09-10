# Fresh-session implementation prompt

> Implementation handoff update, 10 September 2026: T00-T19 are implemented in `736af8e`. Start with [testing and usage](HOW-TO-TEST-AND-USE.md) and [build results](BUILD-RESULTS.md). The instructions below are the preserved build mandate; do not restart implementation from scratch. The user subsequently authorized committing and pushing this branch, but not live activation or deployment.

Copy the text below into a fresh coding session with filesystem access to this machine.

---

Implement the standalone **Chris in WhatsApp** product completely, using the code-grounded build contract at:

`C:/wacrm-chris-plan-20260910/docs/CHRIS-WHATSAPP-PLAN/README.md`

Read every linked plan document in order, including the source manifest, then execute T00–T19. This is an implementation request, not another planning session. Work autonomously without asking me routine questions. Make the documented choices, fix required defects and complete the software, tests, local UI verification and build report. Do not stop after scaffolding, a mock UI or a happy-path demonstration.

The product: a customer supplies an economic endeavour; Chris reasons, resourcefully discovers people, researches fit, invites contact-eligible prospects on WhatsApp to meet the customer, obtains exact agreement to the named three-person WhatsApp group, creates/verifies the group, posts/verifies a useful introduction, and hands over. Multiple prospects progress concurrently. The principal's mandate covers routine candidate choices. RevenueBase is out of scope. Calendars are optional existing functionality, not the core completion criterion.

WACRM source was reviewed at `C:/wacrm-dogfood`, executable checkpoint `e4d0525`, documentation base `657ab22`. The plan lives on branch `codex/chris-wa-plan-20260910` in the separate WACRM repository. Create an isolated implementation worktree from that plan branch. Preserve all other worktrees and dirty changes. Chris in Agent Fleet is being edited concurrently; use the plan's captured behaviour, compare relevant drift once and do not depend on Fleet at runtime or change its files.

The plan explicitly authorizes building the product's autonomous authority mechanism. It does not activate real sending. During this build do not send live messages, buy/register numbers, incur unapproved provider spend, edit secrets/.env/auth/RLS/migrations/billing/deploy configuration, merge, push or publish. Use the already-existing authorized configuration read-only where available. Missing external setup must not halt implementable work: finish the real adapters, state machines, fixture replay, unavailable/recovery UI and tests; then report live acceptance as unverified. Do not fabricate phone ownership, contact permission, provider schema, charges or receipts.

Use the existing WACRM Next.js application and standalone Python service. Preserve the legacy dogfood/calendar tests. Follow the plan's Unipile v1 contract, bounded standalone research/tool loop, versioned persistence, exact consent, durable outbox, unknown-delivery reconciliation and automatic CRM projection. Never bypass safety/state checks with an always-allow callback, import the OS/Fleet runtime or substitute a first unsolicited permission-request message for the documented contact-eligibility requirement.

Inspect executable code before changing it. If a plan detail conflicts with verified current code/provider facts, resolve it with a documented minimal correction and continue. Keep `BUILD-RESULTS.md` current, map every acceptance ID to test/evidence, run the full appropriate tests/typecheck/lint/build, inspect desktop/mobile flows and fix regressions. Use fake provider transports that fail on unexpected network access; simulation mode alone does not guarantee no spend.

Commit scoped implementation in the isolated worktree. Finish with concise results, the worktree/commit and a link to `BUILD-RESULTS.md`, distinguishing implemented and fixture-verified software from any genuinely unperformed live acceptance. No input from me is required to finish the authorized build.
