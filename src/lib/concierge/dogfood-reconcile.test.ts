import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import { reconcileDogfood } from './dogfood-reconcile';
import { reconcileConcierge } from './reconcile';

vi.mock('./reconcile', () => ({ reconcileConcierge: vi.fn() }));
const account = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const contact = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
const user = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
function database(changedPhone?: string) {
  const calls: unknown[][] = [];
  const chain = {
    select: (...args: unknown[]) => { calls.push(['select', ...args]); return chain; },
    eq: (...args: unknown[]) => { calls.push(['eq', ...args]); return chain; },
    in: (...args: unknown[]) => { calls.push(['in', ...args]); return Promise.resolve({ error: null,
      data: [{ id: contact, account_id: account, phone: changedPhone ?? '+27820000001' }] }); },
  };
  return { ctx: { supabase: { from: () => chain } as unknown as SupabaseClient, accountId: account, userId: user }, calls };
}
function report() {
  return { account_id: account, mode: 'simulation',
    prospects: [{ id: 'p1', contact_id: contact, phone: '+27820000001' }],
    messages: [{ id: 'm1', prospect_id: 'p1', direction: 'outbound', purpose: 'approach',
      simulated: true, text: 'Hello', created_at: '2020-01-01T00:00:00Z' }],
    timeline: [{ event_id: 'e1', account_id: account, pursuit_id: 'p1', kind: 'dispatch_verified',
      data: { purpose: 'booking', provider_id: 'booking-1', action_id: 'action-1', request_sha: 'a'.repeat(64) },
      occurred_at: '2020-01-01T00:00:00Z', source_ref: 'simulation:verified-local-effect' }],
  };
}
beforeEach(() => {
  vi.mocked(reconcileConcierge).mockReset().mockResolvedValue({ status: 'reconciled', contacts: [], skipped_contacts: 0,
    totals: { contacts: 1, message_inserts_confirmed: 1, notes_created: 1, notes_existing: 0 } });
});
describe('standalone CRM projection', () => {
  it('maps linked prospect messages and verified timeline to existing replay-safe reconciler', async () => {
    const db = database();
    await reconcileDogfood(db.ctx, report());
    const projection = vi.mocked(reconcileConcierge).mock.calls[0][1] as Record<string, unknown[]>;
    expect(projection.direct_messages[0]).toMatchObject({ contact_id: contact, id: 'm1', simulated: true, chat_id: 'dogfood:p1' });
    expect(projection.timeline[0]).toMatchObject({ pursuit_id: `wacrm:${contact}`, event_id: 'e1' });
    expect(db.calls).toContainEqual(['eq', 'account_id', account]);
    expect(db.calls).toContainEqual(['in', 'id', [contact]]);
  });
  it('does not manufacture outcome notes from a state flag', async () => {
    const value = report();
    value.timeline = [];
    await reconcileDogfood(database().ctx, value);
    expect(vi.mocked(reconcileConcierge).mock.calls[0][1]).toHaveProperty('timeline', []);
  });
  it('rejects foreign account, missing timeline and stale phone links before projection writes', async () => {
    await expect(reconcileDogfood(database().ctx, { ...report(), account_id: user })).rejects.toThrow();
    await expect(reconcileDogfood(database().ctx, { ...report(), timeline: undefined })).rejects.toThrow();
    await expect(reconcileDogfood(database('+27820000002').ctx, report())).rejects.toThrow();
    expect(reconcileConcierge).not.toHaveBeenCalled();
  });
  it('excludes group introductions and calendar effects from direct inbox', async () => {
    const value = report();
    value.messages.push({ ...value.messages[0], id: 'group', purpose: 'introduction' },
      { ...value.messages[0], id: 'calendar', purpose: 'booking' });
    const result = await reconcileDogfood(database().ctx, value);
    expect(result.skipped.group_or_nonmessage).toBe(2);
    expect((vi.mocked(reconcileConcierge).mock.calls[0][1] as { direct_messages: unknown[] }).direct_messages).toHaveLength(1);
  });
  it('leaves future simulated transcript evidence unchanged and reports deferred projection', async () => {
    const value = report();
    value.messages[0].created_at = '2999-01-01T00:00:00Z';
    const result = await reconcileDogfood(database().ctx, value);
    expect(result.status).toBe('partial');
    expect(result.skipped.future_simulation_messages).toBe(1);
    expect(value.messages[0].created_at).toBe('2999-01-01T00:00:00Z');
  });
  it('never projects an unlinked prospect or a draft as sent', async () => {
    const value = report();
    value.prospects.push({ id: 'p2', contact_id: '', phone: '+27820000002' });
    value.messages.push({ ...value.messages[0], id: 'other', prospect_id: 'p2' });
    value.messages.push({ ...value.messages[0], id: 'draft', purpose: 'draft' });
    await reconcileDogfood(database().ctx, value);
    expect((vi.mocked(reconcileConcierge).mock.calls[0][1] as { direct_messages: unknown[] }).direct_messages).toHaveLength(1);
  });
  it('requires provider provenance and rejects simulation flags in live histories', async () => {
    const value = report();
    value.mode = 'live';
    await expect(reconcileDogfood(database().ctx, value)).rejects.toThrow();
    expect(reconcileConcierge).not.toHaveBeenCalled();
  });
});
