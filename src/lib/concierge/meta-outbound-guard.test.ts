import { afterEach, expect, it, vi } from 'vitest';
import { sendTextMessage, sendMediaMessage, sendTemplateMessage, sendReactionMessage, sendInteractiveButtons, sendInteractiveList } from '@/lib/whatsapp/meta-api';

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
it.each([sendTextMessage, sendMediaMessage, sendTemplateMessage, sendReactionMessage, sendInteractiveButtons, sendInteractiveList])('blocks every Meta outbound entrypoint before fetch', async send => {
  vi.stubEnv('WACRM_BRIDGE_URL', 'http://localhost:1');
  const fetch = vi.fn(() => { throw new Error('Must not fetch'); });
  vi.stubGlobal('fetch', fetch);
  // Deliberately no arguments: the deployment guard must run before parsing them.
  await expect((send as (args: unknown) => Promise<unknown>)(undefined)).rejects.toThrow('Use Concierge');
  expect(fetch).not.toHaveBeenCalled();
});
