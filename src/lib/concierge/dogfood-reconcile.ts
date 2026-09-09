import type { SupabaseClient } from '@supabase/supabase-js';
import { createHash } from 'node:crypto';
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
  const outcomes = report.amendment_outcomes ?? [];
  if (!Array.isArray(outcomes)) invalid();
  const amendmentNotes = new Map<string, { id: string; account_id: string; contact_id: string; user_id: string; note_text: string; created_at: string }>();
  for (const event of outcomes) {
    if (!object(event) || event.kind !== 'calendar_amendment_verified' || !nonempty(event.id) ||
        !nonempty(event.prospect_id) || !nonempty(event.booking_id) ||
        !['cancel', 'reschedule'].includes(String(event.operation)) ||
        typeof event.digest !== 'string' || !/^[a-f0-9]{64}$/.test(event.digest) ||
        !nonempty(event.source_ref) || !nonempty(event.created_at) ||
        !/(Z|[+-]\d{2}:\d{2})$/.test(event.created_at) || !Number.isFinite(Date.parse(event.created_at)) ||
        event.simulated !== (report.mode === 'simulation')) invalid();
    const prospect = prospects.get(event.prospect_id);
    if (!prospect) invalid();
    if (!isUuid(prospect.contact_id) || !owned.has(prospect.contact_id)) continue;
    const bookingVerified = report.timeline.some((receipt) => object(receipt) && object(receipt.data) &&
      receipt.pursuit_id === event.prospect_id && typeof receipt.data.request_sha === 'string' &&
      /^[a-f0-9]{64}$/.test(receipt.data.request_sha) &&
      ((receipt.kind === 'dispatch_verified' && receipt.data.purpose === 'booking' && receipt.data.provider_id === event.booking_id) ||
       (receipt.kind === 'booking_verified' && receipt.data.event_id === event.booking_id)));
    if (!bookingVerified) invalid();
    const hash = createHash('sha256').update(JSON.stringify(['dogfood-amendment-v1', ctx.accountId, event.id])).digest();
    hash[6] = (hash[6] & 15) | 128;
    hash[8] = (hash[8] & 63) | 128;
    const hex = hash.subarray(0, 16).toString('hex');
    const id = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    const note = { id, account_id: ctx.accountId, contact_id: prospect.contact_id, user_id: ctx.userId,
      created_at: new Date(event.created_at).toISOString(),
      note_text: `${report.mode === 'simulation' ? '[Simulation] ' : ''}Calendar ${event.operation === 'cancel' ? 'cancellation' : 'reschedule'} verified.\nBooking reference: ${event.booking_id}\nApproved change digest: ${event.digest}\nEvidence: ${event.source_ref}\nConcierge event: ${event.id}` };
    if (amendmentNotes.has(id) && JSON.stringify(amendmentNotes.get(id)) !== JSON.stringify(note)) invalid();
    amendmentNotes.set(id, note);
  }
  const result = await reconcileConcierge(ctx, {
    workspace: { account_id: ctx.accountId }, mode: report.mode, direct_messages, timeline,
  });
  const amendmentErrors: string[] = [];
  let amendmentNotesCreated = 0;
  let amendmentNotesExisting = 0;
  for (const note of amendmentNotes.values()) {
    try {
      const inserted = await ctx.supabase.from('contact_notes').upsert(note, { onConflict: 'id', ignoreDuplicates: true }).select('id');
      if (inserted.error) throw new Error('insert');
      const verified = await ctx.supabase.from('contact_notes').select('id,account_id,contact_id,note_text,created_at')
        .eq('id', note.id).eq('account_id', ctx.accountId).maybeSingle();
      if (verified.error || !verified.data || verified.data.account_id !== ctx.accountId ||
          verified.data.contact_id !== note.contact_id || verified.data.note_text !== note.note_text ||
          Date.parse(verified.data.created_at) !== Date.parse(note.created_at)) throw new Error('collision');
      if (inserted.data?.length) amendmentNotesCreated++;
      else amendmentNotesExisting++;
    } catch {
      amendmentErrors.push('Calendar amendment note could not be verified. Existing notes were preserved; retry reconciliation.');
    }
  }
  return { ...result, skipped,
    amendment_notes_created: amendmentNotesCreated, amendment_notes_existing: amendmentNotesExisting,
    amendment_errors: amendmentErrors,
    status: result.status === 'partial' || owned.size !== linked.size || skipped.future_simulation_messages || amendmentErrors.length
      ? 'partial' : result.status,
    unverified_contact_links: linked.size - owned.size };
}
