import { NextResponse } from 'next/server';
import { requireRole, toErrorResponse } from '@/lib/auth/account';
import { loadAiConfig } from '@/lib/ai/config';
import { BridgeError, bridgeStatus } from '@/lib/concierge/bridge';

export const runtime = 'nodejs';

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
function flag(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

export async function GET() {
  try {
    const ctx = await requireRole('viewer');
    const [bridge, ai] = await Promise.allSettled([
      bridgeStatus(ctx.accountId),
      loadAiConfig(ctx.supabase, ctx.accountId, { requireActive: false }),
    ]);
    let service: 'available' | 'not_configured' | 'unavailable' = 'unavailable';
    let mode: 'simulation' | 'live' | 'unknown' = 'unknown';
    let workspace: Record<string, unknown> | null = null;
    let setup: Record<string, unknown> | null = null;
    let message =
      'The concierge service could not be checked. Ask the workspace administrator to check its server connection, then refresh.';

    if (bridge.status === 'fulfilled') {
      const reportedWorkspace = object(bridge.value.workspace);
      const reportedMode = bridge.value.mode;
      // A connected service is not evidence that its response belongs to this account.
      if (
        reportedWorkspace?.account_id === ctx.accountId &&
        (reportedMode === 'simulation' || reportedMode === 'live')
      ) {
        service = 'available';
        mode = reportedMode;
        workspace = reportedWorkspace;
        setup = object(bridge.value.setup);
        message = 'The concierge service answered for this workspace.';
      } else {
        message =
          'The concierge service returned an unexpected workspace. Ask the administrator to check the account connection.';
      }
    } else if (
      bridge.reason instanceof BridgeError &&
      bridge.reason.status === 404
    ) {
      service = 'not_configured';
      message =
        'The service is reachable. Create your concierge brief to set up this workspace.';
    }

    const hasText = (value: unknown) =>
      typeof value === 'string' && value.trim().length > 0;
    const aiConfig = ai.status === 'fulfilled' ? ai.value : null;
    const aiConfigured = Boolean(aiConfig && hasText(aiConfig.apiKey));
    const body = {
      checked_at: new Date().toISOString(),
      mode,
      service: { status: service, message },
      brief: {
        configured: Boolean(
          workspace &&
          hasText(workspace.principal_name) &&
          hasText(workspace.principal_phone) &&
          hasText(workspace.offer) &&
          hasText(workspace.timezone)
        ),
      },
      whatsapp: {
        account_mapped: setup ? hasText(setup.whatsapp_account_id) : null,
        delivery_enabled: flag(setup?.whatsapp_armed),
        live_connection_verified: null,
      },
      calendar: {
        account_connected: flag(setup?.calendar_connected),
        availability_verified: null,
      },
      ai: {
        status:
          ai.status === 'rejected'
            ? 'unavailable'
            : aiConfigured
              ? 'configured'
              : 'not_configured',
        provider:
          aiConfigured && aiConfig?.provider === 'openai'
            ? 'OpenAI'
            : aiConfigured && aiConfig?.provider === 'anthropic'
              ? 'Anthropic'
              : null,
      },
      live_ready: mode === 'live' ? flag(setup?.live_ready) : false,
      ...(service === 'unavailable' ? { error: message } : {}),
    };
    return NextResponse.json(body, {
      status: service === 'unavailable' ? 503 : 200,
      headers: { 'Cache-Control': 'private, no-store' },
    });
  } catch (error) {
    return toErrorResponse(error);
  }
}
