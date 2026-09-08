import { NextResponse } from 'next/server';
import { sameOrigin } from '@/lib/concierge/origin';
import { requireRole, toErrorResponse } from '@/lib/auth/account';
import {
  checkRateLimit,
  rateLimitResponse,
  RATE_LIMITS,
} from '@/lib/rate-limit';
import {
  BridgeError,
  bridgeRequest,
  bridgeStatus,
  isUuid,
} from '@/lib/concierge/bridge';
import {
  mirrorDirectMessages,
  type DirectMessage,
} from '@/lib/concierge/inbox';

export const runtime = 'nodejs';
const ACTIONS = new Set([
  'start',
  'draft',
  'consent',
  'takeover',
  'resume',
  'sync',
  'simulate_reply',
  'introduce',
  'propose',
  'book',
  'approve',
  'decline',
]);
const SETUP_FIELDS = [
  'principal_name',
  'principal_phone',
  'offer',
  'timezone',
  'booking_link',
];
const ACTION_FIELDS = [
  'chat_id',
  'pursuit_id',
  'revision',
  'text',
  'scope',
  'party',
  'source_ref',
  'fit',
  'profile_url',
  'start',
  'end',
  'timezone',
  'windows',
  'duration_minutes',
  'slot',
  'summary',
  'decision_id',
  'purpose',
  'reason',
];
function select(body: Record<string, unknown>, keys: string[]) {
  return Object.fromEntries(
    keys.filter((key) => body[key] !== undefined).map((key) => [key, body[key]])
  );
}
function errorResponse(error: unknown) {
  return error instanceof BridgeError
    ? NextResponse.json({ error: error.message }, { status: error.status })
    : toErrorResponse(error);
}

export async function GET() {
  try {
    const ctx = await requireRole('viewer');
    const { data: contacts, error } = await ctx.supabase
      .from('contacts')
      .select('id,name,phone,email,company,created_at')
      .eq('account_id', ctx.accountId)
      .order('created_at', { ascending: false })
      .limit(500);
    if (error) throw new Error('Contact lookup failed');
    let report: Record<string, unknown> | null = null;
    try {
      report = await bridgeStatus(ctx.accountId);
    } catch (err) {
      if (!(err instanceof BridgeError && err.status === 404)) throw err;
    }
    return NextResponse.json({
      contacts: contacts ?? [],
      workspace: report?.workspace ?? report?.setup ?? null,
      report,
      mode: report?.mode ?? process.env.WACRM_BRIDGE_MODE ?? 'live',
      contacts_limit: 500,
    });
  } catch (error) {
    return errorResponse(error);
  }
}

export async function POST(request: Request) {
  try {
    // Same-origin browser writes; identity still comes solely from the verified session.
    if (!sameOrigin(request))
      return NextResponse.json(
        { error: 'Cross-origin request refused.' },
        { status: 403 }
      );
    const ctx = await requireRole('agent');
    const limit = checkRateLimit(`concierge:${ctx.userId}`, RATE_LIMITS.send);
    if (!limit.success) return rateLimitResponse(limit);
    const raw = await request.text();
    if (raw.length > 32_000)
      return NextResponse.json(
        { error: 'Request too large.' },
        { status: 413 }
      );
    let body: Record<string, unknown>;
    try {
      body = JSON.parse(raw);
    } catch {
      return NextResponse.json({ error: 'Invalid JSON.' }, { status: 400 });
    }
    if (!body || typeof body !== 'object' || Array.isArray(body))
      return NextResponse.json(
        { error: 'An action is required.' },
        { status: 400 }
      );
    const action = body.action;
    if (action === 'setup') {
      await requireRole('admin');
      return NextResponse.json(
        await bridgeRequest(ctx.accountId, action, select(body, SETUP_FIELDS))
      );
    }
    if (typeof action !== 'string' || !ACTIONS.has(action))
      return NextResponse.json(
        { error: 'Unknown concierge action.' },
        { status: 400 }
      );
    if (!isUuid(body.contact_id))
      return NextResponse.json(
        { error: 'Choose a CRM contact.' },
        { status: 400 }
      );
    const { data: contact, error } = await ctx.supabase
      .from('contacts')
      .select('id,name,phone,email,company')
      .eq('id', body.contact_id)
      .eq('account_id', ctx.accountId)
      .maybeSingle();
    if (error) throw new Error('Contact lookup failed');
    if (!contact)
      return NextResponse.json(
        { error: 'Contact not found in this account.' },
        { status: 404 }
      );
    const result = await bridgeRequest(ctx.accountId, action, {
      ...select(body, ACTION_FIELDS),
      contact: { ...contact, name: contact.name || contact.phone },
    });
    if (
      Array.isArray(result.direct_messages) &&
      result.direct_messages.length
    ) {
      try {
        const messages = result.direct_messages
          .filter(
            (row: Record<string, unknown>) => row.contact_id === contact.id
          )
          .map((row: Record<string, unknown>) => {
            const { contact_id: _contactId, ...message } = row;
            void _contactId;
            return message as unknown as DirectMessage;
          });
        if (messages.length)
          result.inbox = await mirrorDirectMessages(ctx.supabase, {
            accountId: ctx.accountId,
            userId: ctx.userId,
            contactId: contact.id,
            messages,
          });
      } catch {
        result.crm_warning =
          'The concierge action completed, but its inbox copy needs a refresh. Use Refresh conversation; do not repeat the action.';
      }
    }
    // WACRM owns the contact; only readable outcome notes and verified direct messages are mirrored.
    if (action === 'start' && typeof body.fit === 'string' && body.fit.trim()) {
      const { error: noteError } = await ctx.supabase
        .from('contact_notes')
        .insert({
          account_id: ctx.accountId,
          contact_id: contact.id,
          user_id: ctx.userId,
          note_text: `Concierge briefing\n${body.fit.slice(0, 4000)}\nSource: ${String(body.source_ref ?? body.profile_url ?? 'Operator supplied').slice(0, 1000)}`,
        });
      if (noteError)
        result.crm_warning =
          'The concierge started, but the briefing note could not be saved. Do not repeat the action; inspect the timeline.';
    }
    return NextResponse.json(result);
  } catch (error) {
    return errorResponse(error);
  }
}
