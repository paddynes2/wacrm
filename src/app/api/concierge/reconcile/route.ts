import { NextResponse } from 'next/server';
import { requireRole, toErrorResponse } from '@/lib/auth/account';
import { sameOrigin } from '@/lib/concierge/origin';
import { BridgeError, bridgeStatus } from '@/lib/concierge/bridge';
import { reconcileConcierge } from '@/lib/concierge/reconcile';
import { checkRateLimit, rateLimitResponse } from '@/lib/rate-limit';

export const runtime = 'nodejs';
export async function POST(request: Request) {
  try {
    const ctx = await requireRole('agent');
    if (!sameOrigin(request))
      return NextResponse.json(
        { error: 'Invalid request origin.' },
        { status: 403 }
      );
    const limit = checkRateLimit(`concierge-reconcile:${ctx.accountId}`, {
      limit: 3,
      windowMs: 60_000,
    });
    if (!limit.success) return rateLimitResponse(limit);
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (reader) {
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        size += part.value.byteLength;
        if (size > 1024) {
          await reader.cancel();
          return NextResponse.json(
            { error: 'Request is too large.' },
            { status: 413 }
          );
        }
        chunks.push(part.value);
      }
    }
    const raw = Buffer.concat(chunks).toString('utf8');
    let body: unknown;
    try {
      body = JSON.parse(raw);
    } catch {
      return NextResponse.json(
        { error: 'Expected an empty JSON object.' },
        { status: 400 }
      );
    }
    if (
      !body ||
      typeof body !== 'object' ||
      Array.isArray(body) ||
      Object.keys(body).length
    )
      return NextResponse.json(
        { error: 'Expected an empty JSON object.' },
        { status: 400 }
      );
    return NextResponse.json(
      await reconcileConcierge(ctx, await bridgeStatus(ctx.accountId))
    );
  } catch (error) {
    if (error instanceof BridgeError)
      return NextResponse.json(
        {
          error:
            'CRM reconciliation could not complete. Check the concierge connection and retry.',
        },
        { status: error.status }
      );
    return toErrorResponse(error);
  }
}
