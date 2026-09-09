import { NextResponse } from 'next/server';
import { createHash } from 'node:crypto';
import { requireRole, toErrorResponse } from '@/lib/auth/account';
import { sameOrigin } from '@/lib/concierge/origin';
import { BridgeError } from '@/lib/concierge/bridge';
import {
  dogfoodRequest,
  validateDogfoodCommand,
  isObject,
} from '@/lib/concierge/dogfood';
import { normalizeProspectPhone } from '@/lib/concierge/prospecting';
import {
  checkRateLimit,
  rateLimitResponse,
  RATE_LIMITS,
} from '@/lib/rate-limit';

export const runtime = 'nodejs';
function failure(error: unknown) {
  return error instanceof BridgeError
    ? NextResponse.json({ error: error.message }, { status: error.status })
    : toErrorResponse(error);
}
export async function GET() {
  try {
    const ctx = await requireRole('viewer');
    return NextResponse.json(await dogfoodRequest(ctx.accountId), {
      headers: { 'Cache-Control': 'private, no-store' },
    });
  } catch (error) {
    return failure(error);
  }
}
export async function POST(request: Request) {
  try {
    if (!sameOrigin(request))
      return NextResponse.json(
        { error: 'Cross-origin request refused.' },
        { status: 403 }
      );
    const ctx = await requireRole('agent');
    const limit = checkRateLimit(`dogfood:${ctx.userId}`, RATE_LIMITS.send);
    if (!limit.success) return rateLimitResponse(limit);
    const raw = await request.text();
    if (raw.length > 32_000)
      return NextResponse.json(
        { error: 'Request too large.' },
        { status: 413 }
      );
    let body: unknown;
    try {
      body = JSON.parse(raw);
    } catch {
      return NextResponse.json({ error: 'Invalid JSON.' }, { status: 400 });
    }
    const command = validateDogfoodCommand(body);
    if (command.command === 'promote') {
      const report = await dogfoodRequest(ctx.accountId);
      const prospect = Array.isArray(report.prospects)
        ? report.prospects.find(
            (p) => isObject(p) && p.id === command.prospect_id
          )
        : undefined;
      if (!isObject(prospect))
        throw new BridgeError('Prospect not found.', 404);
      const phone =
        typeof prospect.phone === 'string'
          ? normalizeProspectPhone(prospect.phone)
          : null;
      const qualified =
        prospect.status === 'qualified' ||
        prospect.qualification === 'qualified' ||
        (isObject(prospect.qualification) &&
          prospect.qualification.verdict === 'qualified');
      if (!phone || !qualified)
        throw new BridgeError(
          'Qualify this person and record their phone before saving to CRM.',
          409
        );
      if (prospect.fixture === true && report.mode !== 'simulation')
        throw new BridgeError(
          'Fictional candidates cannot enter a live pilot.',
          409
        );
      const hash = createHash('sha256')
        .update(`dogfood-contact:${ctx.accountId}:${phone}`)
        .digest('hex');
      const id = `${hash.slice(0, 8)}-${hash.slice(8, 12)}-5${hash.slice(13, 16)}-8${hash.slice(17, 20)}-${hash.slice(20, 32)}`;
      const lookup = async () =>
        ctx.supabase
          .from('contacts')
          .select('id,name,phone,email,company')
          .eq('account_id', ctx.accountId)
          .eq('phone_normalized', phone.replace(/\D/g, ''))
          .maybeSingle();
      const existing = await lookup();
      if (existing.error) throw new Error('Contact lookup failed');
      let contact = existing.data;
      if (!contact) {
        const inserted = await ctx.supabase
          .from('contacts')
          .insert({
            id,
            account_id: ctx.accountId,
            user_id: ctx.userId,
            name: String(prospect.name || phone),
            phone,
            email: typeof prospect.email === 'string' ? prospect.email : null,
            company:
              typeof prospect.company === 'string' ? prospect.company : null,
          })
          .select('id,name,phone,email,company')
          .single();
        if (inserted.error && inserted.error.code !== '23505')
          throw new Error('Contact insert failed');
        contact = inserted.data;
        if (!contact) {
          const retry = await lookup();
          if (retry.error) throw new Error('Contact verification failed');
          contact = retry.data;
        }
      }
      if (!contact)
        throw new BridgeError(
          'Contact could not be verified. Refresh before retrying.',
          503
        );
      const note = `${report.mode === 'simulation' ? '[Simulation] ' : ''}Chris prospect research\nSource: ${String(prospect.source ?? 'Not supplied').slice(0, 2000)}\nFit: ${String(prospect.fit ?? 'Not supplied').slice(0, 4000)}\nQualification: ${JSON.stringify(prospect.qualification ?? prospect.status).slice(0, 4000)}\nPhone evidence: ${String(prospect.phone_source ?? prospect.source_ref ?? 'See concierge evidence').slice(0, 2000)}\nSaving to CRM does not establish permission to contact.`;
      const noteHash = createHash('sha256')
        .update(`dogfood-note:${ctx.accountId}:${contact.id}:${note}`)
        .digest('hex');
      const noteId = `${noteHash.slice(0, 8)}-${noteHash.slice(8, 12)}-5${noteHash.slice(13, 16)}-8${noteHash.slice(17, 20)}-${noteHash.slice(20, 32)}`;
      const savedNote = await ctx.supabase
        .from('contact_notes')
        .insert({
          id: noteId,
          contact_id: contact.id,
          account_id: ctx.accountId,
          user_id: ctx.userId,
          note_text: note,
        });
      if (savedNote.error && savedNote.error.code !== '23505')
        throw new BridgeError(
          'Contact saved, but its source note needs repair. Retry promotion; the existing contact will be preserved.',
          503
        );
      return NextResponse.json(
        await dogfoodRequest(ctx.accountId, {
          command: 'link_contact',
          prospect_id: prospect.id,
          contact: { ...contact, phone, account_id: ctx.accountId },
          attested_by: ctx.userId,
        })
      );
    }
    return NextResponse.json(
      await dogfoodRequest(ctx.accountId, {
        ...command,
        attested_by: ctx.userId,
      })
    );
  } catch (error) {
    return failure(error);
  }
}
