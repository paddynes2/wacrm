import { beforeEach, describe, expect, it, vi } from 'vitest';

const f = vi.hoisted(() => ({ role: vi.fn(), bridge: vi.fn(), ai: vi.fn() }));
vi.mock('@/lib/auth/account', () => ({
  requireRole: f.role,
  toErrorResponse: () =>
    Response.json({ error: 'Unauthorized' }, { status: 401 }),
}));
vi.mock('@/lib/ai/config', () => ({ loadAiConfig: f.ai }));
vi.mock('@/lib/concierge/bridge', async (original) => ({
  ...(await original<typeof import('@/lib/concierge/bridge')>()),
  bridgeStatus: f.bridge,
}));
import { GET } from './route';
import { BridgeError } from '@/lib/concierge/bridge';

const ACCOUNT = '11111111-1111-4111-8111-111111111111';
const db = { marker: 'owned-database-client' };
const workspace = {
  account_id: ACCOUNT,
  principal_name: 'Patrick',
  principal_phone: '+27820000000',
  offer: 'Implementation',
  timezone: 'Africa/Johannesburg',
};
const setup = {
  whatsapp_account_id: 'private-provider-account',
  whatsapp_armed: false,
  calendar_connected: false,
  live_ready: false,
};
beforeEach(() => {
  vi.clearAllMocks();
  f.role.mockResolvedValue({ accountId: ACCOUNT, supabase: db });
  f.bridge.mockResolvedValue({ mode: 'simulation', workspace, setup });
  f.ai.mockResolvedValue(null);
});

describe('read-only connection readiness', () => {
  it('authenticates a viewer before reading any service or credential', async () => {
    f.role.mockRejectedValue(new Error('no session'));
    expect((await GET()).status).toBe(401);
    expect(f.bridge).not.toHaveBeenCalled();
    expect(f.ai).not.toHaveBeenCalled();
  });
  it('binds both reads to the authenticated account and uses no-store', async () => {
    const response = await GET();
    expect(f.role).toHaveBeenCalledWith('viewer');
    expect(f.bridge).toHaveBeenCalledWith(ACCOUNT);
    expect(f.ai).toHaveBeenCalledWith(db, ACCOUNT, { requireActive: false });
    expect(response.headers.get('cache-control')).toBe('private, no-store');
    const body = await response.json();
    expect(body.mode).toBe('simulation');
    expect(body.brief.configured).toBe(true);
    expect(body.whatsapp.account_mapped).toBe(true);
    expect(body.whatsapp.live_connection_verified).toBeNull();
    expect(body.live_ready).toBe(false);
  });
  it('does not turn simulated connection flags into live readiness', async () => {
    f.bridge.mockResolvedValue({
      mode: 'simulation',
      workspace,
      setup: {
        ...setup,
        whatsapp_armed: true,
        calendar_connected: true,
        live_ready: true,
      },
    });
    const body = await (await GET()).json();
    expect(body.calendar.account_connected).toBe(true);
    expect(body.calendar.availability_verified).toBeNull();
    expect(body.live_ready).toBe(false);
  });
  it('keeps unknown transport and calendar fields unknown', async () => {
    f.bridge.mockResolvedValue({
      mode: 'live',
      workspace,
      setup: { whatsapp_armed: 'true', calendar_connected: 'yes' },
    });
    const body = await (await GET()).json();
    expect(body.whatsapp.delivery_enabled).toBeNull();
    expect(body.calendar.account_connected).toBeNull();
    expect(body.live_ready).toBeNull();
  });
  it('reports missing workspace as reachable but not configured', async () => {
    f.bridge.mockRejectedValue(new BridgeError('missing', 404));
    const response = await GET();
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.service.status).toBe('not_configured');
    expect(body.mode).toBe('unknown');
    expect(body.brief.configured).toBe(false);
  });
  it('returns actionable 503 while retaining independent owned AI readiness', async () => {
    f.bridge.mockRejectedValue(
      new BridgeError('secret-token-in-provider-error', 503)
    );
    f.ai.mockResolvedValue({
      apiKey: 'sk-private',
      isActive: true,
      provider: 'openai',
    });
    const response = await GET();
    expect(response.status).toBe(503);
    const body = await response.json();
    expect(body.service.status).toBe('unavailable');
    expect(body.ai.status).toBe('configured');
    expect(JSON.stringify(body)).not.toContain('secret-token');
  });
  it('refuses foreign and absent workspace mappings before projecting readiness', async () => {
    for (const value of [
      {
        ...workspace,
        account_id: 'foreign-account',
        principal_name: 'Secret owner',
      },
      {},
    ]) {
      f.bridge.mockResolvedValue({
        mode: 'live',
        workspace: value,
        setup: { whatsapp_armed: true, calendar_connected: true },
      });
      const response = await GET();
      expect(response.status).toBe(503);
      const body = await response.json();
      expect(body.whatsapp.account_mapped).toBeNull();
      expect(body.calendar.account_connected).toBeNull();
      expect(JSON.stringify(body)).not.toMatch(/foreign-account|Secret owner/);
    }
  });
  it('does not expose credentials, prompts, account IDs or provider extras', async () => {
    f.ai.mockResolvedValue({
      provider: 'anthropic',
      isActive: true,
      apiKey: 'sk-secret',
      embeddingsApiKey: 'embedding-secret',
      systemPrompt: 'private prompt',
      model: 'private model',
    });
    f.bridge.mockResolvedValue({
      mode: 'live',
      workspace,
      setup: { ...setup, token: 'bridge-secret' },
      secret: 'unrelated-secret',
    });
    const text = await (await GET()).text();
    for (const secret of [
      'sk-secret',
      'embedding-secret',
      'private prompt',
      'private model',
      'bridge-secret',
      'unrelated-secret',
      ACCOUNT,
      'private-provider-account',
      '+27820000000',
    ])
      expect(text).not.toContain(secret);
    expect(JSON.parse(text).ai.provider).toBe('Anthropic');
  });
  it('distinguishes absent AI configuration from an unreadable key', async () => {
    expect((await (await GET()).json()).ai.status).toBe('not_configured');
    f.ai.mockRejectedValue(new Error('decryption failed: secret'));
    const body = await (await GET()).json();
    expect(body.ai.status).toBe('unavailable');
    expect(JSON.stringify(body)).not.toContain('secret');
  });
  it('matches manual AI drafting when automatic replies are disabled', async () => {
    f.ai.mockResolvedValue({
      provider: 'openai',
      apiKey: 'sk-private',
      isActive: false,
    });
    const body = await (await GET()).json();
    expect(body.ai.status).toBe('configured');
    expect(body.ai.provider).toBe('OpenAI');
  });
});
