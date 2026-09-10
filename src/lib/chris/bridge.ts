import { assert, ChrisError, object, uuid, type Row } from './contracts';

export async function chrisRequest(account: string, path = '', body?: Row) {
  assert(uuid(account), 'invalid_account');
  assert(/^\/(?:[a-z]+)(?:\/[a-f0-9-]+)?(?:\/(?:ack|claim))?(?:\?[^#]*)?$/.test(path) || path === '', 'invalid_path');
  const base = process.env.WACRM_BRIDGE_URL, token = process.env.WACRM_BRIDGE_TOKEN;
  assert(base && token, 'service_not_connected', 503);
  const url = new URL(base);
  assert(url.protocol === 'https:' || (url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)), 'invalid_service_origin', 503);
  assert(!url.username && !url.password && !url.search && !url.hash, 'invalid_service_origin', 503);
  let response: Response;
  try {
    response = await fetch(`${base.replace(/\/$/, '')}/workspace/${account}/chris${path}`, {
      method: body ? 'POST' : 'GET', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined, cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(15000),
    });
  } catch { throw new ChrisError('service_unavailable', 503); }
  const result: unknown = await response.json().catch(() => null);
  assert(object(result), 'invalid_service_response', 502);
  if (!response.ok) throw new ChrisError(object(result.error) && typeof result.error.code === 'string' ? result.error.code : 'service_error', response.status);
  return result;
}
