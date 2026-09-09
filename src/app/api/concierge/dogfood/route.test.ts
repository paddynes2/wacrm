import { beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ role: vi.fn(), bridge: vi.fn() }));
vi.mock('@/lib/auth/account', () => ({
  requireRole: mocks.role,
  toErrorResponse: () =>
    Response.json({ error: 'Unauthorized' }, { status: 401 }),
}));
vi.mock('@/lib/concierge/dogfood', async (original) => ({
  ...(await original<typeof import('@/lib/concierge/dogfood')>()),
  dogfoodRequest: mocks.bridge,
}));
vi.mock('@/lib/rate-limit', () => ({
  checkRateLimit: () => ({ success: true }),
  rateLimitResponse: vi.fn(),
  RATE_LIMITS: { send: {} },
}));
import { GET, POST } from './route';
const accountId = '11111111-1111-4111-8111-111111111111';
const request = (body: unknown, origin = 'http://localhost:8316') =>
  new Request('http://localhost:8316/api/concierge/dogfood', {
    method: 'POST',
    headers: { origin },
    body: JSON.stringify(body),
  });
beforeEach(() => {
  vi.clearAllMocks();
  mocks.role.mockResolvedValue({ accountId, userId: 'operator' });
  mocks.bridge.mockResolvedValue({ mode: 'simulation' });
});
describe('dogfood account boundary', () => {
  it('reads through verified viewer account without caching', async () => {
    const result = await GET();
    expect(result.status).toBe(200);
    expect(result.headers.get('cache-control')).toBe('private, no-store');
    expect(mocks.role).toHaveBeenCalledWith('viewer');
    expect(mocks.bridge).toHaveBeenCalledWith(accountId);
  });
  it('binds attestation to the verified actor', async () => {
    expect((await POST(request({ command: 'process' }))).status).toBe(200);
    expect(mocks.role).toHaveBeenCalledWith('agent');
    expect(mocks.bridge).toHaveBeenCalledWith(accountId, {
      command: 'process',
      attested_by: 'operator',
    });
  });
  it('rejects forged identity and unrecognized effects', async () => {
    for (const body of [
      { command: 'process', account_id: accountId },
      { command: 'approve', decision_id: 'd', attested_by: 'forged' },
      { command: 'execute_approved', decision_id: 'd' },
    ])
      expect((await POST(request(body))).status).toBe(400);
    expect(mocks.bridge).not.toHaveBeenCalled();
  });
  it('rejects cross-origin before accessing account', async () => {
    expect(
      (await POST(request({ command: 'process' }, 'https://evil.example')))
        .status
    ).toBe(403);
    expect(mocks.role).not.toHaveBeenCalled();
  });
  it('does not dispatch unauthenticated requests or malformed JSON', async () => {
    mocks.role.mockRejectedValueOnce(new Error('unauthorized'));
    expect((await GET()).status).toBe(401);
    expect(
      (
        await POST(
          new Request('http://localhost:8316/api/concierge/dogfood', {
            method: 'POST',
            body: '{',
          })
        )
      ).status
    ).toBe(400);
    expect(mocks.bridge).not.toHaveBeenCalled();
  });
  it('does not promote unresolved prospects to fake-phone CRM contacts', async () => {
    mocks.bridge.mockResolvedValue({
      mode: 'simulation',
      prospects: [
        { id: 'p', name: 'Person', status: 'qualified', phone: null },
      ],
    });
    expect(
      (await POST(request({ command: 'promote', prospect_id: 'p' }))).status
    ).toBe(409);
    expect(mocks.bridge).toHaveBeenCalledTimes(1);
  });
  it('promotes through canonical normalized identity and preserves existing contact fields', async () => {
    const contact = {
      id: 'existing',
      name: 'Canonical name',
      phone: '+27 (82) 000-0000',
      company: 'Canonical company',
      email: null,
    };
    const eq = vi.fn();
    const select = vi.fn();
    const maybeSingle = vi
      .fn()
      .mockResolvedValue({ data: contact, error: null });
    const query = { eq, select, maybeSingle };
    eq.mockReturnValue(query);
    select.mockReturnValue(query);
    const insert = vi.fn().mockResolvedValue({ error: null });
    const from = vi.fn((table: string) =>
      table === 'contacts' ? query : { insert }
    );
    mocks.role.mockResolvedValue({
      accountId,
      userId: 'operator',
      supabase: { from },
    });
    mocks.bridge
      .mockResolvedValueOnce({
        mode: 'simulation',
        prospects: [
          {
            id: 'p',
            name: 'Research name',
            company: 'Research company',
            phone: '+27820000000',
            status: 'qualified',
            source: 'fixture',
          },
        ],
      })
      .mockResolvedValueOnce({ status: 'linked' });
    expect(
      (await POST(request({ command: 'promote', prospect_id: 'p' }))).status
    ).toBe(200);
    expect(eq).toHaveBeenCalledWith('account_id', accountId);
    expect(eq).toHaveBeenCalledWith('phone_normalized', '27820000000');
    expect(mocks.bridge).toHaveBeenLastCalledWith(accountId, {
      command: 'link_contact',
      prospect_id: 'p',
      contact: { ...contact, phone: '+27820000000', account_id: accountId },
      attested_by: 'operator',
    });
    expect(insert).toHaveBeenCalledWith(
      expect.objectContaining({
        contact_id: 'existing',
        account_id: accountId,
        note_text: expect.stringContaining('[Simulation]'),
      })
    );
  });
});
