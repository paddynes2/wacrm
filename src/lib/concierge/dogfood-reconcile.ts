import type { SupabaseClient } from '@supabase/supabase-js';
import { BridgeError, isUuid } from './bridge';
import { reconcileConcierge } from './reconcile';

type Row = Record<string, unknown>;
const object = (value: unknown): value is Row =>
  !!value && typeof value === 'object' && !Array.isArray(value);
const nonempty = (value: unknown): value is string =>
  typeof value === 'string' && !!value.trim();
const phone = (value: unknown): string | null =>
  typeof value === 'string' && /^\+[1-9]\d{7,14}$/.test(value)
    ? value.replace(/\D/g, '')
    : null;
function invalid(): never {
  throw new BridgeError('Dogfood CRM evidence is incomplete or inconsistent.', 502);
}

/** Convert execution evidence into the existing idempotent CRM projection.
 * The authenticated agent route supplies ctx; no contact creation or sends occur here.
 */
export async function reconcileDogfood(
  ctx: { supabase: SupabaseClient; accountId: string; userId: string },
  report: unknown
) {
  if (!object(report) || report.account_id !== ctx.accountId ||
      !['simulation', 'live'].includes(String(report.mode)) ||
      !Array.isArray(report.prospects) || !Array.isArray(report.messages) ||
      !Array.isArray(report.timeline)) invalid();
  const prospects = new Map<string, Row>();
  const linked = new Map<string, string>();
  let unlinked = 0;
  for (const p of report.prospects) {
    if (!object(p) || !nonempty(p.id) || prospects.has(p.id)) invalid();
    prospects.set(p.id, p);
    if (!p.contact_id) { unlinked++; continue; }
    const normalized = phone(p.phone);
    if (!isUuid(p.contact_id) || !normalized) invalid();
    if (linked.has(p.contact_id) && linked.get(p.contact_id) !== normalized) invalid();
    linked.set(p.contact_id, normalized);
  }
  // Account ownership alone is insufficient: a stale link must not put Alice's
  // transcript into another contact's inbox after that contact's phone changed.
  const owned = new Set<string>();
  const requested = [...linked.keys()];
  for (let i = 0; i < requested.length; i += 200) {
    const batch = requested.slice(i, i + 200);
    const result = await ctx.supabase.from('contacts').select('id,account_id,phone,phone_normalized')
      .eq('account_id', ctx.accountId).in('id', batch);
    if (result.error || !Array.isArray(result.data))
      throw new BridgeError('CRM contact bindings could not be verified. Retry reconciliation.', 503);
    for (const contact of result.data) {
      if (!object(contact) || !isUuid(contact.id) || contact.account_id !== ctx.accountId || !batch.includes(contact.id)) invalid();
      const actual = phone(contact.phone) ?? (typeof contact.phone_normalized === 'string' ? contact.phone_normalized : null);
      if (actual !== linked.get(contact.id)) invalid();
      owned.add(contact.id);
    }
  }
  const direct_messages: Row[] = [];
  const directPurposes = new Set(['approach', 'reply', 'manual', 'schedule', 'booking_link']);
  const skipped = { unlinked_prospects: unlinked, group_or_nonmessage: 0, future_simulation_messages: 0 };
  for (const message of report.messages) {
    if (!object(message) || !nonempty(message.prospect_id)) invalid();
    const prospect = prospects.get(message.prospect_id);
    if (!prospect) invalid();
    if (!isUuid(prospect.contact_id) || !owned.has(prospect.contact_id)) continue;
    if (message.group === true || !directPurposes.has(String(message.purpose))) {
      skipped.group_or_nonmessage++;
      continue;
    }
    if (message.simulated !== (report.mode === 'simulation') || !nonempty(message.id) ||
        !nonempty(message.text) || !['inbound', 'outbound'].includes(String(message.direction))) invalid();
    const stamp = message.provider_timestamp ?? message.created_at;
    if (!nonempty(stamp) || !/(Z|[+-]\d{2}:\d{2})$/.test(stamp) || !Number.isFinite(Date.parse(stamp))) invalid();
    if (Date.parse(stamp) > Date.now() + 60_000 && message.simulated === true) {
      // The simulator can advance time; never rewrite its evidence to today's time.
      skipped.future_simulation_messages++;
      continue;
    }
    if (report.mode === 'live' && (!nonempty(message.chat_id) || !nonempty(message.source_ref))) invalid();
    direct_messages.push({ contact_id: prospect.contact_id, id: message.id, text: message.text,
      direction: message.direction, manual: message.purpose === 'manual',
      occurred_at: stamp, chat_id: message.chat_id ?? `dogfood:${prospect.id}`,
      simulated: report.mode === 'simulation' });
  }
  const timeline: Row[] = [];
  for (const event of report.timeline) {
    if (!object(event) || !object(event.data) || !nonempty(event.pursuit_id) ||
        event.account_id !== ctx.accountId) invalid();
    const prospect = prospects.get(event.pursuit_id);
    if (!prospect) invalid();
    if (!isUuid(prospect.contact_id) || !owned.has(prospect.contact_id)) continue;
    timeline.push({ ...event, pursuit_id: `wacrm:${prospect.contact_id}` });
  }
  const result = await reconcileConcierge(ctx, {
    workspace: { account_id: ctx.accountId }, mode: report.mode, direct_messages, timeline,
  });
  return { ...result, skipped,
    status: result.status === 'partial' || owned.size !== linked.size || skipped.future_simulation_messages
      ? 'partial' : result.status,
    unverified_contact_links: linked.size - owned.size };
}
