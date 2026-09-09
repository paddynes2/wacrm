import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
const bridge = vi.hoisted(() => vi.fn());
vi.mock('@/lib/concierge/bridge', () => ({ bridgeRequest: bridge }));
import { sendMessageToConversation } from '@/lib/whatsapp/send-message';

beforeEach(() => { vi.stubEnv('WACRM_BRIDGE_URL', 'http://127.0.0.1:1'); bridge.mockReset(); bridge.mockResolvedValue({ result: { status: 'needs_approval', decision: { id: 'decision1' } } }); });
afterEach(() => vi.unstubAllEnvs());
it('standalone inbox directs human replies to Chris without calling the legacy bridge or Meta', async () => {
  vi.stubEnv('WACRM_STANDALONE', '1');
  vi.stubEnv('WACRM_BRIDGE_URL', '');
  await expect(sendMessageToConversation(database().db, 'a', { conversationId: 'v', messageType: 'text', contentText: 'Hello' })).rejects.toMatchObject({ status: 409, message: 'Open Chris dogfood to take over this conversation and prepare a reply.' });
  expect(bridge).not.toHaveBeenCalled();
});
function database(account = 'a', missing = false) {
  const filters: unknown[] = [];
  return { filters, db: { from(table: string) {
    if (table !== 'conversations') throw new Error('Must never query Meta config or insert sent row');
    const chain = { select: () => chain, eq: (...args: unknown[]) => { filters.push(args); return chain; },
      single: async () => ({ data: missing ? null : { contact: { id: 'c', account_id: account, phone: '+27820000001', name: 'Sam' } }, error: null }) };
    return chain;
  } } as unknown as SupabaseClient };
}
it('native send becomes an account-scoped draft, never a sent message', async () => {
  const { db, filters } = database();
  await expect(sendMessageToConversation(db, 'a', { conversationId: 'v', messageType: 'text', contentText: 'Hello' })).rejects.toMatchObject({ code: 'draft_staged', message: 'Draft staged in Concierge for approval' });
  expect(filters).toContainEqual(['account_id', 'a']);
  expect(bridge).toHaveBeenCalledWith('a', 'manual_draft', expect.objectContaining({ text: 'Hello', conversation_id: 'v', contact: expect.objectContaining({ id: 'c' }) }));
  expect(bridge.mock.calls[0][2].contact).not.toHaveProperty('account_id');
});
it('cross-account and unavailable contacts cannot reach bridge', async () => {
  for (const db of [database('other').db, database('a', true).db]) {
    await expect(sendMessageToConversation(db, 'a', { conversationId: 'v', messageType: 'text', contentText: 'Hi' })).rejects.toMatchObject({ code: 'not_found' });
  }
  expect(bridge).not.toHaveBeenCalled();
});
it('media and quoted replies fail explicitly without Meta fallback', async () => {
  await expect(sendMessageToConversation(database().db, 'a', { conversationId: 'v', messageType: 'audio', mediaUrl: 'https://example.com/a.ogg' })).rejects.toMatchObject({ code: 'bad_request' });
  await expect(sendMessageToConversation(database().db, 'a', { conversationId: 'v', messageType: 'text', contentText: 'Hi', replyToMessageId: 'm1' })).rejects.toMatchObject({ code: 'bad_request' });
  expect(bridge).not.toHaveBeenCalled();
});
it('bridge failure is not success and never falls back', async () => {
  bridge.mockRejectedValue(new Error('offline'));
  await expect(sendMessageToConversation(database().db, 'a', { conversationId: 'v', messageType: 'text', contentText: 'Hi' })).rejects.toMatchObject({ code: 'bridge_error', status: 502 });
});
it('HTTP success without a staged outcome never claims a draft exists', async () => {
  bridge.mockResolvedValue({ status: 'blocked' });
  await expect(sendMessageToConversation(database().db, 'a', { conversationId: 'v', messageType: 'text', contentText: 'Hi' })).rejects.toMatchObject({ code: 'bridge_error' });
});
