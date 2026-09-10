import { timingSafeEqual } from 'node:crypto';
import { NextResponse } from 'next/server';
import { supabaseAdmin } from '@/lib/automations/admin-client';
import { assert, ChrisError, exact, parseRequest } from '@/lib/chris/contracts';
import { isUuid } from '@/lib/concierge/bridge';
import { projectBatch } from '@/lib/chris/projection';

export async function POST(request: Request) {
  const headers = { 'Cache-Control': 'private, no-store' };
  try {
    const token = process.env.WACRM_BRIDGE_TOKEN;
    assert(token && token.length >= 32, 'private_callback_unavailable', 503);
    const actual = Buffer.from(request.headers.get('authorization') ?? '');
    const expected = Buffer.from('Bearer ' + token);
    assert(actual.length === expected.length && timingSafeEqual(actual, expected), 'unauthorized', 401);
    const body = await parseRequest(request);
    exact(body, ['schema_version', 'account_id', 'projection_ids']);
    assert(body.schema_version === 1 && isUuid(body.account_id) && Array.isArray(body.projection_ids)
      && body.projection_ids.length >= 1 && body.projection_ids.length <= 50 && body.projection_ids.every(isUuid));
    return NextResponse.json(await projectBatch(supabaseAdmin(), body.account_id, body.projection_ids as string[]), { headers });
  } catch (error) {
    return NextResponse.json({ error: { code: error instanceof ChrisError ? error.code : 'projection_unavailable' } }, { status: error instanceof ChrisError ? error.status : 503, headers });
  }
}
