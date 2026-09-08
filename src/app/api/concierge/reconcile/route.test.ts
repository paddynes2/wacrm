import { describe, it, expect, vi, beforeEach } from 'vitest';
const mocks = vi.hoisted(() => ({
  role: vi.fn(),
  status: vi.fn(),
  reconcile: vi.fn(),
  limit: vi.fn(),
}));
vi.mock('@/lib/auth/account', () => ({
  requireRole: mocks.role,
  toErrorResponse: () =>
    Response.json({ error: 'Unauthorized' }, { status: 401 }),
}));
vi.mock('@/lib/concierge/bridge', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  bridgeStatus: mocks.status,
}));
vi.mock('@/lib/concierge/reconcile', () => ({
  reconcileConcierge: mocks.reconcile,
}));
vi.mock('@/lib/rate-limit', () => ({
  checkRateLimit: mocks.limit,
  rateLimitResponse: () =>
    Response.json({ error: 'Rate limited' }, { status: 429 }),
}));
import { POST } from './route';
import { BridgeError } from '@/lib/concierge/bridge';
const request = (body = '{}', origin = 'http://localhost') =>
  new Request('http://localhost/api/concierge/reconcile', {
    method: 'POST',
    headers: { origin, 'content-type': 'application/json' },
    body,
  });
beforeEach(() => {
  vi.clearAllMocks();
  mocks.role.mockResolvedValue({
    accountId: 'account',
    userId: 'user',
    supabase: {},
  });
  mocks.status.mockResolvedValue({ workspace: { account_id: 'account' } });
  mocks.limit.mockReturnValue({ success: true });
  mocks.reconcile.mockResolvedValue({
    status: 'reconciled',
    contacts: [],
    totals: { contacts: 0 },
    skipped_contacts: 0,
  });
});
describe('reconciliation route', () => {
  it('uses server-owned account and history', async () => {
    expect((await POST(request())).status).toBe(200);
    expect(mocks.role).toHaveBeenCalledWith('agent');
    expect(mocks.status).toHaveBeenCalledWith('account');
    expect(mocks.reconcile).toHaveBeenCalledWith(
      expect.objectContaining({ accountId: 'account' }),
      { workspace: { account_id: 'account' } }
    );
  });
  it.each([
    'null',
    '[]',
    '{"report":{}}',
    '{"account_id":"foreign"}',
    'broken',
  ])('rejects caller data %s', async (body) => {
    expect((await POST(request(body))).status).toBe(400);
    expect(mocks.status).not.toHaveBeenCalled();
  });
  it('rejects oversized input', async () => {
    expect((await POST(request(' '.repeat(1025)))).status).toBe(413);
  });
  it('rejects cross origin and rate limits', async () => {
    expect((await POST(request('{}', 'https://evil.test'))).status).toBe(403);
    mocks.limit.mockReturnValue({ success: false });
    expect((await POST(request())).status).toBe(429);
    expect(mocks.status).not.toHaveBeenCalled();
  });
  it('redacts bridge failures and preserves useful service status', async () => {
    mocks.status.mockRejectedValue(new BridgeError('secret token', 503));
    const response = await POST(request());
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain('secret');
  });
  it('does not access bridge without authentication', async () => {
    mocks.role.mockRejectedValue(new Error('unauthorized'));
    expect((await POST(request())).status).toBe(401);
    expect(mocks.status).not.toHaveBeenCalled();
  });
  it('preserves partial outcomes for safe retries', async () => {
    mocks.reconcile.mockResolvedValue({
      status: 'partial',
      skipped_contacts: 1,
    });
    expect(await (await POST(request())).json()).toEqual({
      status: 'partial',
      skipped_contacts: 1,
    });
  });
});
