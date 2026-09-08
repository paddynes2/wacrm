'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  CalendarDays,
  Check,
  CircleHelp,
  ClipboardList,
  FlaskConical,
  Loader2,
  MessageCircle,
  Plug,
  RefreshCw,
  ShieldCheck,
  Smartphone,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface Readiness {
  checked_at: string;
  mode: 'simulation' | 'live' | 'unknown';
  service: {
    status: 'available' | 'not_configured' | 'unavailable';
    message: string;
  };
  brief: { configured: boolean };
  whatsapp: {
    account_mapped: boolean | null;
    delivery_enabled: boolean | null;
    live_connection_verified: null;
  };
  calendar: { account_connected: boolean | null; availability_verified: null };
  ai: {
    status: 'configured' | 'not_configured' | 'unavailable';
    provider: string | null;
  };
  live_ready: boolean | null;
  error?: string;
}
interface CheckItem {
  title: string;
  label: string;
  ready: boolean;
  description: string;
  next: string;
  icon: typeof Plug;
  href?: string;
  link?: string;
}

export function ConnectionReadiness() {
  const [data, setData] = useState<Readiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const active = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/concierge/readiness', {
        cache: 'no-store',
        signal: controller.signal,
      });
      const body = await response.json();
      if (
        !body ||
        !body.service ||
        !body.brief ||
        !body.whatsapp ||
        !body.calendar ||
        !body.ai ||
        !['simulation', 'live', 'unknown'].includes(body.mode)
      ) {
        throw new Error(
          typeof body?.error === 'string'
            ? body.error
            : 'Connection status could not be loaded. Please try again.'
        );
      }
      if (active.current === controller) {
        setData(body);
        if (!response.ok)
          setError(
            body.error ??
              'The concierge service is unavailable. The checks below show what could be confirmed.'
          );
      }
    } catch (e) {
      if (!controller.signal.aborted && active.current === controller)
        setError(
          e instanceof Error
            ? e.message
            : 'Connection status could not be loaded.'
        );
    } finally {
      if (active.current === controller) setLoading(false);
    }
  }, []);
  useEffect(() => {
    void refresh();
    return () => active.current?.abort();
  }, [refresh]);

  const checks: CheckItem[] = data
    ? [
        {
          title: 'Concierge service',
          label:
            data.service.status === 'available'
              ? 'Available'
              : data.service.status === 'not_configured'
                ? 'Ready for setup'
                : 'Unavailable',
          ready: data.service.status === 'available',
          icon: Plug,
          description: data.service.message,
          next:
            data.service.status === 'unavailable'
              ? 'Ask your workspace administrator to check the private service connection and account mapping, then refresh this page.'
              : 'The service is checked for your signed-in workspace only.',
          href: '/concierge',
          link: 'Open Concierge',
        },
        {
          title: 'Your business brief',
          label: data.brief.configured ? 'Configured' : 'Not configured',
          ready: data.brief.configured,
          icon: ClipboardList,
          description: data.brief.configured
            ? 'Chris has a principal name, WhatsApp number, offer and timezone for this workspace.'
            : 'Tell Chris whom he represents, what you offer, and which timezone to use.',
          next: 'Your number identifies the person Chris introduces. It is separate from the assistant’s own number.',
          href: '/concierge',
          link: data.brief.configured ? 'View your brief' : 'Set up your brief',
        },
        {
          title: 'Assistant WhatsApp number',
          label:
            data.whatsapp.account_mapped === null
              ? 'Not checked'
              : data.whatsapp.account_mapped
                ? 'Account mapped'
                : 'Not mapped',
          ready: data.whatsapp.account_mapped === true,
          icon: Smartphone,
          description: data.whatsapp.account_mapped
            ? 'The service has an assistant WhatsApp account mapped to this workspace. This does not verify that the provider session is connected.'
            : 'Use a dedicated number your business controls for Chris, then link its WhatsApp account to this workspace.',
          next: 'Register the owned number in WhatsApp Business, complete the provider’s linking flow, and have the administrator map that account. Number ownership and live connection have not been verified here.',
        },
        {
          title: 'Calendar access',
          label:
            data.calendar.account_connected === null
              ? 'Not checked'
              : data.calendar.account_connected
                ? 'Account connected'
                : 'Not connected',
          ready: data.calendar.account_connected === true,
          icon: CalendarDays,
          description: data.calendar.account_connected
            ? 'The calendar connector reports an account connection. This check has not fetched availability or created a meeting.'
            : 'Connect the principal’s calendar to coordinate available times and prepare meetings.',
          next: 'Ask the administrator to connect the intended calendar account. Chris checks real availability when proposing times; an unavailable calendar must remain unverified.',
        },
        {
          title: 'AI drafting',
          label:
            data.ai.status === 'configured'
              ? `${data.ai.provider ?? 'Provider'} configured`
              : data.ai.status === 'unavailable'
                ? 'Could not check'
                : 'Not configured',
          ready: data.ai.status === 'configured',
          icon: Bot,
          description:
            data.ai.status === 'configured'
              ? 'A provider configuration and readable key are available for this account. No AI request was made by this check.'
              : data.ai.status === 'unavailable'
                ? 'The account’s AI configuration could not be read. Ask an administrator to check it.'
                : 'Add your own provider key in AI Agents. Editable message drafts work without it.',
          next: 'Provider credentials stay on the server. Use Draft with AI in Concierge when you want to test a real draft.',
          href: '/agents',
          link: 'Open AI Agents',
        },
        {
          title: 'Message delivery',
          label:
            data.whatsapp.delivery_enabled === null
              ? 'Not checked'
              : data.whatsapp.delivery_enabled
                ? 'Enabled in service'
                : 'Paused',
          ready:
            data.mode === 'live' &&
            data.whatsapp.delivery_enabled === true &&
            data.live_ready === true,
          icon: MessageCircle,
          description:
            data.mode === 'simulation'
              ? 'This is a simulation workspace. Its messages and calendar outcomes do not establish live delivery readiness.'
              : data.whatsapp.delivery_enabled
                ? 'The service reports that WhatsApp delivery is enabled. Each message still needs its own permissions and approval.'
                : 'Live delivery has not been confirmed. Connection setup does not itself authorize sending.',
          next: 'Before enabling live work, verify the assistant account, recipient permissions, approval flow and intended calendar. This page makes no configuration changes.',
        },
      ]
    : [];

  return (
    <div
      className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 sm:p-6 lg:p-8"
      aria-busy={loading}
    >
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Badge variant="secondary" className="mb-3 gap-1.5">
            <Plug className="size-3" />
            Connections
          </Badge>
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            Know what Chris can work with.
          </h2>
          <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-7">
            A read-only view of your workspace’s setup. Configuration,
            simulation and verified live operation are shown separately.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void refresh()}
          disabled={loading}
        >
          {loading ? <Loader2 className="animate-spin" /> : <RefreshCw />}
          Refresh status
        </Button>
      </header>
      {error && (
        <div
          role="alert"
          className="border-destructive/20 bg-destructive/5 flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 text-sm"
        >
          <p className="text-destructive min-w-0 break-words">{error}</p>
          <Button
            variant="outline"
            onClick={() => void refresh()}
            disabled={loading}
          >
            Try again
          </Button>
        </div>
      )}
      {data && (
        <section
          className={`flex flex-col gap-4 rounded-xl border p-5 sm:flex-row sm:items-center sm:justify-between ${data.mode === 'simulation' ? 'border-amber-500/25 bg-amber-500/5' : 'bg-card'}`}
        >
          <div className="flex items-start gap-3">
            {data.mode === 'simulation' ? (
              <FlaskConical className="mt-0.5 size-5 shrink-0 text-amber-600 dark:text-amber-400" />
            ) : (
              <ShieldCheck className="text-primary mt-0.5 size-5 shrink-0" />
            )}
            <div>
              <h3 className="text-sm font-semibold">
                {data.mode === 'simulation'
                  ? 'Simulation workspace'
                  : data.mode === 'live'
                    ? 'Live workspace configuration'
                    : 'Workspace mode not yet verified'}
              </h3>
              <p className="text-muted-foreground mt-1 max-w-2xl text-xs leading-6">
                {data.mode === 'simulation'
                  ? 'Practice introductions and scheduling here. Simulated accounts, replies and meetings are not proof that your live connections work.'
                  : data.live_ready === true
                    ? 'The service reports live readiness. The individual checks below describe the evidence available.'
                    : 'Live readiness has not been confirmed. Review the setup below before using external messaging or calendars.'}
              </p>
            </div>
          </div>
          <Link
            href="/concierge"
            className="text-primary inline-flex shrink-0 items-center gap-2 text-sm font-medium"
          >
            Go to Concierge
            <ArrowRight className="size-4" />
          </Link>
        </section>
      )}
      {!data && loading ? (
        <div
          role="status"
          aria-label="Checking connections"
          className="grid gap-4 md:grid-cols-2"
        >
          {[0, 1, 2, 3].map((key) => (
            <div key={key} className="bg-muted h-48 animate-pulse rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid items-stretch gap-4 md:grid-cols-2">
          {checks.map((item) => (
            <section
              key={item.title}
              className="bg-card flex min-w-0 flex-col rounded-xl border p-5 sm:p-6"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-xl">
                    <item.icon className="size-4" />
                  </span>
                  <h3 className="text-sm font-semibold">{item.title}</h3>
                </div>
                <Badge variant="outline" className="shrink-0 gap-1 text-[10px]">
                  {item.ready && <Check className="size-3" />}
                  {item.label}
                </Badge>
              </div>
              <p className="mt-4 text-sm leading-7">{item.description}</p>
              <p className="text-muted-foreground mt-3 text-xs leading-6">
                {item.next}
              </p>
              {item.href && (
                <Link
                  href={item.href}
                  className="text-primary mt-auto flex items-center gap-1 pt-5 text-xs font-medium"
                >
                  {item.link}
                  <ArrowUpRight className="size-3.5" />
                </Link>
              )}
            </section>
          ))}
        </div>
      )}
      <footer className="text-muted-foreground flex flex-wrap items-start justify-between gap-4 border-t pt-4 text-xs leading-6">
        <p className="flex max-w-2xl gap-2">
          <CircleHelp className="mt-1 size-3.5 shrink-0" />
          <span>
            This check does not send messages, contact an AI provider, verify
            number ownership or book calendar events. Existing configuration is
            read without exposing credentials.
          </span>
        </p>
        {data && (
          <p>
            Checked{' '}
            {Number.isFinite(Date.parse(data.checked_at))
              ? new Date(data.checked_at).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })
              : 'time unavailable'}
          </p>
        )}
      </footer>
    </div>
  );
}
