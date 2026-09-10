import { createHash } from 'node:crypto';
import type { SupabaseClient } from '@supabase/supabase-js';
import { chrisRequest } from './bridge';
import { assert, canonical, exact, object, type Row } from './contracts';
import { isUuid } from '@/lib/concierge/bridge';
import { mirrorDirectMessages, type DirectMessage } from '@/lib/concierge/inbox';

export function stableId(value: string) {
  const h = createHash('sha256').update(value).digest('hex');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-5${h.slice(13, 16)}-8${h.slice(17, 20)}-${h.slice(20, 32)}`;
}

/** Called only after private callback authentication, using immutable source facts. */
export async function projectBatch(db: SupabaseClient, account: string, ids: string[], bridge = chrisRequest) {
  assert(isUuid(account) && ids.length <= 50 && ids.every(isUuid));
  const profiles = await db.from('profiles').select('user_id,account_id,account_role').eq('account_id', account).eq('account_role', 'owner');
  assert(!profiles.error && profiles.data?.length === 1 && profiles.data[0].account_id === account, 'principal_mapping_unverified', 503);
  const user = profiles.data[0].user_id;
  const results: Row[] = [];
  for (const id of ids) {
    const response = await bridge(account, '/projections/' + id);
    assert(object(response.item), 'invalid_projection');
    const row = response.item;
    assert(row.account_id === account && row.projection_id === id && object(row.payload), 'foreign_projection', 403);
    const p = row.payload;
    assert(createHash('sha256').update(canonical(p)).digest('hex') === row.payload_digest, 'projection_digest_mismatch', 409);
    assert(['contact', 'dossier_note', 'direct_messages', 'introduction_note', 'tombstone'].includes(String(row.kind)), 'invalid_projection_kind');
    assert(typeof p.phone_e164 === 'string' && /^\+[1-9]\d{7,14}$/.test(p.phone_e164) && isUuid(p.person_id), 'projection_identity_unresolved', 409);
    const phone = p.phone_e164;
    if (p.contact_id !== undefined) assert(isUuid(p.contact_id), 'foreign_contact', 403);
    const lookup = () => db.from('contacts').select('id,account_id,phone,phone_normalized').eq('account_id', account).eq('phone_normalized', phone.slice(1)).maybeSingle();
    let contact = await lookup();
    assert(!contact.error, 'crm_prerequisites_unverified', 503);
    if (row.kind === 'tombstone' || p.tombstone === true) {
      await bridge(account, '/projections/' + id + '/ack', { digest: row.payload_digest, result: 'tombstone' });
      results.push({ id, status: 'tombstone' }); continue;
    }
    if (!contact.data && row.kind === 'contact') {
      exact(p, ['person_id', 'phone_e164', 'display_name', 'company_name', 'identity_status'], ['synthetic']);
      assert(['corroborated', 'operator_attested'].includes(String(p.identity_status)), 'projection_identity_unresolved', 409);
      const prior = await db.from('contacts').select('id,account_id,phone_normalized').eq('id', stableId(`chris-contact:${account}:${p.person_id}`)).maybeSingle();
      assert(!prior.error && !prior.data, 'crm_identity_changed', 409);
      if (row.status === 'acknowledged') {
        await bridge(account, '/projections/' + id + '/ack', { digest: row.payload_digest, result: 'tombstone' });
        results.push({ id, status: 'tombstone' }); continue;
      }
      assert(!row.contact_creation_claimed, 'contact_creation_uncertain', 409);
      // Persist before creation. After a lost response, only read-back is allowed;
      // absence is never proof that a deleted contact should be recreated.
      await bridge(account, '/projections/' + id + '/claim', { digest: row.payload_digest });
      const inserted = await db.from('contacts').insert({ id: stableId(`chris-contact:${account}:${p.person_id}`), account_id: account, user_id: user,
        name: String(p.display_name).slice(0, 200), company: String(p.company_name).slice(0, 200), phone });
      assert(!inserted.error || inserted.error.code === '23505', 'crm_contact_write_failed', 503);
      contact = await lookup();
    }
    assert(!contact.error && contact.data && contact.data.account_id === account && (contact.data.phone_normalized === phone.slice(1) || contact.data.phone === phone), 'crm_identity_changed', 409);
    if (p.contact_id !== undefined) assert(p.contact_id === contact.data.id, 'foreign_contact', 403);
    if (row.kind === 'direct_messages') {
      assert(Array.isArray(p.messages) && p.messages.length <= 100 && p.messages.every(object), 'invalid_messages');
      const messages: DirectMessage[] = p.messages.map(m => {
        assert(object(m) && typeof m.id === 'string' && typeof m.text === 'string' && typeof m.occurred_at === 'string'
          && ['inbound', 'outbound'].includes(String(m.direction)), 'invalid_message');
        return { id: m.id, text: m.text, occurred_at: m.occurred_at, direction: m.direction as 'inbound' | 'outbound',
          chat_id: typeof m.chat_id === 'string' ? m.chat_id : undefined, simulated: p.synthetic === true };
      });
      await mirrorDirectMessages(db, { accountId: account, userId: user, contactId: contact.data.id, messages });
    } else if (['dossier_note', 'introduction_note'].includes(String(row.kind))) {
      const content = row.kind === 'introduction_note'
        ? `WhatsApp introduction observed in the intended group.\nChris: /chris/introductions/${String(p.introduction_id)}\nEvidence event: ${String(row.source_event_id)}`
        : `Chris research: ${String(p.summary).slice(0, 4000)}\nDossier: /chris/people/${String(p.person_id)}\nEvidence event: ${String(row.source_event_id)}`;
      const note = { id, account_id: account, contact_id: contact.data.id, user_id: user, note_text: (p.synthetic ? '[Simulation] ' : '') + content };
      const inserted = await db.from('contact_notes').upsert(note, { onConflict: 'id', ignoreDuplicates: true });
      assert(!inserted.error, 'crm_note_write_failed', 503);
      const observed = await db.from('contact_notes').select('id,account_id,contact_id,note_text').eq('id', id).eq('account_id', account).maybeSingle();
      assert(!observed.error && observed.data?.contact_id === note.contact_id && observed.data?.note_text === note.note_text, 'crm_note_collision', 409);
    }
    await bridge(account, '/projections/' + id + '/ack', { digest: row.payload_digest, result: 'written' });
    results.push({ id, status: 'acknowledged' });
  }
  return { results };
}
