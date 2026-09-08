# Test the WhatsApp CRM

Open http://127.0.0.1:8316/concierge on Patrick's Windows machine.

- Email: `patrick@concierge.test`
- Password: `Concierge-Test-2026!`

These are local-only test credentials. This is standalone WACRM, not the Agent Fleet
dashboard. Data persists in local Supabase. The Simulation badge means no real WhatsApp
messages or calendar invitations are sent.

## Try it

New pages: `/prospects` imports sourced CSV with preview/selection; `/operations` creates
draft sequences, processes due work, reviews incoming suggestions and synchronizes CRM
outcomes; `/connections` shows what is configured and what is still unverified.
Start an opportunity and record contact eligibility before enrolling it in a sequence.
The local worker checks every 30 seconds. A finished queue job means a draft is staged,
not delivered. Follow-ups wait for the exact preceding verified message and stop on reply.
Use the Operations AI reply button only after configuring a provider; review/edit its
output before staging. Existing chat watches read providers only in live mode.

1. Open Contacts to inspect Bond and Stuart or add a contact. Open Pipelines for the
   seeded introduction pipeline and referral deal. Inbox contains saved test conversations.
2. Open Concierge. Add an opportunity from a CRM contact and record why it fits.
3. Edit the approach, record contact permission with its source, stage the draft, then
   approve in simulation. Confirm the message appears in Inbox.
4. Enter a reply in the simulation recipient panel. A positive reply does not grant every
   permission. Record the relevant permissions for both parties before introduction/scheduling.
5. Prepare an introduction and approve its pending decision in simulation.
6. Find a time: set dates, counterpart timezone and working hours. Los Angeles after 9 AM
   can show no overlap with ordinary South African hours. Overlapping hours return slots
   in both timezones. Select one, prepare the meeting and approve the exact proposal.
7. Inspect the simulated booking. Try STOP, takeover, stale decisions and Discard draft.

AI drafts require a provider in the existing AI settings. No provider key is configured
in this local test; editable template drafts work without it.

## Restart and verify

Docker Desktop must run. In `C:/wacrm-product`:

```powershell
npx supabase start
python scripts/seed-local-concierge.py
python scripts/local-concierge.py
```

If already running, just use the URL. The launcher refuses occupied ports. Process IDs
are in `.local/processes.json`; logs are `.local/web.log` and `.local/engine.log`.
It uses generated local Supabase keys in process environments, without creating `.env`
or loading OS credentials. Set `WACRM_FLEET_SOURCE` to another checkout's
`apps/internal/agent-fleet` if needed. New machines need `npm ci` and Fleet Python
dependencies installed. Do not reset the database to restart the application.

With the app running:

```powershell
npx tsc --noEmit
npm test -- --run
python scripts/test-local-concierge.py
python scripts/test-local-operations.py
```

The HTTP test creates separate local test accounts, permits only loopback requests and
does not overwrite Patrick's workspace. Run bridge tests from the Fleet engine folder:

```powershell
python -m pytest fleet/tests/test_wacrm_bridge.py -q
```

Live delivery still requires an owned assistant number, linked WhatsApp/Unipile account,
calendar configuration and provider acceptance. The old Virgin Active trial number has
not been verified. Public deployment and live sending are not part of this local test.
