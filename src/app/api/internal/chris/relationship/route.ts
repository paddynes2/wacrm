import { timingSafeEqual } from 'node:crypto';
import { NextResponse } from 'next/server';
import { supabaseAdmin } from '@/lib/automations/admin-client';
import { assert, ChrisError, exact, object, parseRequest } from '@/lib/chris/contracts';
import { isUuid } from '@/lib/concierge/bridge';
import { chrisRequest } from '@/lib/chris/bridge';
import { stableId } from '@/lib/chris/projection';

/** Wake payload identifies a person; immutable account-owned data supplies the query. */
export async function POST(request: Request) {
  const headers = { 'Cache-Control': 'private, no-store' };
  try {
    const token = process.env.WACRM_BRIDGE_TOKEN;
    assert(token && token.length >= 32, 'private_callback_unavailable', 503);
    const actual = Buffer.from(request.headers.get('authorization') ?? '');
    const expected = Buffer.from('Bearer ' + token);
    assert(actual.length === expected.length && timingSafeEqual(actual, expected), 'unauthorized', 401);
    const body = await parseRequest(request);
    exact(body, ['schema_version', 'account_id', 'person_id']);
    assert(body.schema_version === 1 && isUuid(body.account_id) && isUuid(body.person_id));
    const result = await chrisRequest(body.account_id, '/people/' + body.person_id);
    assert(object(result.item), 'person_unavailable', 409);
    const person = result.item;
    const db = supabaseAdmin();
    // Exact matches only; no caller-supplied filter expressions or bulk CRM dump.
    let query = db.from('contacts').select('id,account_id,name,company,phone_normalized').eq('account_id', body.account_id);
    if (typeof person.phone_e164 === 'string') query = query.eq('phone_normalized', person.phone_e164.replace(/^\+/, ''));
    else {
      assert(typeof person.display_name === 'string' && typeof person.company_name === 'string', 'identity_unresolved');
      query = query.eq('name', person.display_name).eq('company', person.company_name);
    }
    const matches = await query.limit(3);
    assert(!matches.error && Array.isArray(matches.data) && matches.data.every(r => r.account_id === body.account_id), 'relationship_unavailable', 503);
    const ownProjection = person.crm_contact_projected === true && matches.data.length === 1 && matches.data[0].id === stableId(`chris-contact:${body.account_id}:${body.person_id}`);
    return NextResponse.json({ known: matches.data.length > 0 && !ownProjection, fresh: true, coverage: 'Current WACRM contacts: exact phone or exact name and company only. Existing Chris-sourced follow-through is preserved. External networks and aliases are not covered.' }, { headers });
  } catch (error) {
    return NextResponse.json({ error: { code: error instanceof ChrisError ? error.code : 'relationship_unavailable' } }, { status: error instanceof ChrisError ? error.status : 503, headers });
  }
}
