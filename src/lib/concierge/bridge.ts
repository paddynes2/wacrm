/** Server-to-server adapter. The browser never selects an account, bot or transport. */
export class BridgeError extends Error {
  constructor(
    message: string,
    public status = 502
  ) {
    super(message);
  }
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function isUuid(value: unknown): value is string {
  return typeof value === 'string' && UUID.test(value);
}

async function call(
  path: string,
  method = 'GET',
  body?: Record<string, unknown>
) {
  const base = process.env.WACRM_BRIDGE_URL;
  const token = process.env.WACRM_BRIDGE_TOKEN;
  if (!base || !token)
    throw new BridgeError(
      'The concierge service is not connected. Configure the server connection first.',
      503
    );
  const url = new URL(base);
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new BridgeError('Invalid concierge service configuration.', 503);
  }
  let response: Response;
  try {
    response = await fetch(`${base.replace(/\/$/, '')}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
      cache: 'no-store',
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw new BridgeError(
      'The concierge service could not be reached. Refresh its status before retrying an action.',
      503
    );
  }
  const result = await response.json().catch(() => null);
  if (!response.ok) {
    const safe =
      result && typeof result.detail === 'string'
        ? result.detail
        : 'The concierge could not complete this action.';
    throw new BridgeError(
      safe.slice(0, 500),
      [400, 404, 409, 422, 503].includes(response.status)
        ? response.status
        : 502
    );
  }
  if (!result || typeof result !== 'object' || Array.isArray(result))
    throw new BridgeError('Invalid concierge response.');
  return result as Record<string, unknown>;
}

export async function bridgeStatus(accountId: string) {
  if (!isUuid(accountId)) throw new BridgeError('Invalid account.', 400);
  return call(`/workspace/${accountId}/status`);
}

export async function bridgeRequest(
  accountId: string,
  action: string,
  payload: Record<string, unknown>
) {
  if (!isUuid(accountId)) throw new BridgeError('Invalid account.', 400);
  if (action === 'setup')
    return call('/workspace', 'POST', { ...payload, account_id: accountId });
  return call(`/workspace/${accountId}/action`, 'POST', { ...payload, action });
}
