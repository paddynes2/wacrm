import { beforeEach, describe, expect, it, vi } from 'vitest';
const f = vi.hoisted(() => ({
  role: vi.fn(),
  from: vi.fn(),
  contacts: [] as { id: string; phone: string }[],
  contactInsert: vi.fn(),
  noteInsert: vi.fn(),
  query: {} as Record<string, ReturnType<typeof vi.fn>>,
  rate: vi.fn(),
}));
vi.mock('@/lib/auth/account', () => ({
  requireRole: f.role,
  toErrorResponse: () => Response.json({ error: 'Denied' }, { status: 403 }),
}));
vi.mock('@/lib/rate-limit', () => ({
  checkRateLimit: f.rate,
  rateLimitResponse: () =>
    Response.json({ error: 'Rate limited' }, { status: 429 }),
  RATE_LIMITS: { send: {} },
}));
import { POST } from './route';
const account = '11111111-1111-4111-8111-111111111111';
const csv =
  'name,phone,source,fit\nJane,+27820000004,Research,Relevant workflows\nJohn,+27820000005,Article,Partner';
function request(body: unknown, origin = 'http://localhost:8316') {
  return new Request('http://localhost:8316/api/concierge/prospects', {
    method: 'POST',
    headers: { origin },
    body: JSON.stringify(body),
  });
}
beforeEach(() => {
  vi.clearAllMocks();
  f.contacts = [];
  f.rate.mockReturnValue({ success: true });
  f.query = Object.fromEntries(
    ['select', 'eq', 'order'].map((key) => [key, vi.fn(() => f.query)])
  );
  f.query.range = vi.fn(async () => ({ data: f.contacts, error: null }));
  f.query.maybeSingle = vi.fn(async () => ({ data: null, error: null }));
  f.contactInsert.mockResolvedValue({ error: null });
  f.noteInsert.mockResolvedValue({ error: null });
  f.from.mockImplementation((table) =>
    table === 'contacts'
      ? { ...f.query, insert: f.contactInsert }
      : { insert: f.noteInsert }
  );
  f.role.mockResolvedValue({
    accountId: account,
    userId: account,
    supabase: { from: f.from },
  });
});
describe('prospect import boundary and retry behavior', () => {
  it('previews without any writes and identifies formatted existing phones', async () => {
    f.contacts = [{ id: 'existing', phone: '+27 (82) 000-0004' }];
    const response = await POST(request({ action: 'preview', csv }));
    expect((await response.json()).rows[0].duplicate).toBe(true);
    expect(f.query.eq).toHaveBeenCalledWith('account_id', account);
    expect(f.contactInsert).not.toHaveBeenCalled();
  });
  it('rejects foreign IDs, extra fields and invalid selections', async () => {
    for (const extra of [
      { account_id: 'foreign' },
      { contact_id: 'foreign' },
      { selected_rows: [900] },
      { selected_rows: [2, 2] },
    ])
      expect(
        (
          await POST(
            request({ action: 'import', csv, selected_rows: [2], ...extra })
          )
        ).status
      ).toBe(400);
    expect(f.contactInsert).not.toHaveBeenCalled();
  });
  it('requires agent and refuses cross-origin calls before auth', async () => {
    expect(
      (await POST(request({ action: 'import', csv }, 'https://evil.example')))
        .status
    ).toBe(403);
    expect(f.role).not.toHaveBeenCalled();
    f.role.mockRejectedValue(new Error('Viewer'));
    expect((await POST(request({ action: 'preview', csv }))).status).toBe(403);
    expect(f.role).toHaveBeenCalledWith('agent');
  });
  it('imports only selected rows and persists canonical account plus research note', async () => {
    const response = await POST(
      request({ action: 'import', csv, selected_rows: [3] })
    );
    expect((await response.json()).results[0].status).toBe('imported');
    expect(f.contactInsert).toHaveBeenCalledTimes(1);
    expect(f.contactInsert.mock.calls[0][0]).toMatchObject({
      account_id: account,
      user_id: account,
      name: 'John',
    });
    expect(f.noteInsert.mock.calls[0][0].note_text).toContain(
      'Source: Article'
    );
  });
  it('reports partial failures and reuses deterministic contact and note IDs on retry', async () => {
    f.noteInsert.mockResolvedValueOnce({ error: { code: '500' } });
    let response = await POST(
      request({ action: 'import', csv, selected_rows: [2] })
    );
    expect((await response.json()).results[0].status).toBe('note_failed');
    const saved = f.contactInsert.mock.calls[0][0];
    const noteId = f.noteInsert.mock.calls[0][0].id;
    f.contacts = [{ id: saved.id, phone: saved.phone }];
    response = await POST(
      request({ action: 'import', csv, selected_rows: [2] })
    );
    expect((await response.json()).results[0].status).toBe('already_imported');
    expect(f.contactInsert).toHaveBeenCalledTimes(1);
    expect(f.noteInsert.mock.calls[1][0].id).toBe(noteId);
  });
  it('does not overwrite native existing contacts or append their notes', async () => {
    f.contacts = [{ id: 'native', phone: '+27820000004' }];
    const response = await POST(
      request({ action: 'import', csv, selected_rows: [2] })
    );
    expect((await response.json()).results[0].status).toBe('duplicate');
    expect(f.contactInsert).not.toHaveBeenCalled();
    expect(f.noteInsert).not.toHaveBeenCalled();
  });
  it('does not mistake unverified uniqueness failures for successful imports', async () => {
    f.contactInsert.mockResolvedValue({ error: { code: '23505' } });
    const response = await POST(
      request({ action: 'import', csv, selected_rows: [2] })
    );
    expect((await response.json()).results[0].status).toBe('failed');
    expect(f.noteInsert).not.toHaveBeenCalled();
  });
  it('continues after row write errors and refuses invalid rows', async () => {
    f.contactInsert.mockResolvedValueOnce({ error: { code: '500' } });
    const response = await POST(
      request({ action: 'import', csv, selected_rows: [2, 3] })
    );
    expect(
      (await response.json()).results.map((r: { status: string }) => r.status)
    ).toEqual(['failed', 'imported']);
    const invalid = await POST(
      request({
        action: 'import',
        csv: 'name,phone,source\nJane,0820000004,Research',
        selected_rows: [2],
      })
    );
    expect((await invalid.json()).results[0].status).toBe('invalid');
  });
  it('bounds bodies and rate limits', async () => {
    expect(
      (await POST(request({ action: 'preview', csv: 'x'.repeat(400001) })))
        .status
    ).toBe(413);
    f.rate.mockReturnValue({ success: false });
    expect((await POST(request({ action: 'preview', csv }))).status).toBe(429);
  });
});
