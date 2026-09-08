import { beforeEach, describe, expect, it, vi } from 'vitest';
const f = vi.hoisted(() => ({
  role: vi.fn(),
  bridge: vi.fn(),
  status: vi.fn(),
  from: vi.fn(),
  query: {} as Record<string, ReturnType<typeof vi.fn>>,
}));
vi.mock('@/lib/auth/account', () => ({
  requireRole: f.role,
  toErrorResponse: () =>
    Response.json({ error: 'Unauthorized' }, { status: 401 }),
}));
vi.mock('@/lib/rate-limit', () => ({
  checkRateLimit: () => ({ success: true }),
  rateLimitResponse: vi.fn(),
  RATE_LIMITS: { send: {} },
}));
vi.mock('@/lib/concierge/bridge', async (original) => ({
  ...(await original<typeof import('@/lib/concierge/bridge')>()),
  bridgeRequest: f.bridge,
  bridgeStatus: f.status,
}));
import { POST } from './route';
const account = '11111111-1111-4111-8111-111111111111';
const contactId = '22222222-2222-4222-8222-222222222222';
beforeEach(() => {
  vi.clearAllMocks();
  f.query = Object.fromEntries(
    ['select', 'eq'].map((k) => [k, vi.fn(() => f.query)])
  );
  f.query.maybeSingle = vi
    .fn()
    .mockResolvedValue({
      data: { id: contactId, name: 'Bond', phone: '+27820000002' },
      error: null,
    });
  f.from.mockReturnValue(f.query);
  f.role.mockResolvedValue({
    accountId: account,
    userId: account,
    supabase: { from: f.from },
  });
  f.bridge.mockResolvedValue({ status: 'staged' });
});
function request(body: unknown, origin = 'http://localhost:8316') {
  return new Request('http://localhost:8316/api/concierge', {
    method: 'POST',
    headers: { origin },
    body: JSON.stringify(body),
  });
}
describe('CRM account to concierge boundary', () => {
  it('binds live attestation to authenticated user and canonical contact', async () => {
    const result = await POST(request({action:'execute_approved',contact_id:contactId,decision_id:'d1',digest:'digest',attested_by:'spoof'}));
    expect(result.status).toBe(200);
    expect(f.bridge).toHaveBeenCalledWith(account,'execute_approved',{decision_id:'d1',digest:'digest',attested_by:account,contact:{id:contactId,name:'Bond',phone:'+27820000002'}});
  });
  it('accepts formatting on an explicitly international native CRM phone', async () => {
    f.query.maybeSingle.mockResolvedValue({data:{id:contactId,name:'Bond',phone:'+27 (82) 000-0002'}});
    expect((await POST(request({action:'draft',contact_id:contactId,text:'Hello'}))).status).toBe(200);
    expect(f.bridge).toHaveBeenCalledWith(account,'draft',{text:'Hello',contact:{id:contactId,name:'Bond',phone:'+27820000002'}});
  });
  it('refuses cross-origin mutation before session or network work', async () => {
    expect(
      (await POST(request({ action: 'draft' }, 'https://evil.example'))).status
    ).toBe(403);
    expect(f.bridge).not.toHaveBeenCalled();
  });
  it('refuses unauthenticated callers', async () => {
    f.role.mockRejectedValue(new Error('auth'));
    expect(
      (await POST(request({ action: 'draft', contact_id: contactId }))).status
    ).toBe(401);
    expect(f.bridge).not.toHaveBeenCalled();
  });
  it('checks exact account ownership before dispatching a foreign contact', async () => {
    f.query.maybeSingle.mockResolvedValue({ data: null });
    expect(
      (await POST(request({ action: 'draft', contact_id: contactId }))).status
    ).toBe(404);
    expect(f.query.eq).toHaveBeenCalledWith('account_id', account);
    expect(f.bridge).not.toHaveBeenCalled();
  });
  it('ignores browser transport identity and uses canonical contact', async () => {
    const response = await POST(
      request({
        action: 'draft',
        contact_id: contactId,
        account_id: 'wrong',
        bot_id: 'wrong',
        contact: { phone: 'wrong' },
        text: 'Hello',
      })
    );
    expect(response.status).toBe(200);
    expect(f.bridge).toHaveBeenCalledWith(account, 'draft', {
      text: 'Hello',
      contact: { id: contactId, name: 'Bond', phone: '+27820000002' },
    });
  });
  it('requires admin to set up the assistant', async () => {
    f.role.mockImplementation(async (role) => {
      if (role === 'admin') throw new Error('forbidden');
      return { accountId: account, userId: account };
    });
    await POST(request({ action: 'setup', principal_name: 'Patrick' }));
    expect(f.bridge).not.toHaveBeenCalled();
  });
  it('rejects unknown actions and malformed bodies', async () => {
    for (const body of [
      [],
      null,
      { action: 'send_anything' },
      { action: 'draft', contact_id: '../other' },
    ])
      expect((await POST(request(body))).status).toBe(400);
    expect(f.bridge).not.toHaveBeenCalled();
  });
});
