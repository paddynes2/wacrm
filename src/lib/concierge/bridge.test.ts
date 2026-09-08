import { afterEach, describe, expect, it, vi } from 'vitest';
import { bridgeRequest, bridgeStatus } from './bridge';

const account = '11111111-1111-4111-8111-111111111111';
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});
describe('concierge bridge boundary', () => {
  it('fails without credentials before any network access', async () => {
    vi.stubEnv('WACRM_BRIDGE_URL', '');
    const fetcher = vi.fn();
    vi.stubGlobal('fetch', fetcher);
    await expect(bridgeStatus(account)).rejects.toThrow('not connected');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('rejects path injection before network access', async () => {
    const fetcher = vi.fn();
    vi.stubGlobal('fetch', fetcher);
    await expect(bridgeStatus('../someone')).rejects.toThrow('Invalid account');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('server account wins over an injected account in setup', async () => {
    vi.stubEnv('WACRM_BRIDGE_URL', 'http://127.0.0.1:8317');
    vi.stubEnv('WACRM_BRIDGE_TOKEN', 'test-only');
    const fetcher = vi
      .fn()
      .mockResolvedValue(Response.json({ mode: 'simulation' }));
    vi.stubGlobal('fetch', fetcher);
    await bridgeRequest(account, 'setup', {
      account_id: 'other',
      offer: 'Workflows',
    });
    expect(JSON.parse(fetcher.mock.calls[0][1].body).account_id).toBe(account);
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
      'Bearer test-only'
    );
  });
  it('reports timeout as uncertain reachability, without blind retry', async () => {
    vi.stubEnv('WACRM_BRIDGE_URL', 'http://127.0.0.1:8317');
    vi.stubEnv('WACRM_BRIDGE_TOKEN', 'test-only');
    const fetcher = vi.fn().mockRejectedValue(new Error('timeout'));
    vi.stubGlobal('fetch', fetcher);
    await expect(bridgeRequest(account, 'draft', {})).rejects.toThrow(
      'Refresh its status'
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it('preserves stale revision refusal', async () => {
    vi.stubEnv('WACRM_BRIDGE_URL', 'http://127.0.0.1:8317');
    vi.stubEnv('WACRM_BRIDGE_TOKEN', 'test-only');
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          Response.json({ detail: 'Refresh stale revision' }, { status: 409 })
        )
    );
    await expect(bridgeStatus(account)).rejects.toMatchObject({
      status: 409,
      message: 'Refresh stale revision',
    });
  });
});
