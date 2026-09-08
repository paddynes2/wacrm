import { describe, expect, it } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import { mirrorDirectMessages, type DirectMessage } from './inbox';

function database(responses: Array<{ data?: unknown; error?: unknown }>) {
  const calls: Array<{ table: string; ops: Array<[string, ...unknown[]]> }> = [];
  const db = { from(table: string) {
    const call = { table, ops: [] as Array<[string, ...unknown[]]> }; calls.push(call);
    const chain: Record<string, unknown> = {};
    for (const method of ['select', 'eq', 'maybeSingle', 'single', 'insert', 'update', 'or']) {
      chain[method] = (...args: unknown[]) => { call.ops.push([method, ...args]); return chain; };
    }
    chain.then = (resolve: (v: unknown) => unknown) => {
      if (!responses.length) throw new Error('Unexpected database call');
      return Promise.resolve(resolve(responses.shift()));
    };
    return chain;
  } } as unknown as SupabaseClient;
  return { db, calls };
}
const message: DirectMessage = { id: 'm1', text: 'Hello', direction: 'inbound', occurred_at: '2026-01-01T10:00:00Z' };
const input = (messages = [message]) => ({ accountId: 'a', userId: 'u', contactId: 'c', messages });
const contact = { data: { id: 'c', account_id: 'a' } };
const conv = { data: { id: 'v' } };

describe('native inbox bridge', () => {
  it('checks account and labels simulated history distinctly', async () => {
    const { db, calls } = database([contact, conv, {}, {}]);
    expect(await mirrorDirectMessages(db, input([{ ...message, simulated: true }]))).toEqual({ conversationId: 'v', count: 1 });
    expect(calls[0].ops).toContainEqual(['eq', 'account_id', 'a']);
    expect(calls[2].ops[0]).toEqual(['insert', expect.objectContaining({ message_id: 'simulation:direct:m1', content_text: '[Simulation] Hello', sender_type: 'customer' })]);
  });
  it('rejects cross-account contact before writes', async () => {
    const { db, calls } = database([{ data: { id: 'c', account_id: 'other' } }]);
    await expect(mirrorDirectMessages(db, input())).rejects.toThrow('account');
    expect(calls).toHaveLength(1);
  });
  it.each([{ direction: 'draft' }, { occurred_at: '2026-01-01' }, { occurred_at: '2026-02-30T10:00:00Z' }, { id: '' }, { manual: true }, { simulated: 'false' }])('validates entire batch before writes: %j', async change => {
    const { db, calls } = database([]);
    await expect(mirrorDirectMessages(db, input([{ ...message, ...change } as DirectMessage]))).rejects.toThrow();
    expect(calls).toHaveLength(0);
  });
  it('skips group transcripts', async () => {
    const { db, calls } = database([contact, conv]);
    expect((await mirrorDirectMessages(db, input([{ ...message, group: true }]))).count).toBe(0);
    expect(calls.map(x => x.table)).toEqual(['contacts', 'conversations']);
  });
  it('does not attribute historical manual sends to the importing operator', async () => {
    const { db, calls } = database([contact, conv, {}, {}]);
    await mirrorDirectMessages(db, input([{ ...message, direction: 'outbound', manual: true }]));
    expect(calls[2].ops[0]).toEqual(['insert', expect.objectContaining({ sender_type: 'agent', sender_id: null })]);
  });
  it('deduplicates known provider messages without overwriting', async () => {
    const { db, calls } = database([contact, conv, { error: { code: '23505' } },
      { data: { message_id: 'unipile:direct:m1', content_text: 'Hello', sender_type: 'customer', created_at: message.occurred_at } }, {}]);
    expect((await mirrorDirectMessages(db, input())).count).toBe(0);
    expect(calls[3].ops).toContainEqual(['eq', 'conversation_id', 'v']);
  });
  it('surfaces changed payload collision and database failures', async () => {
    const a = database([contact, conv, { error: { code: '23505' } }, { data: { content_text: 'other' } }]);
    await expect(mirrorDirectMessages(a.db, input())).rejects.toThrow('collision');
    const b = database([contact, conv, { error: { code: 'XX000' } }]);
    await expect(mirrorDirectMessages(b.db, input())).rejects.toThrow('mirror failed');
  });
  it('recovers only unique conversation race and preserves account scope', async () => {
    const { db, calls } = database([contact, { data: null }, { error: { code: '23505' } }, conv, {}, {}]);
    expect((await mirrorDirectMessages(db, input())).conversationId).toBe('v');
    expect(calls[3].ops).toContainEqual(['eq', 'account_id', 'a']);
  });
});
