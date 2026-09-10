import { beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ role: vi.fn(), bridge: vi.fn() }));
vi.mock('@/lib/auth/account', () => ({ requireRole: mocks.role, toErrorResponse: () => Response.json({}, { status: 401 }) }));
vi.mock('./bridge', () => ({ chrisRequest: mocks.bridge }));
vi.mock('@/lib/rate-limit', () => ({ checkRateLimit: () => ({ success: true }), rateLimitResponse: vi.fn(), RATE_LIMITS: { send: {} } }));
import { get, post, detail } from './routes';
const account = '11111111-1111-4111-8111-111111111111';
const user = '22222222-2222-4222-8222-222222222222';
const envelope = { schema_version: 1, command_id: '33333333-3333-4333-8333-333333333333', expected_revision: 0, command: 'autonomy.set', payload: { enabled: true, scope_kinds: ['invite'], displayed_authority_revision: 0 } };
const request = (body: unknown, origin = 'http://localhost:18762') => new Request('http://localhost:18762/api/chris/commands', { method: 'POST', headers: { origin }, body: JSON.stringify(body) });
beforeEach(() => { vi.clearAllMocks(); mocks.role.mockResolvedValue({ accountId: account, userId: user, role: 'owner' }); mocks.bridge.mockResolvedValue({ status: 'accepted' }); });
describe('Chris public account boundary', () => {
  it.each(['viewer', 'admin', 'agent'])('only owner can expand authority: %s', async role => {
    mocks.role.mockResolvedValue({ accountId: account, userId: user, role });
    expect((await post(request(envelope))).status).toBe(403); expect(mocks.bridge).not.toHaveBeenCalled();
  });
  it('derives the account and actor instead of trusting payload fields', async () => {
    expect((await post(request(envelope))).status).toBe(202);
    expect(mocks.bridge).toHaveBeenCalledWith(account, '/commands', { envelope, actor: { user_id: user, role: 'owner', request_id: expect.any(String) } });
    expect((await post(request({ ...envelope, account_id: account }))).status).toBe(400);
  });
  it('rejects origin, unknown effects, malformed JSON and byte overflow', async () => {
    expect((await post(request(envelope, 'https://foreign.example'))).status).toBe(403);
    expect((await post(request({ ...envelope, command: 'send' }))).status).toBe(400);
    expect((await post(request({ ...envelope, command: 'brief.propose', payload: { text: '😀'.repeat(9000) } }))).status).toBe(413);
  });
  it('requires owner for export and returns no-store data', async () => {
    const response = await get(undefined, '/export'); expect(response.status).toBe(200);
    expect(mocks.role).toHaveBeenCalledWith('owner'); expect(response.headers.get('cache-control')).toBe('private, no-store');
  });
  it('refuses malformed entity IDs and cursors before forwarding', async () => {
    expect((await detail('people', 'foreign/path')).status).toBe(404);
    expect((await get(new Request('http://localhost/api/chris/people?limit=101'), '/people')).status).toBe(400);
    expect(mocks.bridge).not.toHaveBeenCalled();
  });
});
