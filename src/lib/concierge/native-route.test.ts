import { afterEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ send: vi.fn() }));
vi.mock('@/lib/auth/account', () => ({ requireRole: vi.fn(async () => {
  const chain = { select: () => chain, eq: () => chain, single: async () => ({ data: { id: 'v' } }) };
  return { supabase: { from: () => chain }, accountId: 'a', userId: 'u' };
}), toErrorResponse: vi.fn() }));
vi.mock('@/lib/rate-limit', () => ({ checkRateLimit: () => ({ success: true }), RATE_LIMITS: { send: {} }, rateLimitResponse: vi.fn() }));
vi.mock('@/lib/whatsapp/send-message', async original => ({ ...await original<typeof import('@/lib/whatsapp/send-message')>(), sendMessageToConversation: mocks.send }));
import { SendMessageError } from '@/lib/whatsapp/send-message';
import { GET, POST } from '@/app/api/whatsapp/send/route';

afterEach(() => vi.unstubAllEnvs());
it('202 draft receipt has no fake message id or sent success flag', async () => {
  mocks.send.mockRejectedValue(new SendMessageError('draft_staged', 'Draft staged in Concierge for approval', 409));
  const response = await POST(new Request('http://localhost/api/whatsapp/send', { method: 'POST', body: JSON.stringify({ conversation_id: 'v', message_type: 'text', content_text: 'Hello' }) }));
  expect(response.status).toBe(202);
  expect(await response.json()).toEqual({ draft_staged: true, message: 'Draft ready in Concierge', concierge_url: '/concierge' });
});
it('composer mode reveals only the staging mode', async () => {
  vi.stubEnv('WACRM_BRIDGE_URL', 'http://localhost:1');
  expect(await (await GET()).json()).toEqual({ draft_only: true });
});
