# Chris dogfood workspace

Open `/dogfood` after signing into WACRM. The sidebar also links to **Chris dogfood**.

1. Save one offer, audience, geography, evidence-backed claims and budget in **Brief**.
2. In **Prospects**, select fictional fixtures for a repeatable exercise, or the configured treg provider for real research. Review source evidence and qualify or reject each person. Record attributed phone evidence before promoting a qualified person into CRM.
3. In **Conversation**, choose the person and let Chris initiate. Process queued work when needed. In simulation, type as the recipient and approve Chris's prepared actions locally.
4. Record each party's actual permissions with evidence. Prepare the introduction and explicit meeting proposal, then review their actions. Preparing a booking does not establish that it occurred.
5. Record usefulness, supervision time and corrections in **Review**. Inspect provider readiness, metrics and execution evidence in **Connections & pilot**.

Queued work refreshes automatically while pending. Follow-up and clock controls exercise due work in simulation; takeover exposes a manual simulated reply. Exact returned calendar slots can be selected for booking. After a verified simulated booking, reschedule/cancel preparation presents the proposed change and requires separate approval.

Pause/resume work, retry failed jobs after resolving their cause, preserve old history when starting a pursuit for a revised brief, and download the current pilot evidence as JSON. Live reply synchronization is read-only; no live execution button is exposed.

Browser verification on 2026-09-09 used isolated ports 8336/8337 and an isolated SQLite execution store with the existing local test login. The actual rendered workflow saved a QA brief, discovered 10 synthetic candidates, qualified one, initiated automatically, handled typed replies, recorded both-party permissions, approved an introduction, selected an exact returned calendar slot and approved its simulated booking. Backend read-back reported one introduction and one booking with zero provider spend. No CRM contacts were promoted and no external actions occurred. Screenshots remain in the testing worktree's ignored `.local/qa-*.png`; no browser errors were reported. Later amendment controls require the corresponding backend amendment implementation.

Simulation is visibly labeled. Fixture research is fictional and is not live contact verification. The model label comes from the service; configured research/model usage can incur costs. Live mode does not expose an external execution button.

The number path is Wabi number → registered WhatsApp account → Unipile → Chris. Number ownership, registration, pairing and controlled delivery still require real verification; configuration does not establish live acceptance.

## Integration boundary

The Next API retains existing verified account roles, same-origin checks and rate limits. Account and actor fields are derived server-side. Only allowlisted commands and fields cross the backend boundary. Prospects without usable phones stay in the execution store. CRM promotion looks up account-scoped normalized phone identity and inserts only when absent; it never overwrites an existing contact.

The backend owns durable execution, budget enforcement, state validation and simulated/live behavior. It must reject live external execution independently of the UI. GET reports must contain mode, brief, prospects, messages, decisions, jobs, metrics, readiness and events. POST results are followed by a fresh GET, with no automatic mutation retries.
