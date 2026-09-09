# Chris dogfood workspace

Open `/dogfood` after signing into WACRM. The sidebar also links to **Chris dogfood**.

1. Save one offer, audience, geography, evidence-backed claims and budget in **Brief**.
2. In **Prospects**, select fictional fixtures for a repeatable exercise, or the configured treg provider for real research. Review source evidence and qualify or reject each person. Record attributed phone evidence before promoting a qualified person into CRM.
3. In **Conversation**, choose the person and let Chris initiate. Process queued work when needed. In simulation, type as the recipient and approve Chris's prepared actions locally.
4. Record each party's actual permissions with evidence. Prepare the introduction and explicit meeting proposal, then review their actions. Preparing a booking does not establish that it occurred.
5. Record usefulness, supervision time and corrections in **Review**. Inspect provider readiness, metrics and execution evidence in **Connections & pilot**.

Simulation is visibly labeled. Fixture research is fictional and is not live contact verification. The model label comes from the service; configured research/model usage can incur costs. Live mode does not expose an external execution button.

The number path is Wabi number → registered WhatsApp account → Unipile → Chris. Number ownership, registration, pairing and controlled delivery still require real verification; configuration does not establish live acceptance.

## Integration boundary

The Next API retains existing verified account roles, same-origin checks and rate limits. Account and actor fields are derived server-side. Only allowlisted commands and fields cross the backend boundary. Prospects without usable phones stay in the execution store. CRM promotion looks up account-scoped normalized phone identity and inserts only when absent; it never overwrites an existing contact.

The backend owns durable execution, budget enforcement, state validation and simulated/live behavior. It must reject live external execution independently of the UI. GET reports must contain mode, brief, prospects, messages, decisions, jobs, metrics, readiness and events. POST results are followed by a fresh GET, with no automatic mutation retries.
