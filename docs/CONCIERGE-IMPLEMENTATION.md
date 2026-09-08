# Concierge product implementation

Latest continuation: [IMPLEMENTATION-NEXT.md](IMPLEMENTATION-NEXT.md) records the durable
worker, sequences, prospect import, connection readiness, live approval integration and CRM
reconciliation. Scope below describes the first WACRM adoption checkpoint; the continuation
supersedes its statements about missing workers, sequencing and live approval endpoints.

Upstream WACRM MIT source pinned at 98b5bd26e8feacacfd4b74ff58411acb8154d212.
Implementation worktree: C:/wacrm-product, branch codex/concierge-product.
Fleet engine worktree: C:/wacwt, branch codex/wa-concierge-20260908.

This corrects the prior Fleet-only UI implementation. WACRM is the actual application
foundation and canonical product CRM. The product name has not been chosen.

## Acceptance contract

- Native account login, contacts/import/detail/notes, pipelines/deals and inbox work with
  persistent database records, not a replacement table or an in-memory mock API.
- Concierge onboarding, evidence-backed approach drafts, scoped permissions, introductions,
  timezone-aware scheduling, approvals and human takeover connect to the existing engine.
- Server resolves authenticated WACRM account and exact canonical contact; browser cannot
  select a Fleet bot, Unipile account or calendar credential.
- Direct verified messages appear in native inbox; groups remain in the concierge timeline.
- An explicit simulation workspace allows the full loop to be tested without external sends.
  Production account setup is distinct; simulation state cannot silently turn into live state.
- Original WACRM schemas, auth and RLS remain intact. No production database is migrated.

## Delivered

WACRM owns authenticated accounts, contacts, notes, imports, inbox conversations and
commercial pipelines in real local Supabase. Fleet owns concierge execution history.
The Concierge page supports a customer brief, contact-specific fit and source evidence,
editable approach drafts, scoped consent for each party, introductions, human takeover,
timezone-aware proposals and exact meeting approval. Optional AI drafts use the account's
existing BYO provider configuration; the initial editable draft is a template.

Server routes resolve the canonical account and contact. Native inbox composition stages
a reviewable draft. Native Meta send helpers are blocked while the bridge is configured,
preventing other modules from bypassing review. Verified direct messages mirror into the
native inbox idempotently; groups stay in the concierge timeline. Stale decisions cannot
execute and can be discarded. The local simulation runs the same execution checks.

## Verification

- WACRM: 88 files, 876 tests passing; TypeScript passes.
- Fleet bridge: 38 tests passing, including stale decisions and decline behavior.
- Broader concierge/calendar/approval regression run: 144 passing before the final
  additional bridge cases; final bridge suite rerun separately.
- Production webpack build succeeds; existing framework/edge-runtime warnings remain.
- Local Supabase schema verification passes.
- Local HTTP acceptance script verifies the consent-to-booking journey, inbox persistence,
  replay protection, STOP, CSRF, viewer restrictions and cross-account isolation in 61 requests.
- Browser checks cover login, setup, contact creation, native pipelines/inbox, drafts,
  recipient replies and mobile calendar no-overlap/meeting approval journeys.
  Screenshots and local QA report: `.local/qa/` (ignored).

## Boundaries

This is a local dogfood implementation, not a publicly deployed service. CRM persistence
and authentication are real; delivery, groups and bookings are explicitly simulated.
No external messages or invitations were sent. Existing auth, RLS, migrations and deploy
source were not edited. Upstream migrations ran only in the new local Docker database.

Live operation requires an owned number, linked transport account, real calendar bindings
and provider acceptance. The live bridge stages decisions; this UI does not grant itself
live sending authority. No new always-on inbound webhook worker was deployed; sync is explicit.
Upstream Meta campaigns and automations are not a Unipile sequence engine and are blocked
from sending under this configuration. Contact creation/import works; no Apollo-scale
owned database, public billing or hosted rollout was built. Manual drafts during takeover
require resuming the concierge or handling the conversation in the actual WhatsApp client.

See [TESTING-CONCIERGE.md](TESTING-CONCIERGE.md) for access and repeatable checks.
