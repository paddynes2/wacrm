# Autonomous execution and release runbook

> Implementation handoff update, 10 September 2026: T00-T19 are implemented in `736af8e`. Start with [testing and usage](HOW-TO-TEST-AND-USE.md) and [build results](BUILD-RESULTS.md). The instructions below are the preserved build mandate; do not restart implementation from scratch. The user subsequently authorized committing and pushing this branch, but not live activation or deployment.

## Build boundaries

The current user request authorizes this implementation plan and an autonomous software build following it. It does not authorize live outreach, number purchase/registration, third-party messages, secret edits, SQL/auth/RLS/billing/deploy changes or public deployment. Implement the mechanism and exact unavailable-state behaviour fully. Do not ask the user routine implementation questions; use the decisions in this plan. Never substitute unapproved external actions for missing test fixtures.

Keep all writes inside a new WACRM worktree. Do not edit `C:/Users/Patrick/OS`, `clients/`, `apps/external/` or the concurrent Agent Fleet checkout. Do not stage nested repositories into OS. Preserve existing dirty branches and do not force-reset or stash somebody else's work.

## Start a fresh implementation worktree

From an existing WACRM checkout, inspect `git status`, `git worktree list` and current plan commit. Choose an unused path/branch, for example:

```powershell
git -C C:/wacrm-chris-plan-20260910 worktree list
git -C C:/wacrm-chris-plan-20260910 worktree add C:/wacrm-chris-build-20260910 -b codex/chris-wa-build-20260910 codex/chris-wa-plan-20260910
```

If path/branch already exists, inspect and reuse only if it belongs to this task; otherwise choose a new suffixed name. Never delete/recreate an occupied worktree automatically. Once created, all implementation commands use that explicit working directory.

Read plan documents in README order. Run the source manifest check against its recorded baseline and the new worktree. Source hashes may differ because the user warned of concurrent Chris updates. Inspect changed code once, record substantive drift and adapt without restarting research or waiting for another session to finish. Do not read private Chris notebooks or import other customer data.

```powershell
python docs/CHRIS-WHATSAPP-PLAN/verify-plan.py --source-root C:/wacrm-chris-build-20260910
```

The checker is read-only. Exit0 means plan integrity and compared source hashes match; exit2 means source drift/unavailable source that must be inspected, not a reason to abandon the build; exit1 means a broken plan link/snapshot/task registry requiring repair. Current Fleet source drift is informational provenance; the captured reference remains the release contract.

## Dependencies and verification commands

Read `package.json`, lockfiles, Python requirements and installed Next docs before installs. Use the repository's locked dependencies (`npm ci`) in the isolated worktree when needed. Do not upgrade Next/React/TypeScript or introduce a framework migration. Python uses its own `.local/venv`; do not modify the global environment. If a compatible existing environment is reused read-only, record its exact interpreter.

Baseline/current Python command pattern:

```powershell
C:/wacrm-dogfood/.local/venv/Scripts/python.exe -m pytest concierge_service/tests -q -p no:cacheprovider
```

Run from the implementation worktree so imports exercise changed source. If creating a local venv, use the repository's lock (`concierge_service/requirements.txt` references `requirements.lock`). Read its bootstrap instructions before choosing installation commands. Tests receive fake provider transports; unset/inject configuration in the test process, not by editing canonical `.env`.

Frontend final checks, each separately recorded:

```powershell
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

Read actual scripts first; if they changed, use the exact current equivalents and record why. Typecheck may require Next type generation; follow installed version docs. A build requiring unavailable public configuration uses documented nonsecret test values in the child process only. Do not fabricate a successful production deploy from a local build.

Run narrow tests during each task, then full suites once all required work is integrated. Repeat full checks only after meaningful further changes/failures. Preserve old tests; do not weaken assertions or skip whole suites to get a green count.

## Offline integration environment

Use a new explicit SQLite path under implementation worktree `.local/chris-test/` and a separate blob directory. Initialize fake account UUIDs, fake principal/prospect identities and fixture provider configuration. Never reuse a live execution database or copy live permissions. All external HTTP in offline tests must be intercepted and unexpected network attempts must fail.

Start service using the repository's actual ASGI factory/startup pattern, extended for the Chris worker. Use OS-assigned free ports for test harnesses where possible. For a user-visible local browser run, inspect listening processes and repository port conventions first; do not collide with canonical8316 dogfood or another concurrent session. Run background helpers hidden on Windows. Record PID/port and stop only processes started by this build.

Seed fixtures through normal authenticated command/service interfaces, not by injecting completed outcomes into persistence. Replay search/read/model/provider responses through the real host logic. Open `/chris`, perform full brief-to-introduction flow, then verify WACRM projection with browser closed. Maintain synthetic test evidence clearly labelled.

## When something is missing

| Condition | Autonomous next step |
|---|---|
| No model/search credentials or approved allowance | Finish strict adapters and replay/eval harness; verify all fixtures; live capability remains unavailable. |
| No WhatsApp number/Unipile account | Finish identity/linking/status paths, transport tests and saga. Do not purchase or request OTP. |
| No principal WhatsApp control proof | Finish nonce flow in simulation; in-console workflow remains available. |
| No contact permission | Keep candidate researched/unapproached; test supported evidence paths; do not send a first permission-request message as a workaround. |
| Actual provider schema differs | Retain redacted evidence, implement a verified supported mapping if within v1; otherwise strict unavailable capability. Never guess fields or mix v2. |
| Missing Supabase access/index prerequisite | Finish projection adapter/fixtures; retain pending queue and exact readiness reason. No migration/auth edits. |
| Browser unavailable | Finish automated route/component tests; record browser QA not performed with exact error. Do not claim screenshots were checked. Use another permitted existing surface only if instructions allow. |
| Concurrent source changes | Compare relevant functions, preserve improvements, update build decision log; do not wait indefinitely. |
| Unrelated baseline test failure | Reproduce, record source/baseline status, continue scoped tests; fix if caused by implementation. |
| Actual defect in plan | Resolve using source/provider evidence and safest compatible choice, document one explicit correction; do not ask about routine engineering choices. |

Missing live dependencies are not a blocker to software completion. A failure in core logic/tests is a blocker to claiming implementation complete and must be fixed. Do not stop after writing an “unavailable” stub where the contract is implementable from verified docs and fixtures.

## Backup, restore and recovery

Before operating on a real existing execution store, use SQLite's backup API for a consistent copy; copying a WAL database file alone can lose committed data. Copy referenced blobs and a hash manifest. Test restore only into a distinct offline path. Never overwrite the live DB from this build.

Restored workspaces start with external authority off and an explicit restoration generation. Preserve all started/unknown/verified action evidence. Reconcile externally observed state before any possible later activation; a stale backup must never resurrect old queued sends. Document this as a restore procedure, not a silent migration or an automated live restoration command.

For unknown sends/groups, use `action.reconcile`, inspect exact action and observed provider references, follow05's schedule, and retain ambiguity. Never clear an action claim or manually change unknown to queued. For CRM repair, retry the projection only. For storage pressure, pause new work, export diagnostics and let the host increase capacity/archive under explicit operational control; never discard suppression or consent evidence to free space.

Account restrictions/reconnect: disable write readiness, preserve old generation, refresh account health and compare owner identity. Same owner reconnect still revalidates history and paused actions; changed owner invalidates bindings. Do not rotate to a new phone as a reliability tactic.

## Read-only preflight to implement

Add a CLI/module command that reports JSON plus concise text for: schema version, DB writable/size, blob integrity sample, worker heartbeat/lag, account configuration coverage, exact provider type/self/health if configured, principal distinctness, contact policy present, effective research/dispatch allowances, pending unknown actions, projection backlog and schema prerequisites when observable. It does not create chats, send messages, change settings, run paid research, touch secrets or mutate external accounts.

Exit codes:0 ready for the requested read-only capability,2 missing external configuration/evidence,3 corrupt/incompatible local state,4 provider read failure. Separate per-capability reasons so a missing WhatsApp link does not mark research code broken. Include `live_acceptance_verified=false` unless a real accepted test receipt exists.

## Live acceptance, only if separately authorized

Real acceptance requires a configured dedicated Chris account, a separately verified principal and a willing test prospect, applicable contact permission, explicit authorization of the concrete test and host settings. The implementation session must not infer those facts from this planning prompt. If no such authorization exists, skip live mutations and report them unperformed without asking the user to supply them during the autonomous build.

When authorized in a later session, use one willing test prospect, observe the initial invitation, their actual text agreement, exact group membership and substantive introduction, then verify CRM outcome. Include privacy/refusal/withdrawal/restart paths through controlled fixtures or consenting test actors; do not manufacture unexpected live group operations to test recovery. Capture redacted IDs/timestamps/hashes. Read/delivery claims require actual provider metadata; observed message is not proof the human read it.

## Final artifact contract

Create `docs/CHRIS-WHATSAPP-PLAN/BUILD-RESULTS.md` with:

1. Implementation worktree, branch, base and resulting commit IDs.
2. Task completion T00–T19 with substantive evidence and documented plan corrections.
3. Changed runtime file map and boundaries preserved.
4. Baseline/full test, typecheck, lint, build and UI outcomes with commands and output locations.
5. Matrix ID-to-test mapping and full completion trace from08.
6. Granular readiness: implemented, fixture-verified, live-observed or unavailable for each provider capability.
7. External setup/acceptance remaining, exact cause and already-implemented UI behaviour.
8. Any material limits, especially contact eligibility, first-degree coverage and bounded persistence.

Do not put credentials, real prospect private messages or database files in Git. Commit scoped code/docs in the isolated WACRM repository. No merge/push/deploy is necessary for this request. Final user message should state what was implemented and tested, link the results and name actual unverified live pieces. Do not claim “fully live,” “compliant everywhere” or “exactly once delivery” from fixtures.
