# Operating Chris

For a first run, use [Test and use Chris](HOW-TO-TEST-AND-USE.md), which includes complete PowerShell commands and the synthetic login.

Use `/chris` for briefing, people, introductions and settings. `/dogfood` remains available for legacy calendar and simulator work. The existing private Python ASGI factory composes both workflows; set the already-documented worker input in the host environment when operating it. No deployment or environment files are changed by this implementation.

Live sending starts off. A verified distinct principal, connected dedicated WhatsApp identity, current brief, retained contact permission and the owner’s future-action setting are all required. A paid allowance defaults to zero. Public phone discovery is not contact permission. Unknown contact and relationship coverage remain visible gaps.

## Host configuration contract

Install `concierge_service/requirements-dev.txt` for development or `requirements.lock` for runtime. The added phone parser is `phonenumbers==9.0.38` (Apache-2.0); parsing only establishes possible international syntax, never ownership or contact permission. No default country is inferred.

Use the existing account-keyed `CONCIERGE_MODELS_JSON` and `CONCIERGE_DISCOVERY_JSON` host inputs. Each configured model/search entry additionally requires a positive integer `max_operation_micro_usd`, a conservative upper reservation for one call. Missing price ceilings show `provider_price_ceiling_unverified` and disable paid work. Model entries need provider (`openai` or `anthropic`), model and API key; public search uses provider `exa` and its API key. Supply these through the host's established secret mechanism, not a committed file.

`CONCIERGE_CHRIS_SETTINGS_JSON` supplies account-keyed `daily_micro_usd`, `job_micro_usd`, `daily_operations`, timezone and permitted lower operating limits. Default paid allowance is zero. Reservations are cumulative per job and per local calendar day; timeout/unknown cost is retained, never refunded by assumption. A reported price above the reserved ceiling pauses research for host attention. The owner can reduce the host allowance through Settings.

The ASGI `application()` factory installs the scoped product authorizer. `create_app()` intentionally has no external authorizer by default. `CONCIERGE_WORKER_ENABLED=1` enables the independent worker. `CONCIERGE_WACRM_INTERNAL_URL` is the fixed trusted WACRM origin for automatic projection/relationship callbacks; `WACRM_BRIDGE_TOKEN` protects both directions. The Next host uses its existing service client, account ownership and installed contact/conversation/message constraints. No schema change is performed.

Optional principal WhatsApp status replies require both the separate principal-message setting and `principal_reply` authority. Console chat remains available without this setting or a WhatsApp connection. Non-English, conditional, media and ambiguous permission remain explicit attention gaps; a bare later yes cannot silently erase an unresolved condition. A current, exact-question-bound "Yes, I agree unconditionally" can resolve it only after semantic evidence validation; the original condition and resolving event remain recorded. Reviewed pursuit resume clears operator pause while retaining the recorded not-before time.

## Diagnosis

Run `python -m concierge_service.chris.preflight --db <absolute existing SQLite path>` for a read-only local integrity report. It does not contact providers, spend, change configuration or send messages. Code 0 means local inspection passed, 2 means no configured Chris account, 3 means local corruption/unavailability. Local success does not establish live provider acceptance.

Review the overview readiness fields independently: research configuration, WhatsApp, principal, external authority, worker heartbeat, projection and storage. Missing bridge configuration gives the UI a disconnected state. Missing model/search allowance disables paid work. Provider identity changes invalidate principal/permission applicability and cancel unstarted actions. Reconnect the configured identity rather than rotating sender numbers.

## Pausing and recovery

Pause in the console. This cancels unstarted drafts/actions; it cannot recall an in-flight provider request. Ingestion and reconciliation continue. Never edit a `started` or `unknown` action back to queued. Use its reconciliation action, which performs read-only observations. Repeated absence is not proof of non-execution. More than one matching receipt needs attention.

A group that exists without a verified substantive introduction is a partial result. Inspect exact members. Do not create a replacement group or add participants to bypass privacy settings. Withdrawal before the substantive message cancels the remaining work.

CRM repair uses projection retry only. The private callback is a wakeup containing immutable projection IDs, then WACRM fetches source facts and verifies their digest. It never forwards a WhatsApp resend. Missing database constraints or ownership mapping leave the projection pending; do not apply historical SQL migrations to clear the warning.

Contact creation is claimed durably before CRM insertion. `contact_creation_uncertain` means the claim exists but its deterministic contact cannot be read back. Inspect the account's CRM and source event before any repair; do not clear the claim to force recreation. A deleted acknowledged contact becomes a tombstone. An externally changed phone yields `crm_identity_changed`, preventing transcript misfiling. Retry reuses deterministic note/message IDs after a lost acknowledgement.

## Backup and restore

Stop the worker before an operational backup. Use `concierge_service.chris.preflight.backup(database, new_directory)`, which uses SQLite backup and copies content-addressed blobs with a checksum manifest. Keep the backup private; it contains account evidence. Never copy only a live SQLite file while its WAL is active.

The automated `restore(backup_directory, new_directory)` utility is for simulation rehearsals only. It refuses an existing destination, checks hashes and disables external authority in restored workspaces. Started/unknown/verified action history remains intact. Live restoration requires a separately authorized host procedure with dispatch disabled, the same verified identity and external reconciliation before any later activation. A stale backup must not resurrect old sends.

At 8 MiB new discovery pauses; at 12 MiB new paid research and outbound stop. The 16 MiB ceiling reserves no false acknowledgement: a write that cannot persist fails. Export and have the host adjust capacity; do not delete suppression, consent or action evidence to clear space. The first release is single-host and bounded.

## Live acceptance

This build does not purchase/link numbers or activate live outreach. A later controlled test needs a dedicated account, principal control proof, willing recipient, retained contact permission, configured paid allowance if needed, and explicit authorization of that test. Verify actual group membership and substantive receipt independently. Observed sent is not the same as delivered or read.

For a later authorized qualitative research evaluation, `python -m concierge_service.chris.evaluation --help` describes the opt-in harness. Its default report is read-only; paid research requires its explicit flag and configured allowance. It does not schedule or execute WhatsApp dispatch. The offline six-endeavour fixtures establish host progression and evidence boundaries, not live model judgment quality.

## Reproduce offline verification

For the loopback harness, set the Next process's public Supabase URL and `WACRM_BRIDGE_URL` to `http://127.0.0.1:18761`, use synthetic public/service-role keys, and use the synthetic `TOKEN` constant from `concierge_service/tests/chris_qa_host.py` for `WACRM_BRIDGE_TOKEN`. Start Next with `npm run dev -- --hostname 127.0.0.1 --port 18762`. These fixture values have no authority at any external service.

After activating a brief in the UI, run `python -m concierge_service.tests.chris_qa_replay --db <same synthetic database> <stage>` for `research`, `invite`, `consent`, `complete`, then `projection`. The last stage uses the real private callback and asserts three wire receipts, five acknowledgements and one completed introduction. `ambiguous` and `partial` are optional inspection stages; partial membership obeys its persisted retry timer. Finish with `pause` and disable the synthetic messaging switch. Stop only the test processes you started.

Run `python -m pytest concierge_service/tests -q`, `npm test`, `npm run typecheck`, `npm run lint -- --quiet`, and `npm run build`. A build without installed Supabase configuration needs synthetic process-only public URL/key values for prerendering the existing login/reset pages. No real credentials are needed.

The optional loopback UI harness is `python -m concierge_service.tests.chris_qa_host --db <worktree>/.local/qa-new.sqlite --port 18761`; it refuses paths outside `.local` or filenames without `qa-`. Run Next on an independently checked free port with the matching synthetic bridge/Supabase process environment. Use only `qa@example.test` and a synthetic password. The fixture persists CRM I/O beside its simulation DB, and never accesses external Supabase or WhatsApp. See the build results for the tested process variables and replay sequence.
