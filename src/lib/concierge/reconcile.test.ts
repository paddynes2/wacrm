import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import { reconcileConcierge } from './reconcile';
import { mirrorDirectMessages } from './inbox';
vi.mock('./inbox', () => ({ mirrorDirectMessages: vi.fn() }));
const account = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const contact = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
const other = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
function database(owned = [contact]) {
  const notes = new Map<string, Record<string, unknown>>();
  const calls: { table: string; filters: unknown[][] }[] = [];
  const db = {
    from(table: string) {
      const call = { table, filters: [] as unknown[][] };
      calls.push(call);
      let candidate: Record<string, unknown> | undefined;
      const chain: Record<string, unknown> = {};
      for (const op of ['select', 'eq', 'in', 'maybeSingle', 'upsert'])
        chain[op] = (...args: unknown[]) => {
          call.filters.push([op, ...args]);
          if (op === 'upsert') candidate = args[0] as Record<string, unknown>;
          return chain;
        };
      chain.then = (resolve: (value: unknown) => unknown) => {
        if (table === 'contacts')
          return Promise.resolve(
            resolve({
              data: owned.map((id) => ({ id, account_id: account })),
              error: null,
            })
          );
        if (candidate) {
          const id = String(candidate.id);
          const exists = notes.has(id);
          if (!exists) notes.set(id, candidate);
          return Promise.resolve(
            resolve({ data: exists ? [] : [{ id }], error: null })
          );
        }
        const id = String(
          call.filters.find((f) => f[0] === 'eq' && f[1] === 'id')?.[2]
        );
        return Promise.resolve(resolve({ data: notes.get(id), error: null }));
      };
      return chain;
    },
  };
  return {
    ctx: {
      supabase: db as unknown as SupabaseClient,
      accountId: account,
      userId: other,
    },
    notes,
    calls,
  };
}
const report = (timeline: unknown[] = [], direct_messages: unknown[] = []) => ({
  workspace: { account_id: account },
  mode: 'simulation',
  timeline,
  direct_messages,
});
const event = (
  kind = 'dispatch_verified',
  data: Record<string, unknown> = {
    action_id: 'action',
    purpose: 'introduction',
    provider_id: 'group',
  }
) => ({
  event_id: 'event-1',
  pursuit_id: `wacrm:${contact}`,
  kind,
  data,
  occurred_at: '2026-09-01T10:00:00Z',
  source_ref: 'provider receipt',
});
beforeEach(() => {
  vi.mocked(mirrorDirectMessages)
    .mockReset()
    .mockImplementation(async (_db, input) => ({
      conversationId: 'conversation',
      count: input.messages.length,
    }));
});
describe('reconcileConcierge', () => {
  it('rejects foreign workspaces and malformed histories before writes', async () => {
    const db = database();
    await expect(
      reconcileConcierge(db.ctx, {
        ...report(),
        workspace: { account_id: other },
      })
    ).rejects.toThrow();
    await expect(
      reconcileConcierge(db.ctx, report([], [{ contact_id: 'invalid' }]))
    ).rejects.toThrow();
    expect(db.calls).toHaveLength(0);
  });
  it('chunks long histories and strips contact routing from message payloads', async () => {
    const db = database();
    const messages = Array.from({ length: 2001 }, (_, i) => ({
      contact_id: contact,
      id: String(i),
      simulated: true,
    }));
    const result = await reconcileConcierge(db.ctx, report([], messages));
    expect(result.totals.message_inserts_confirmed).toBe(2001);
    expect(
      vi
        .mocked(mirrorDirectMessages)
        .mock.calls.map((c) => c[1].messages.length)
    ).toEqual([1000, 1000, 1]);
    expect(
      vi.mocked(mirrorDirectMessages).mock.calls[0][1].messages[0]
    ).not.toHaveProperty('contact_id');
    expect(db.calls[0].filters).toContainEqual(['eq', 'account_id', account]);
  });
  it('skips unowned contacts without copying messages', async () => {
    const result = await reconcileConcierge(
      database([]).ctx,
      report([], [{ contact_id: other, id: 'one', simulated: true }])
    );
    expect(result.skipped_contacts).toBe(1);
    expect(result.status).toBe('partial');
    expect(mirrorDirectMessages).not.toHaveBeenCalled();
  });
  it('creates stable readable outcome notes once and never notes drafts', async () => {
    const db = database();
    const history = report([
      event(),
      { ...event('dispatch_started', {}), event_id: 'draft' },
    ]);
    expect(
      (await reconcileConcierge(db.ctx, history)).totals.notes_created
    ).toBe(1);
    expect(
      (await reconcileConcierge(db.ctx, history)).totals.notes_existing
    ).toBe(1);
    expect(db.notes.size).toBe(1);
    expect([...db.notes.values()][0].note_text).toContain(
      '[Simulation] WhatsApp introduction verified'
    );
  });
  it('preserves colliding existing notes and reports partial failure', async () => {
    const db = database();
    await reconcileConcierge(db.ctx, report([event()]));
    const note = [...db.notes.values()][0];
    note.note_text = 'Human edited note';
    const result = await reconcileConcierge(db.ctx, report([event()]));
    expect(result.status).toBe('partial');
    expect(note.note_text).toBe('Human edited note');
  });
  it('fails closed on contradictory event IDs and unsupported attendance', async () => {
    const db = database();
    await expect(
      reconcileConcierge(
        db.ctx,
        report([event(), { ...event(), source_ref: 'different' }])
      )
    ).rejects.toThrow();
    await expect(
      reconcileConcierge(
        db.ctx,
        report([event('meeting_attended', { event_id: 'missing' })])
      )
    ).rejects.toThrow();
    expect(db.calls).toHaveLength(0);
  });
  it('copies receipt-backed booking and attendance, independent of history order', async () => {
    const db = database();
    const booking = event('booking_verified', {
      event_id: 'meeting',
      request_sha: 'a'.repeat(64),
    });
    const attendance = {
      ...event('meeting_attended', { event_id: 'meeting' }),
      event_id: 'attended',
    };
    expect(
      (await reconcileConcierge(db.ctx, report([attendance, booking]))).totals
        .notes_created
    ).toBe(2);
  });
  it('continues notes after a partially successful message batch without claiming all inserts', async () => {
    vi.mocked(mirrorDirectMessages).mockRejectedValueOnce(
      new Error('secret provider error')
    );
    const db = database();
    const result = await reconcileConcierge(
      db.ctx,
      report([event()], [{ contact_id: contact, id: 'one', simulated: true }])
    );
    expect(result.status).toBe('partial');
    expect(result.totals.notes_created).toBe(1);
    expect(result.totals.message_inserts_confirmed).toBe(0);
    expect(JSON.stringify(result)).not.toContain('secret');
  });
});
