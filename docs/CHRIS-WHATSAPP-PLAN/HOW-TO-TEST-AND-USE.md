# Test and use Chris

Published branch: [paddynes2/wacrm - codex/chris-wa-build-20260910](https://github.com/paddynes2/wacrm/tree/codex/chris-wa-build-20260910). The local branch tracks the `patrick` remote; `origin` remains the upstream repository. If working on another machine, check out this branch and replace the Windows worktree path below with your checkout path.

Start with the offline walkthrough below. It uses the real application and Chris service with synthetic research, WhatsApp and CRM I/O. It needs no paid keys or WhatsApp number. The implementation is on branch `codex/chris-wa-build-20260910`, commit `736af8e`; subsequent commits update the handoff documentation.

Verified implementation results: 421 Python tests, 1,018 TypeScript tests, typecheck, lint, production build, desktop/mobile QA and backup/restore. See [build results](BUILD-RESULTS.md), [acceptance evidence](ACCEPTANCE-EVIDENCE.md) and [screenshots](QA-OBSERVATIONS.md). Live provider acceptance remains a separate step.

## 1. Start a fresh offline workspace

### Existing local session on Patrick's machine

Last verified **10 September 2026, 12:42 UTC**: both local servers were running, and the login page returned HTTP 200. Open [the login page](http://127.0.0.1:18762/login), sign in with `qa@example.test` / `synthetic-password`, then open [Chris](http://127.0.0.1:18762/chris). Do not start duplicate servers while this session is running.

This session uses `C:/wacrm-chris-build-20260910/.local/chris-manual/qa-demo.sqlite`. At verification it was a blank simulation workspace: no active brief, zero people or introductions, and external messaging disabled. Continue at **Give Chris an endeavour** below. The older build-verification databases are separate from this manual session.

The servers were started for the user after a connection-refused report. They are local development processes, not an installed service or an automatically starting deployment. If the page later refuses a connection, follow **Reopen an existing local workspace** below. A refused connection means there is no reachable listener; it is not a password error.

### Reopen an existing local workspace

First inspect the listeners:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 18761,18762 -ErrorAction SilentlyContinue |
    Select-Object LocalAddress,LocalPort,OwningProcess
```

If neither port is listening, start the service in one terminal using the existing database:

```powershell
Set-Location C:/wacrm-chris-build-20260910
$qaDatabase = Join-Path (Get-Location) '.local/chris-manual/qa-demo.sqlite'
if (-not (Test-Path -LiteralPath $qaDatabase)) {
    throw 'Existing workspace not found. Use the fresh-workspace instructions instead.'
}
& .local/venv/Scripts/python.exe -m concierge_service.tests.chris_qa_host --db $qaDatabase --port 18761
```

Then run the **terminal 2** environment/startup block below in a second terminal. If only one port is missing, investigate the process shown for the occupied port and start only the missing component after confirming it belongs to this worktree. Do not delete or reseed the existing database to restart. Reload the browser after Next reports Ready.

### Create another fresh workspace

Use three PowerShell terminals in `C:/wacrm-chris-build-20260910`. The installed dependencies and `.local/venv` already exist on Patrick's machine. In a fresh checkout, first run:

```powershell
npm ci --ignore-scripts --no-audit --no-fund
python -m venv .local/venv
& .local/venv/Scripts/python.exe -m pip install -r concierge_service/requirements-dev.txt
```

In terminal 1, check the two test ports and start the synthetic private service:

```powershell
Set-Location C:/wacrm-chris-build-20260910
if (Get-NetTCPConnection -State Listen -LocalPort 18761,18762 -ErrorAction SilentlyContinue) {
    throw 'A test port is occupied. Stop your previous test session or investigate before continuing.'
}
New-Item -ItemType Directory -Force .local/chris-manual | Out-Null
$qaDatabase = Join-Path (Get-Location) '.local/chris-manual/qa-demo.sqlite'
if (Test-Path -LiteralPath $qaDatabase) {
    throw 'This demo database already exists. Reopen it to inspect it, or choose a new qa- filename in all three terminals for a fresh replay.'
}
& .local/venv/Scripts/python.exe -m concierge_service.tests.chris_qa_host --db $qaDatabase --port 18761
```

Keep that terminal running. In terminal 2, start Next with process-only synthetic settings:

```powershell
Set-Location C:/wacrm-chris-build-20260910
$env:NEXT_PUBLIC_SUPABASE_URL = 'http://127.0.0.1:18761'
$env:NEXT_PUBLIC_SUPABASE_ANON_KEY = 'synthetic-qa-key'
$env:SUPABASE_SERVICE_ROLE_KEY = 'synthetic-service-role-key'
$env:WACRM_BRIDGE_URL = 'http://127.0.0.1:18761'
$env:WACRM_BRIDGE_TOKEN = 'synthetic-chris-qa-token-not-a-real-credential'
npm run dev -- --hostname 127.0.0.1 --port 18762
```

These are fixture values, not real credentials. Do not point this fixture at a real Supabase or WhatsApp service. No `.env` file is needed.

Open **http://127.0.0.1:18762/login** and sign in with:

- Email: `qa@example.test`
- Password: `synthetic-password`

Then open **http://127.0.0.1:18762/chris**. You should see Simulation, messaging off and no people. The fixture does not run a continuous worker, so Worker unavailable can appear after its initial heartbeat expires. This is expected in this manually advanced walkthrough.

## 2. Give Chris an endeavour

Under **Talk to Chris**, enter `Find distribution partners for a public software offer.` and click **Send to Chris**. Review the proposal using these fixture-compatible values:

- Public name: `Alex`
- Public background: `Alex builds software for distributors.`
- Operating timezone: `Europe/London`
- Leave geography unspecified to allow global research.

Click **Start research**. This activates the brief; it does not enable real messaging. Without configured model/search providers, the offline walkthrough waits for the synthetic research stage below.

## 3. Walk through the actual introduction flow

In terminal 3:

```powershell
Set-Location C:/wacrm-chris-build-20260910
$qaDatabase = Join-Path (Get-Location) '.local/chris-manual/qa-demo.sqlite'
$qaPython = Join-Path (Get-Location) '.local/venv/Scripts/python.exe'
& $qaPython -m concierge_service.tests.chris_qa_replay --db $qaDatabase research
```

Open **People**. Maya Chen should appear with a sourced dossier and visible uncertainty. The research stage invokes the real tool loop against deterministic model/search I/O.

Run each following stage once, inspecting the page between stages:

```powershell
& $qaPython -m concierge_service.tests.chris_qa_replay --db $qaDatabase invite
& $qaPython -m concierge_service.tests.chris_qa_replay --db $qaDatabase consent
& $qaPython -m concierge_service.tests.chris_qa_replay --db $qaDatabase complete
& $qaPython -m concierge_service.tests.chris_qa_replay --db $qaDatabase projection
```

The `invite` stage supplies synthetic principal/identity/contact proof and enables only synthetic scoped actions. `consent` supplies the observed recipient's reply. `complete` runs the real group saga. `projection` calls the real private Next CRM callback. Normal connected operation obtains these observations from providers and the worker instead of these terminal stages.

Expected result:

- **People:** one researched and introduced person, with the observed direct conversation.
- **Introductions:** one verified introduction containing Chris, Alex and Maya; both the group creation and substantive message are verified.
- **CRM:** the pending count clears. The fixture persists one contact, two notes, one direct conversation and two messages in `.local/chris-manual/qa-demo.crm.json`.
- **Evidence:** `.local/chris-manual/qa-demo.completion.json` records three wire receipts, one completed outcome and five acknowledged projections. The stage asserts those counts.

The fake CRM implements the reads/writes needed for this acceptance replay, not every CRM module. Use its JSON and the Chris UI to inspect this test. Existing evidence from the completed build is also committed under [build-evidence](build-evidence/).

For ambiguity testing on a separate fresh replay, insert `ambiguous` between `invite` and `consent`; it must not grant group permission. For partial-group testing, use `partial` before `complete`, inspect the missing-member state, wait at least 60 seconds for the persisted retry time, then run `complete`. Do not repeatedly run mutation stages against an already completed replay; use a new `qa-` database name to start over.

Finish by clicking **Pause Chris**, then in **Settings** click **Turn messaging off** if enabled. Press Ctrl+C in terminals 1 and 2. Keep the simulation files for inspection; starting another fresh replay does not require deleting them.

## 4. Run automated checks

Stop the development server before the production build because both use `.next`:

```powershell
Set-Location C:/wacrm-chris-build-20260910
& .local/venv/Scripts/python.exe -m pytest concierge_service/tests -q
npm test
npm run typecheck
npm run lint -- --quiet
$env:NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
$env:NEXT_PUBLIC_SUPABASE_ANON_KEY = 'synthetic-build-key'
npm run build
```

These public build placeholders satisfy existing login/reset page prerendering. They do not connect a production account. The Python Chris tests reject unexpected external network access.

## 5. Use Chris with connected services

Connected operation needs the existing WACRM account/auth/CRM installation plus the dedicated private Python service. The [operations guide](OPERATIONS.md#host-configuration-contract) lists exact host inputs; configuring credentials or linking a real WhatsApp number was not part of this build or push.

The host must provide the account-keyed model/search settings and price ceilings, paid allowance, Unipile v1 account, private bridge token, persistent execution database, trusted CRM callback origin and enabled worker. It must also verify the actual account/self identity, history/member schema and installed CRM constraints. Research can operate before WhatsApp setup is complete.

Once the host is connected:

1. Sign into your normal WACRM account and open `/chris`.
2. Describe and review your endeavour, public context, exclusions and timezone.
3. Let Chris research; inspect **People** for reasons, sources, gaps and relationship coverage.
4. In **Settings**, verify Chris's dedicated number. Generate a control code and send it directly to Chris from your separate principal number.
5. Resolve recipient identity and retain actual WhatsApp contact permission. A public phone number alone is insufficient.
6. Review the future messaging scope and limits. Only the owner can enable it. Keep it off until a separately authorized controlled live test is ready.
7. Once enabled and eligible, the worker handles invitations, replies, exact group consent, membership verification, the substantive introduction and CRM projection without an open browser.

Use **Pause Chris** to stop new actions; in-flight requests may still need observation. Use **Take over** to handle an individual conversation, then resume only after reviewing the latest thread. For an uncertain send, use **Check whether this happened**, not another send. A group without the verified substantive message is a partial outcome, not a completed introduction. See [recovery](OPERATIONS.md#pausing-and-recovery) for the exact procedures.
