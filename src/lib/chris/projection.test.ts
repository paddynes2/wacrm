import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import { canonical, type Row } from './contracts';
import { projectBatch } from './projection';

const account = '22222222-2222-4222-8222-222222222222';
const person = '33333333-3333-4333-8333-333333333333';
const id = '44444444-4444-4444-8444-444444444444';
function fixture() {
  const rows: Record<string, Row[]> = { profiles: [{ user_id: person, account_id: account, account_role: 'owner' }], contacts: [], contact_notes: [] };
  const writes: Row[] = [];
  const db = { from(table: string) {
    const filters: [string, unknown][] = []; let one = false; let mutation: Row | undefined;
    const q = {
      select() { return q; }, eq(k: string, v: unknown) { filters.push([k,v]); return q; },
      maybeSingle() { one = true; return q; }, insert(row: Row) { mutation = row; return q; },
      upsert(row: Row) { mutation = row; return q; },
      then(resolve: (value: unknown) => unknown) {
        if (mutation && !rows[table].some(r => r.id === mutation?.id)) {
          const value = { ...mutation, ...(table === 'contacts' ? { phone_normalized: String(mutation.phone).slice(1) } : {}) };
          rows[table].push(value); writes.push(value);
        }
        const found = rows[table].filter(r => filters.every(([k,v]) => r[k] === v));
        return Promise.resolve(resolve({ data: one ? found[0] ?? null : found, error: null }));
      }
    }; return q;
  } } as unknown as SupabaseClient;
  const payload = { person_id: person, phone_e164: '+15550001003', display_name: 'Maya', company_name: 'Synthetic Cedar', identity_status: 'operator_attested', synthetic: true };
  const item: Row = { projection_id: id, account_id: account, kind: 'contact', payload, payload_digest: createHash('sha256').update(canonical(payload)).digest('hex'), status: 'pending' };
  const calls: string[] = []; let loseAck = false;
  const bridge = async (_account: string, path = '', body?: Row): Promise<Row> => {
    calls.push(path); expect(_account).toBe(account);
    if (path.endsWith('/claim')) { expect(item.contact_creation_claimed).toBeUndefined(); item.contact_creation_claimed = true; return { claimed: true }; }
    if (path.endsWith('/ack')) { if (loseAck) { loseAck = false; throw new Error('ack lost'); } item.status = 'acknowledged'; item.result = body?.result; return {}; }
    return { item: structuredClone(item) };
  };
  return { db, rows, writes, item, calls, bridge, loseNextAck: () => { loseAck = true; } };
}

describe('real CRM projection adapter with persisted fake tables', () => {
  it('P05 reads back the deterministic contact after CRM commit and lost acknowledgement', async () => {
    const f = fixture(); f.loseNextAck();
    await expect(projectBatch(f.db, account, [id], f.bridge)).rejects.toThrow('ack lost');
    await projectBatch(f.db, account, [id], f.bridge);
    expect(f.rows.contacts).toHaveLength(1); expect(f.writes).toHaveLength(1); expect(f.item.status).toBe('acknowledged');
  });
  it('P08 never recreates a contact deleted after acknowledged creation', async () => {
    const f = fixture(); await projectBatch(f.db, account, [id], f.bridge);
    f.rows.contacts.length = 0;
    await projectBatch(f.db, account, [id], f.bridge);
    expect(f.rows.contacts).toHaveLength(0); expect(f.item.result).toBe('tombstone'); expect(f.writes).toHaveLength(1);
  });
  it('P08 fails closed after creation started but no contact is observable', async () => {
    const f = fixture(); f.item.contact_creation_claimed = true;
    await expect(projectBatch(f.db, account, [id], f.bridge)).rejects.toMatchObject({ code: 'contact_creation_uncertain' }); expect(f.writes).toHaveLength(0);
  });
  it('P04 rejects a foreign immutable callback entity before any CRM write', async () => {
    const f = fixture(); f.item.account_id = person;
    await expect(projectBatch(f.db, account, [id], f.bridge)).rejects.toMatchObject({ code: 'foreign_projection' }); expect(f.writes).toHaveLength(0);
  });
  it('P04 rejects a supplied foreign contact ID before insertion', async () => {
    const f = fixture(); (f.item.payload as Row).contact_id = person;
    f.item.payload_digest = createHash('sha256').update(canonical(f.item.payload)).digest('hex');
    await expect(projectBatch(f.db, account, [id], f.bridge)).rejects.toThrow(); expect(f.writes).toHaveLength(0);
  });
  it('P07 rejects changed phone on an existing deterministic contact', async () => {
    const f = fixture(); await projectBatch(f.db, account, [id], f.bridge);
    f.rows.contacts[0].phone_normalized = '15550009999';
    await expect(projectBatch(f.db, account, [id], f.bridge)).rejects.toMatchObject({ code: 'crm_identity_changed' }); expect(f.writes).toHaveLength(1);
  });
});
