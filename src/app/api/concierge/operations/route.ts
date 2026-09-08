import { NextResponse } from 'next/server';
import { requireRole, toErrorResponse } from '@/lib/auth/account';
import { sameOrigin } from '@/lib/concierge/origin';
import { bridgeOperations, bridgeStatus, BridgeError, isUuid } from '@/lib/concierge/bridge';
import { normalizeProspectPhone } from '@/lib/concierge/prospecting';
import { checkRateLimit, rateLimitResponse, RATE_LIMITS } from '@/lib/rate-limit';

export const runtime = 'nodejs';
function failure(error: unknown) {
  return error instanceof BridgeError ? NextResponse.json({ error: error.message }, { status: error.status }) : toErrorResponse(error);
}
export async function GET() {
  try {
    const ctx = await requireRole('viewer');
    const [operations, workspace, lookup] = await Promise.all([
      bridgeOperations(ctx.accountId), bridgeStatus(ctx.accountId),
      ctx.supabase.from('contacts').select('id,name,phone').eq('account_id', ctx.accountId).limit(500),
    ]);
    if (lookup.error) throw new Error('Contact lookup failed');
    const ids = new Set((Array.isArray(workspace.pursuits) ? workspace.pursuits : []).map((p: {pursuit_id: string}) => p.pursuit_id));
    return NextResponse.json({ ...operations, contacts: (lookup.data ?? []).filter(c => ids.has(`wacrm:${c.id}`)) });
  } catch (error) { return failure(error); }
}
export async function POST(request: Request) {
  try {
    if (!sameOrigin(request)) return NextResponse.json({ error: 'Cross-origin request refused.' }, { status: 403 });
    const ctx = await requireRole('agent');
    const limit = checkRateLimit(`concierge-operations:${ctx.userId}`, RATE_LIMITS.send);
    if (!limit.success) return rateLimitResponse(limit);
    const raw = await request.text();
    if (raw.length > 32000) return NextResponse.json({error:'Request too large.'}, {status:413});
    let body: Record<string, unknown>;
    try { body = JSON.parse(raw); } catch { return NextResponse.json({error:'Invalid JSON.'}, {status:400}); }
    if (!body || typeof body !== 'object' || Array.isArray(body)) return NextResponse.json({error:'Command required.'}, {status:400});
    const fields: Record<string,string[]> = {
      create_campaign:['name','steps','pace_seconds','daily_cap'], enroll:['campaign_id','contact_ids'],
      pause_campaign:['campaign_id'], tick:[], watch:['contact_id','chat_id','enabled'],
    };
    const command = typeof body.command === 'string' ? body.command : '';
    if (!fields[command] || Object.keys(body).some(k => k !== 'command' && !fields[command].includes(k)))
      return NextResponse.json({error:'Unknown command or fields.'}, {status:400});
    const payload = { ...body };
    if (command === 'enroll' || command === 'watch') {
      const ids = command === 'enroll' ? body.contact_ids : [body.contact_id];
      if (!Array.isArray(ids) || !ids.length || ids.length > 100 || !ids.every(isUuid) || new Set(ids).size !== ids.length)
        return NextResponse.json({error:'Select 1–100 distinct CRM contacts.'}, {status:400});
      const { data, error } = await ctx.supabase.from('contacts').select('id,name,phone,email,company').eq('account_id', ctx.accountId).in('id',ids);
      if (error) throw new Error('Contact lookup failed');
      if (!data || data.length !== ids.length) return NextResponse.json({error:'Contact not found in this account.'}, {status:404});
      const contacts = data.map(c => ({...c,name:c.name || c.phone,phone:normalizeProspectPhone(c.phone),account_id:ctx.accountId}));
      if (contacts.some(c => !c.phone)) return NextResponse.json({error:'Contacts need an international phone number with country code.'}, {status:400});
      delete payload.contact_ids; delete payload.contact_id;
      if (command === 'enroll') payload.contacts = contacts;
      else payload.contact = contacts[0];
    }
    return NextResponse.json(await bridgeOperations(ctx.accountId, payload));
  } catch (error) { return failure(error); }
}
