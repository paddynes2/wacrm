import { afterEach, expect, it, vi } from 'vitest';
import { chrisRequest } from './bridge';

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

it('forwards projection creation claims and acknowledgements through the real private bridge', async () => {
  vi.stubEnv('WACRM_BRIDGE_URL', 'http://127.0.0.1:18761');
  vi.stubEnv('WACRM_BRIDGE_TOKEN', 'synthetic-test-token');
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(Response.json({ status: 'accepted' })));
  vi.stubGlobal('fetch', fetch);
  const account = '11111111-1111-4111-8111-111111111111';
  const id = '22222222-2222-5222-8222-222222222222';
  for (const effect of ['claim', 'ack']) {
    await chrisRequest(account, `/projections/${id}/${effect}`, { digest: 'a'.repeat(64) });
    expect(fetch).toHaveBeenLastCalledWith(`http://127.0.0.1:18761/workspace/${account}/chris/projections/${id}/${effect}`, expect.objectContaining({ method: 'POST', redirect: 'error', cache: 'no-store' }));
  }
  await expect(chrisRequest(account, '/projections/../../secrets')).rejects.toMatchObject({ code: 'invalid_path' });
  expect(fetch).toHaveBeenCalledTimes(2);
});
