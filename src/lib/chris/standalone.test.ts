import { afterEach, expect, it, vi } from 'vitest';
import { sendTextMessage, sendMediaMessage, sendTemplateMessage, sendReactionMessage, sendInteractiveButtons, sendInteractiveList } from '@/lib/whatsapp/meta-api';
import { parseRequest } from './contracts';

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
it.each([sendTextMessage,sendMediaMessage,sendTemplateMessage,sendReactionMessage,sendInteractiveButtons,sendInteractiveList])('D20 standalone blocks Meta helper %s before fetch', async send => {
  vi.stubEnv('WACRM_STANDALONE','1'); const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
  await expect(send({} as never)).rejects.toThrow('Meta outbound is disabled');
  expect(fetch).not.toHaveBeenCalled();
});
it('T01 streaming body limits count UTF-8 bytes', async () => {
  const request=new Request('http://localhost/api/chris',{method:'POST',body:'é'.repeat(17000)});
  await expect(parseRequest(request)).rejects.toMatchObject({code:'body_too_large',status:413});
});
it('T01 malformed UTF-8 is rejected instead of silently replacing bytes', async () => {
  const request=new Request('http://localhost/api/chris',{method:'POST',body:new Uint8Array([0xff,0xfe])});
  await expect(parseRequest(request)).rejects.toMatchObject({code:'invalid_unicode'});
});
