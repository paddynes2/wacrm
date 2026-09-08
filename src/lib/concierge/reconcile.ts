import { createHash } from 'node:crypto';
import type { SupabaseClient } from '@supabase/supabase-js';
import { BridgeError, isUuid } from './bridge';
import { mirrorDirectMessages, type DirectMessage } from './inbox';

type Row = Record<string, unknown>;
const object = (v: unknown): v is Row =>
  !!v && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string =>
  typeof v === 'string' && !!v.trim() && v.length <= 2000;
function invalid(): never {
  throw new BridgeError(
    'The concierge returned an invalid reconciliation report.',
    502
  );
}
function noteId(account: string, event: string) {
  const bytes = createHash('sha256')
    .update(JSON.stringify(['concierge-outcome-v1', account, event]))
    .digest();
  bytes[6] = (bytes[6] & 15) | 128;
  bytes[8] = (bytes[8] & 63) | 128;
  const h = bytes.subarray(0, 16).toString('hex');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
type Note = {
  id: string;
  contact_id: string;
  account_id: string;
  user_id: string;
  note_text: string;
  created_at: string;
};

/** Replay the canonical history into existing CRM records. No provider actions occur here. */
export async function reconcileConcierge(
  ctx: { supabase: SupabaseClient; accountId: string; userId: string },
  report: unknown
) {
  if (
    !object(report) ||
    !object(report.workspace) ||
    report.workspace.account_id !== ctx.accountId ||
    !['simulation', 'live'].includes(String(report.mode)) ||
    !Array.isArray(report.direct_messages) ||
    !Array.isArray(report.timeline)
  )
    invalid();
  const messages = new Map<string, DirectMessage[]>();
  const notes = new Map<string, Note[]>();
  const ids = new Set<string>();
  for (const entry of report.direct_messages) {
    if (!object(entry) || !isUuid(entry.contact_id)) invalid();
    const { contact_id, ...message } = entry;
    if (message.simulated !== (report.mode === 'simulation')) invalid();
    ids.add(contact_id);
    const history = messages.get(contact_id) ?? [];
    history.push(message as unknown as DirectMessage);
    messages.set(contact_id, history);
  }
  const seen = new Map<string, string>();
  const bookings = new Set<string>();
  // Booking receipts are looked up independently of report ordering.
  for (const event of report.timeline) {
    if (!object(event) || !object(event.data)) invalid();
    if (
      event.kind === 'booking_verified' &&
      text(event.data.event_id) &&
      typeof event.data.request_sha === 'string' &&
      /^[a-f0-9]{64}$/i.test(event.data.request_sha)
    )
      bookings.add(`${event.pursuit_id}:${event.data.event_id}`);
    if (
      event.kind === 'dispatch_verified' &&
      event.data.purpose === 'booking' &&
      text(event.data.provider_id) &&
      typeof event.data.request_sha === 'string' &&
      /^[a-f0-9]{64}$/i.test(event.data.request_sha)
    )
      bookings.add(`${event.pursuit_id}:${event.data.provider_id}`);
  }
  for (const event of report.timeline) {
    if (!object(event) || !object(event.data)) invalid();
    const d = event.data;
    let label: string;
    let receipt: unknown;
    if (event.kind === 'dispatch_verified' && d.purpose === 'introduction') {
      label = 'WhatsApp introduction verified';
      receipt = d.provider_id;
      if (!text(d.action_id)) invalid();
    } else if (
      event.kind === 'booking_verified' ||
      (event.kind === 'dispatch_verified' && d.purpose === 'booking')
    ) {
      label = 'Calendar booking verified';
      receipt = event.kind === 'booking_verified' ? d.event_id : d.provider_id;
      if (
        typeof d.request_sha !== 'string' ||
        !/^[a-f0-9]{64}$/i.test(d.request_sha)
      )
        invalid();
    } else if (event.kind === 'meeting_attended') {
      label = 'Meeting attendance recorded';
      receipt = d.event_id;
      if (!bookings.has(`${event.pursuit_id}:${receipt}`)) invalid();
    } else continue;
    const contact =
      typeof event.pursuit_id === 'string'
        ? event.pursuit_id.replace(/^wacrm:/, '')
        : '';
    if (
      !String(event.pursuit_id).startsWith('wacrm:') ||
      !isUuid(contact) ||
      !text(event.event_id) ||
      !text(event.source_ref) ||
      !text(receipt) ||
      typeof event.occurred_at !== 'string' ||
      !/(Z|[+-]\d{2}:\d{2})$/.test(event.occurred_at) ||
      !Number.isFinite(Date.parse(event.occurred_at))
    )
      invalid();
    const note: Note = {
      id: noteId(ctx.accountId, event.event_id),
      account_id: ctx.accountId,
      contact_id: contact,
      user_id: ctx.userId,
      created_at: new Date(event.occurred_at).toISOString(),
      note_text: `${report.mode === 'simulation' ? '[Simulation] ' : ''}${label}.\nProvider reference: ${receipt}\nEvidence: ${event.source_ref}\nConcierge event: ${event.event_id}`,
    };
    const signature = JSON.stringify(note);
    if (seen.has(note.id)) {
      if (seen.get(note.id) !== signature) invalid();
      continue;
    }
    seen.set(note.id, signature);
    ids.add(contact);
    notes.set(contact, [...(notes.get(contact) ?? []), note]);
  }
  const owned = new Set<string>();
  const requested = [...ids];
  for (let i = 0; i < requested.length; i += 200) {
    const batch = requested.slice(i, i + 200);
    const response = await ctx.supabase
      .from('contacts')
      .select('id, account_id')
      .eq('account_id', ctx.accountId)
      .in('id', batch);
    if (response.error || !Array.isArray(response.data))
      throw new BridgeError(
        'CRM contacts could not be checked. Retry reconciliation.',
        503
      );
    for (const contact of response.data) {
      if (contact.account_id !== ctx.accountId || !batch.includes(contact.id))
        invalid();
      owned.add(contact.id);
    }
  }
  const contacts = [];
  for (const contactId of owned) {
    const result = {
      contact_id: contactId,
      status: 'reconciled' as 'reconciled' | 'partial',
      message_inserts_confirmed: 0,
      notes_created: 0,
      notes_existing: 0,
      errors: [] as string[],
    };
    const history = messages.get(contactId) ?? [];
    for (let i = 0; i < history.length; i += 1000) {
      try {
        result.message_inserts_confirmed += (
          await mirrorDirectMessages(ctx.supabase, {
            ...ctx,
            contactId,
            messages: history.slice(i, i + 1000),
          })
        ).count;
      } catch {
        result.errors.push(
          'Conversation history was only partially copied. Retrying is safe and will not resend messages.'
        );
        break;
      }
    }
    for (const note of notes.get(contactId) ?? []) {
      try {
        const inserted = await ctx.supabase
          .from('contact_notes')
          .upsert(note, { onConflict: 'id', ignoreDuplicates: true })
          .select('id');
        if (inserted.error) throw new Error('insert');
        const existing = await ctx.supabase
          .from('contact_notes')
          .select('id, account_id, contact_id, note_text, created_at')
          .eq('id', note.id)
          .eq('account_id', ctx.accountId)
          .maybeSingle();
        if (
          existing.error ||
          !existing.data ||
          existing.data.account_id !== ctx.accountId ||
          existing.data.contact_id !== contactId ||
          existing.data.note_text !== note.note_text ||
          Date.parse(existing.data.created_at) !== Date.parse(note.created_at)
        )
          throw new Error('collision');
        if (inserted.data?.length) result.notes_created++;
        else result.notes_existing++;
      } catch {
        result.errors.push(
          'An outcome note could not be verified. Existing notes were preserved; retry reconciliation.'
        );
      }
    }
    if (result.errors.length) result.status = 'partial';
    contacts.push(result);
  }
  const skipped_contacts = ids.size - owned.size;
  return {
    status:
      skipped_contacts || contacts.some((c) => c.status === 'partial')
        ? 'partial'
        : 'reconciled',
    contacts,
    skipped_contacts,
    totals: {
      contacts: contacts.length,
      message_inserts_confirmed: contacts.reduce(
        (n, c) => n + c.message_inserts_confirmed,
        0
      ),
      notes_created: contacts.reduce((n, c) => n + c.notes_created, 0),
      notes_existing: contacts.reduce((n, c) => n + c.notes_existing, 0),
    },
  };
}
