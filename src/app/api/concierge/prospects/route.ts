import { createHash } from 'node:crypto';
import { NextResponse } from 'next/server';
import { requireRole, toErrorResponse } from '@/lib/auth/account';
import { sameOrigin } from '@/lib/concierge/origin';
import {
  checkRateLimit,
  rateLimitResponse,
  RATE_LIMITS,
} from '@/lib/rate-limit';
import {
  previewProspects,
  normalizeProspectPhone,
  MAX_CSV_LENGTH,
} from '@/lib/concierge/prospecting';

export const runtime = 'nodejs';
function stableId(value: string) {
  const hash = createHash('sha256').update(value).digest('hex');
  return `${hash.slice(0, 8)}-${hash.slice(8, 12)}-5${hash.slice(13, 16)}-8${hash.slice(17, 20)}-${hash.slice(20, 32)}`;
}
export async function POST(request: Request) {
  try {
    if (!sameOrigin(request))
      return NextResponse.json(
        { error: 'Cross-origin request refused.' },
        { status: 403 }
      );
    const ctx = await requireRole('agent');
    const limit = checkRateLimit(`prospects:${ctx.userId}`, RATE_LIMITS.send);
    if (!limit.success) return rateLimitResponse(limit);
    const raw = await request.text();
    if (raw.length > MAX_CSV_LENGTH * 2)
      return NextResponse.json(
        { error: 'Request too large.' },
        { status: 413 }
      );
    let body;
    try {
      body = JSON.parse(raw);
    } catch {
      return NextResponse.json({ error: 'Invalid JSON.' }, { status: 400 });
    }
    if (
      !body ||
      typeof body.csv !== 'string' ||
      !['preview', 'import'].includes(body.action) ||
      Object.keys(body).some(
        (key) => !['csv', 'action', 'selected_rows'].includes(key)
      )
    )
      return NextResponse.json(
        {
          error:
            'Provide action, CSV and selected_rows only. Account and contact IDs are not accepted.',
        },
        { status: 400 }
      );
    let rows;
    try {
      rows = previewProspects(body.csv);
    } catch (error) {
      return NextResponse.json(
        { error: (error as Error).message },
        { status: 400 }
      );
    }
    const existing = new Map<string, string>();
    // Native contacts accept formatted numbers. Scan bounded account pages so formatting cannot hide duplicates.
    for (let offset = 0; ; offset += 1000) {
      if (offset >= 10_000)
        return NextResponse.json(
          {
            error:
              'This import supports workspaces below 10,000 contacts. Use the native Contacts importer for larger accounts.',
          },
          { status: 409 }
        );
      const { data: contacts, error: lookupError } = await ctx.supabase
        .from('contacts')
        .select('id,phone')
        .eq('account_id', ctx.accountId)
        .order('id')
        .range(offset, offset + 999);
      if (lookupError) throw new Error('Contact lookup failed');
      for (const contact of contacts ?? []) {
        const phone = normalizeProspectPhone(contact.phone);
        if (phone) existing.set(phone, contact.id);
      }
      if ((contacts ?? []).length < 1000) break;
    }
    if (body.action === 'preview')
      return NextResponse.json({
        rows: rows.map((row) => ({
          ...row,
          duplicate: existing.has(row.prospect.phone),
          retryable:
            existing.get(row.prospect.phone) ===
            stableId(`prospect:${ctx.accountId}:${row.prospect.phone}`),
        })),
      });
    if (
      !Array.isArray(body.selected_rows) ||
      !body.selected_rows.length ||
      body.selected_rows.some(
        (n: unknown) =>
          !Number.isInteger(n) || !rows.some((row) => row.row === n)
      ) ||
      new Set(body.selected_rows).size !== body.selected_rows.length
    )
      return NextResponse.json(
        { error: 'Select valid, unique preview row numbers.' },
        { status: 400 }
      );
    const results = [];
    for (const row of rows.filter((row) =>
      body.selected_rows.includes(row.row)
    )) {
      if (row.errors.length) {
        results.push({
          row: row.row,
          status: 'invalid',
          error: row.errors.join(' '),
        });
        continue;
      }
      const p = row.prospect;
      const id = stableId(`prospect:${ctx.accountId}:${p.phone}`);
      const previous = existing.get(p.phone);
      if (previous && previous !== id) {
        results.push({
          row: row.row,
          status: 'duplicate',
          contact_id: previous,
        });
        continue;
      }
      if (!previous) {
        const { error } = await ctx.supabase
          .from('contacts')
          .insert({
            id,
            account_id: ctx.accountId,
            user_id: ctx.userId,
            name: p.name,
            phone: p.phone,
            email: p.email || null,
            company: p.company || null,
          });
        if (error && error.code !== '23505') {
          results.push({
            row: row.row,
            status: 'failed',
            error: 'Contact was not saved. Retry this row.',
          });
          continue;
        }
        // A concurrent retry can win the deterministic ID. Verify ownership before adding its note.
        if (error) {
          const { data, error: verifyError } = await ctx.supabase
            .from('contacts')
            .select('id')
            .eq('account_id', ctx.accountId)
            .eq('id', id)
            .eq('phone', p.phone)
            .maybeSingle();
          if (verifyError || !data) {
            results.push({
              row: row.row,
              status: 'failed',
              error:
                'Contact could not be verified. Refresh Contacts before retrying.',
            });
            continue;
          }
        }
        existing.set(p.phone, id);
      }
      const note = `Prospect research (operator supplied; not independently verified)\nSource: ${p.source}\nProfile: ${p.profile_url || 'Not supplied'}\nFit: ${p.fit || 'Not supplied'}\nImport does not establish permission to contact.`;
      const { error } = await ctx.supabase
        .from('contact_notes')
        .insert({
          id: stableId(`prospect-note:${ctx.accountId}:${id}:${note}`),
          account_id: ctx.accountId,
          contact_id: id,
          user_id: ctx.userId,
          note_text: note,
        });
      results.push({
        row: row.row,
        contact_id: id,
        status:
          error && error.code !== '23505'
            ? 'note_failed'
            : previous
              ? 'already_imported'
              : 'imported',
        ...(error && error.code !== '23505'
          ? {
              error:
                'Contact saved, but source note failed. Retry this row to repair its note.',
            }
          : {}),
      });
    }
    return NextResponse.json({ results });
  } catch (error) {
    return toErrorResponse(error);
  }
}
