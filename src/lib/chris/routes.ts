import { NextResponse } from 'next/server';
import { randomUUID } from 'node:crypto';
import { requireRole, toErrorResponse } from '@/lib/auth/account';
import { sameOrigin } from '@/lib/concierge/origin';
import { checkRateLimit, rateLimitResponse, RATE_LIMITS } from '@/lib/rate-limit';
import { chrisRequest } from './bridge';
import { assert, ChrisError, parseRequest, validateCommand, ownerCommand, uuid } from './contracts';

const headers = { 'Cache-Control': 'private, no-store' };
function failure(error: unknown) {
  if (error instanceof ChrisError) return NextResponse.json({ error: { code: error.code, message: error.message, retryable: false } }, { status: error.status, headers });
  const response = toErrorResponse(error);
  response.headers.set('Cache-Control','private, no-store');
  return response;
}
export async function get(request?: Request, path = '') {
  try {
    const ctx = await requireRole(path === '/export' ? 'owner' : 'viewer');
    if (request && ['/people', '/introductions', '/activity'].includes(path)) {
      const query = new URL(request.url).searchParams;
      assert([...query.keys()].every(k => ['cursor', 'limit'].includes(k)));
      const limit = Number(query.get('limit') ?? 25);
      assert(Number.isInteger(limit) && limit >= 1 && limit <= 100);
      const cursor = query.get('cursor') ?? ''; assert(cursor.length <= 1024 && /^[A-Za-z0-9_=-]*$/.test(cursor));
      path += `?limit=${limit}&cursor=${encodeURIComponent(cursor)}`;
    }
    const result = await chrisRequest(ctx.accountId, path);
    return NextResponse.json(result, { headers: { ...headers, ...(path === '/export' ? { 'Content-Disposition': 'attachment; filename="chris-export.json"' } : {}) } });
  } catch (error) { return failure(error); }
}
export async function detail(collection: string, id: string) {
  try { assert(uuid(id), 'not_found', 404); return get(undefined, `/${collection}/${id}`); }
  catch (error) { return failure(error); }
}
export async function post(request: Request) {
  try {
    assert(sameOrigin(request), 'cross_origin', 403);
    const ctx = await requireRole('agent');
    const limit = checkRateLimit(`chris:${ctx.userId}`, RATE_LIMITS.send);
    if (!limit.success) return rateLimitResponse(limit);
    const envelope = validateCommand(await parseRequest(request));
    assert(!ownerCommand(envelope.command) || ctx.role === 'owner', 'owner_required', 403);
    return NextResponse.json(await chrisRequest(ctx.accountId, '/commands', {
      envelope, actor: { user_id: ctx.userId, role: ctx.role, request_id: randomUUID() },
    }), { status: 202, headers });
  } catch (error) { return failure(error); }
}
