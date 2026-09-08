'use client';

import Link from 'next/link';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  CalendarDays,
  Check,
  ChevronRight,
  CircleHelp,
  FlaskConical,
  Hand,
  Link2,
  Loader2,
  MessageCircle,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  belongsToDecision,
  dateBoundary,
  eventText,
  initials,
  nextStep,
  safeLink,
  SCOPE_LABELS,
  statusLabel,
  type Pursuit,
  type WorkspaceData,
} from './model';

type Fields = Record<string, string>;
type Modal =
  | 'setup'
  | 'start'
  | 'consent'
  | 'takeover'
  | 'resume'
  | 'schedule'
  | 'sync'
  | null;
interface Slot {
  start: string;
  end: string;
  local?: Record<string, { start: string; end: string; timezone: string }>;
}
interface CalendarResult {
  status: string;
  slots: Slot[];
  unverified_participants?: string[];
  fallback?: { url: string } | null;
}
const selectClass =
  'h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50';

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="grid gap-2 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {hint && (
        <span className="text-muted-foreground text-xs leading-relaxed">
          {hint}
        </span>
      )}
    </label>
  );
}
function ErrorBanner({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="border-destructive/20 bg-destructive/5 text-destructive flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 text-sm"
    >
      <span className="min-w-0 break-words">{message}</span>
      {retry && (
        <Button variant="outline" onClick={retry}>
          Try again
        </Button>
      )}
    </div>
  );
}
function timeLabel(value: string, timezone?: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.valueOf())) return 'Time unavailable';
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: timezone,
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
    }).format(date);
  } catch {
    return 'Timezone unavailable';
  }
}

export function ConciergeWorkspace() {
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [warning, setWarning] = useState('');
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState('');
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState<Modal>(null);
  const [fields, setFields] = useState<Fields>({});
  const [formError, setFormError] = useState('');
  const [draft, setDraft] = useState('');
  const [simulationReply, setSimulationReply] = useState('');
  const [calendar, setCalendar] = useState<CalendarResult | null>(null);
  const [chosenSlot, setChosenSlot] = useState<number | null>(null);
  const lock = useRef(false);
  const readVersion = useRef(0);
  const load = useCallback(async (signal?: AbortSignal) => {
    const version = ++readVersion.current;
    try {
      const response = await fetch('/api/concierge', {
        cache: 'no-store',
        signal,
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          typeof body.error === 'string'
            ? body.error
            : 'The concierge workspace could not be loaded.'
        );
      if (
        !body ||
        !Array.isArray(body.contacts) ||
        !['simulation', 'live'].includes(body.mode)
      )
        throw new Error(
          'The workspace returned an incomplete response. Please try again.'
        );
      if (version === readVersion.current) {
        setData(body);
        setError(body.error ?? '');
      }
    } catch (e) {
      if (
        !(e instanceof DOMException && e.name === 'AbortError') &&
        version === readVersion.current
      )
        setError(
          e instanceof Error ? e.message : 'Could not connect to the workspace.'
        );
    } finally {
      if (version === readVersion.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  const pursuits = useMemo(() => data?.report?.pursuits ?? [], [data]);
  const selected =
    pursuits.find((p) => p.pursuit_id === selectedId) ?? pursuits[0];
  const contactId = selected?.pursuit_id.startsWith('wacrm:')
    ? selected.pursuit_id.slice(6)
    : '';
  const workspace = data?.workspace;
  const configured = Boolean(workspace?.principal_name && workspace?.offer);
  const simulated = data?.mode === 'simulation';
  const blocked = selected
    ? [
        'human_owned',
        'declined',
        'opted_out',
        'reconcile',
        'attended',
      ].includes(selected.status)
    : false;
  const filtered = useMemo(
    () =>
      pursuits.filter((p) =>
        `${p.identity.name} ${p.identity.fit}`
          .toLowerCase()
          .includes(search.toLowerCase())
      ),
    [pursuits, search]
  );
  const timeline = (data?.report?.timeline ?? []).filter(
    (event) => event.pursuit_id === selected?.pursuit_id
  );
  const pending = (data?.report?.pending_decisions ?? []).filter(
    (decision) => selected && belongsToDecision(decision, selected.pursuit_id)
  );
  const messages = (data?.report?.direct_messages ?? []).filter(
    (message) => message.contact_id === contactId
  );
  const request = async (
    action: string,
    payload: Record<string, unknown> = {}
  ) => {
    if (lock.current) return null;
    lock.current = true;
    setBusy(true);
    setFormError('');
    setError('');
    try {
      const bound = !['setup', 'start'].includes(action);
      const response = await fetch('/api/concierge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          ...(bound && contactId ? { contact_id: contactId } : {}),
          ...(bound && selected ? { revision: selected.revision } : {}),
          ...payload,
        }),
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          typeof body.error === 'string'
            ? body.error
            : typeof body.detail === 'string'
              ? body.detail
              : 'This action could not be completed. Please refresh and try again.'
        );
      await load();
      const crmWarning = body.crm_warning ?? body.result?.crm_warning;
      setWarning(typeof crmWarning === 'string' ? crmWarning : '');
      return body;
    } catch (e) {
      const message =
        e instanceof Error ? e.message : 'The action could not be completed.';
      setFormError(message);
      if (!modal) setError(message);
      return null;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const open = (kind: Modal) => {
    setModal(kind);
    setFormError('');
    setCalendar(null);
    setChosenSlot(null);
    const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
    const later = new Date(Date.now() + 14 * 86400000)
      .toISOString()
      .slice(0, 10);
    setFields({
      principal_name: workspace?.principal_name ?? '',
      principal_phone: workspace?.principal_phone ?? '',
      offer: workspace?.offer ?? '',
      timezone:
        workspace?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
      booking_link: workspace?.booking_link ?? '',
      party: 'recipient',
      scope: 'introduction',
      contact_id: '',
      start: tomorrow,
      end: later,
      hours_start: '09:00',
      hours_end: '17:00',
      duration: '30',
      recipient_timezone: '',
      chat_id: selected?.latest_inbound?.chat_id ?? '',
    });
  };
  const change = (key: string, value: string) => {
    setFields((previous) => ({ ...previous, [key]: value }));
    if (modal === 'schedule') {
      setCalendar(null);
      setChosenSlot(null);
    }
  };
  const submitModal = async () => {
    if (!modal) return;
    const required =
      modal === 'setup'
        ? ['principal_name', 'principal_phone', 'offer', 'timezone']
        : modal === 'start'
          ? ['contact_id', 'fit', 'source_ref']
          : modal === 'consent'
            ? ['source_ref']
            : modal === 'sync'
              ? ['chat_id']
              : modal === 'schedule'
                ? ['start', 'end', 'recipient_timezone']
                : ['reason'];
    if (required.some((key) => !fields[key]?.trim())) {
      setFormError('Complete the required fields to continue.');
      return;
    }
    if (fields.booking_link && !safeLink(fields.booking_link)) {
      setFormError('Use a full HTTPS booking link.');
      return;
    }
    if (modal === 'setup') {
      try {
        new Intl.DateTimeFormat(undefined, { timeZone: fields.timezone });
      } catch {
        setFormError('Use a valid timezone, such as Africa/Johannesburg.');
        return;
      }
      const offer = [
        fields.offer.trim(),
        fields.counterpart?.trim()
          ? `Ideal counterpart: ${fields.counterpart.trim()}`
          : '',
      ]
        .filter(Boolean)
        .join('\n\n');
      const result = await request('setup', {
        principal_name: fields.principal_name.trim(),
        principal_phone: fields.principal_phone.trim(),
        offer,
        timezone: fields.timezone,
        ...(fields.booking_link?.trim()
          ? { booking_link: fields.booking_link.trim() }
          : {}),
      });
      if (result) {
        setModal(null);
        toast.success('Chris has your brief. Choose your first opportunity.');
      }
    } else if (modal === 'start') {
      const result = await request('start', {
        contact_id: fields.contact_id,
        fit: fields.fit.trim(),
        source_ref: fields.source_ref.trim(),
      });
      if (result) {
        setSelectedId(`wacrm:${fields.contact_id}`);
        setDraft(
          typeof result.result?.draft === 'string' ? result.result.draft : ''
        );
        setModal(null);
        toast.success('Opportunity added. Review the proposed approach.');
      }
    } else if (modal === 'consent') {
      if (
        await request('consent', {
          scope: fields.scope,
          party: fields.party,
          source_ref: fields.source_ref.trim(),
        })
      ) {
        setModal(null);
        toast.success('Permission recorded.');
      }
    } else if (modal === 'sync') {
      if (await request('sync', { chat_id: fields.chat_id.trim() })) {
        setModal(null);
        toast.success('Conversation refreshed.');
      }
    } else if (modal === 'schedule') {
      if (calendar && chosenSlot !== null) {
        const slot = calendar.slots[chosenSlot];
        if (
          await request('book', {
            slot: { start: slot.start, end: slot.end },
            summary: `${selected?.identity.principal_name} + ${selected?.identity.name}`,
            timezone: fields.recipient_timezone,
            windows: [0, 1, 2, 3, 4].map((weekday) => ({
              weekday,
              start: fields.hours_start,
              end: fields.hours_end,
            })),
          })
        ) {
          setModal(null);
          toast.success('Meeting prepared for review.');
        }
      } else {
        try {
          new Intl.DateTimeFormat(undefined, {
            timeZone: fields.recipient_timezone,
          });
        } catch {
          setFormError('Use a valid recipient timezone.');
          return;
        }
        if (
          fields.end < fields.start ||
          fields.hours_end <= fields.hours_start
        ) {
          setFormError('Choose increasing dates and working hours.');
          return;
        }
        let searchStart: string, searchEnd: string;
        try {
          searchStart = dateBoundary(
            fields.start,
            workspace?.timezone ?? 'UTC'
          );
          searchEnd = dateBoundary(
            fields.end,
            workspace?.timezone ?? 'UTC',
            true
          );
        } catch (e) {
          setFormError(e instanceof Error ? e.message : 'Choose valid dates.');
          return;
        }
        const result = await request('propose', {
          start: searchStart,
          end: searchEnd,
          timezone: fields.recipient_timezone,
          windows: [0, 1, 2, 3, 4].map((weekday) => ({
            weekday,
            start: fields.hours_start,
            end: fields.hours_end,
          })),
          duration_minutes: Number(fields.duration),
        });
        const proposal = result?.result;
        if (proposal && Array.isArray(proposal.slots)) setCalendar(proposal);
        else if (result)
          setFormError(
            'No readable calendar result was returned. Please try again.'
          );
      }
    } else if (
      await request(modal, {
        text: fields.reason.trim(),
      })
    ) {
      setModal(null);
      toast.success(
        modal === 'takeover'
          ? 'Chris is paused. You’re handling this.'
          : 'Handed back to Chris.'
      );
    }
  };
  const choose = (p: Pursuit) => {
    setSelectedId(p.pursuit_id);
    setDraft('');
    setSimulationReply('');
    setFormError('');
  };
  const generateDraft = () => {
    if (!selected) return;
    const i = selected.identity;
    setDraft(
      selected.reply_required
        ? selected.introduction_agreed && selected.group_agreed
          ? 'Thanks, I’ll make the introduction.'
          : ''
        : `Hi ${i.name}, I’m Chris, ${i.principal_name}’s AI assistant. ${i.fit}\n\nWould you be open to an introduction?`
    );
  };

  const draftWithAI = async () => {
    if (!selected || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      const response = await fetch('/api/concierge/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_id: contactId,
          fit: selected.identity.fit,
          purpose: selected.reply_required ? 'reply' : 'approach',
          ...(draft.trim() ? { text: draft.trim() } : {}),
        }),
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          typeof body.error === 'string'
            ? body.error
            : 'AI drafting is unavailable. Your editable draft is still here.'
        );
      if (
        typeof body.draft !== 'string' ||
        !body.draft.trim() ||
        body.source !== 'ai'
      )
        throw new Error('No readable AI draft was returned.');
      setDraft(body.draft);
      toast.success('AI draft ready for your review.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'AI drafting is unavailable.');
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="gap-1.5">
              <Sparkles className="size-3" /> Concierge
            </Badge>
            {data && (
              <Badge
                variant="outline"
                className={
                  simulated
                    ? 'gap-1.5 border-amber-500/30 text-amber-700 dark:text-amber-300'
                    : 'gap-1.5'
                }
              >
                {simulated ? (
                  <FlaskConical className="size-3" />
                ) : (
                  <ShieldCheck className="size-3" />
                )}
                {simulated ? 'Simulation workspace' : 'Live workspace'}
              </Badge>
            )}
          </div>
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            The right people. A reason to connect.
          </h2>
          <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-6">
            Chris starts the conversation, earns the introduction, and carries
            the next step through.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={() => void load()}
            aria-label="Refresh workspace"
            disabled={busy}
          >
            <RefreshCw className={loading ? 'animate-spin' : ''} />
          </Button>
          <Button variant="outline" onClick={() => open('setup')} disabled={!data || busy}>
            <Settings2 />
            {!data ? 'Loading brief' : configured ? 'Your brief' : 'Set up Chris'}
          </Button>
          <Button
            onClick={() => open(configured ? 'start' : 'setup')}
            disabled={!data || busy}
          >
            <Plus />
            New opportunity
          </Button>
        </div>
      </header>
      {error && <ErrorBanner message={error} retry={() => void load()} />}
      {warning && (
        <div
          role="status"
          className="rounded-xl border border-amber-500/25 bg-amber-500/5 px-4 py-3 text-sm leading-6"
        >
          <strong>
            The action completed, but the CRM copy needs attention.
          </strong>
          <p className="text-muted-foreground">{warning}</p>
        </div>
      )}
      {simulated && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm">
          <FlaskConical className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <p className="text-muted-foreground leading-6">
            <span className="text-foreground font-medium">
              Try the complete experience.
            </span>{' '}
            Messages and meetings stay in this simulation. Use the recipient
            panel to play through replies; no WhatsApp messages or calendar
            invitations are sent.
          </p>
        </div>
      )}
      {loading && !data ? (
        <div
          className="grid gap-4 md:grid-cols-3"
          role="status"
          aria-label="Loading concierge"
        >
          <div className="bg-muted h-72 animate-pulse rounded-2xl" />
          <div className="bg-muted h-72 animate-pulse rounded-2xl md:col-span-2" />
        </div>
      ) : data && !configured ? (
        <section className="bg-card grid overflow-hidden rounded-2xl border lg:grid-cols-[1.15fr_1fr]">
          <div className="p-7 sm:p-10">
            <div className="bg-primary/10 text-primary mb-6 flex size-12 items-center justify-center rounded-2xl">
              <Bot className="size-6" />
            </div>
            <h3 className="max-w-md text-2xl font-semibold tracking-tight">
              Meet the assistant who makes the introduction.
            </h3>
            <p className="text-muted-foreground mt-4 max-w-lg text-sm leading-7">
              Start with your offer and a person in your CRM. Chris explains the
              fit, asks for permission, and connects you when there’s mutual
              interest.
            </p>
            <Button className="mt-6" size="lg" onClick={() => open('setup')}>
              Give Chris your brief
              <ArrowRight />
            </Button>
          </div>
          <div className="bg-muted/30 grid content-center gap-7 border-t p-7 sm:p-10 lg:border-t-0 lg:border-l">
            {[
              [
                Users,
                'Start with a real person',
                'Choose from your contacts and explain why the connection matters.',
              ],
              [
                MessageCircle,
                'Make a thoughtful approach',
                'Review a concise introduction proposal, grounded in your offer.',
              ],
              [
                CalendarDays,
                'Carry it through',
                'Agree on the introduction, coordinate a time, and keep the context.',
              ],
            ].map(([Icon, title, description]) => {
              const StepIcon = Icon as typeof Users;
              return (
                <div className="flex gap-4" key={String(title)}>
                  <StepIcon className="text-primary mt-1 size-5 shrink-0" />
                  <div>
                    <h4 className="text-sm font-medium">{String(title)}</h4>
                    <p className="text-muted-foreground mt-1 text-sm leading-6">
                      {String(description)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : (
        data && (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[
                ['Opportunities', pursuits.length],
                [
                  'Introductions made',
                  pursuits.filter((p) => p.introduced).length,
                ],
                [
                  'Meetings booked',
                  pursuits.filter((p) =>
                    ['booked', 'attended'].includes(p.status)
                  ).length,
                ],
                [
                  'Need your attention',
                  pursuits.filter(
                    (p) => p.reply_required || p.status === 'reconcile'
                  ).length,
                ],
              ].map(([label, count]) => (
                <div
                  key={String(label)}
                  className="bg-card rounded-xl border px-5 py-4"
                >
                  <p className="text-muted-foreground text-xs">{label}</p>
                  <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">
                    {count}
                  </p>
                </div>
              ))}
            </div>
            <div className="grid items-start gap-5 xl:grid-cols-[270px_minmax(0,1fr)_290px]">
              <aside className="bg-card overflow-hidden rounded-xl border">
                <div className="border-b p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="text-sm font-semibold">Opportunities</h3>
                    <span className="text-muted-foreground text-xs">
                      {pursuits.length}
                    </span>
                  </div>
                  <div className="relative">
                    <Search className="text-muted-foreground pointer-events-none absolute top-2.5 left-3 size-4" />
                    <Input
                      className="pl-9"
                      placeholder="Find a person…"
                      aria-label="Find an opportunity"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                </div>
                <div className="max-h-[480px] overflow-y-auto xl:max-h-[650px]">
                  {filtered.length ? (
                    filtered.map((p) => (
                      <button
                        key={p.pursuit_id}
                        onClick={() => choose(p)}
                        disabled={busy}
                        className={`hover:bg-muted/60 flex w-full items-start gap-3 border-b px-4 py-4 text-left transition-colors last:border-0 ${selected?.pursuit_id === p.pursuit_id ? 'bg-primary/5' : ''}`}
                        aria-pressed={selected?.pursuit_id === p.pursuit_id}
                      >
                        <span className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-full text-xs font-medium">
                          {initials(p.identity.name)}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">
                            {p.identity.name}
                          </span>
                          <span className="text-muted-foreground mt-1 block text-xs">
                            {statusLabel(p.status)}
                          </span>
                        </span>
                        <ChevronRight className="text-muted-foreground mt-2 size-3.5 shrink-0" />
                      </button>
                    ))
                  ) : (
                    <div className="text-muted-foreground px-5 py-8 text-center text-sm">
                      {search
                        ? 'No matching opportunities.'
                        : 'Your first connection starts here.'}
                    </div>
                  )}
                </div>
                <div className="border-t p-3">
                  <Link
                    href="/contacts"
                    className="text-muted-foreground hover:bg-muted flex items-center justify-between rounded-md px-2 py-2 text-xs"
                  >
                    Browse CRM contacts <ArrowUpRight className="size-3.5" />
                  </Link>
                </div>
              </aside>
              <main className="min-w-0">
                {selected ? (
                  <section className="bg-card overflow-hidden rounded-xl border">
                    <div className="border-b p-5 sm:p-6">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h3 className="text-xl font-semibold tracking-tight">
                            {selected.identity.name}
                          </h3>
                          <p className="text-muted-foreground mt-1 text-sm">
                            An introduction to{' '}
                            {selected.identity.principal_name}
                          </p>
                        </div>
                        <Badge variant="secondary">
                          {statusLabel(selected.status)}
                        </Badge>
                      </div>
                      <p className="mt-4 text-sm leading-7">
                        {selected.identity.fit}
                      </p>
                      <div className="bg-muted/50 mt-5 flex items-start gap-2.5 rounded-lg p-3 text-xs leading-6">
                        <Sparkles className="text-primary mt-1 size-3.5 shrink-0" />
                        <p>{nextStep(selected)}</p>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={busy}
                          onClick={() =>
                            simulated ? void request('sync') : open('sync')
                          }
                        >
                          <RefreshCw />
                          Refresh conversation
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={
                            busy ||
                            ['opted_out', 'declined'].includes(selected.status)
                          }
                          onClick={() =>
                            open(
                              selected.status === 'human_owned'
                                ? 'resume'
                                : 'takeover'
                            )
                          }
                        >
                          <Hand />
                          {selected.status === 'human_owned'
                            ? 'Hand back to Chris'
                            : 'Take over'}
                        </Button>
                        <Link
                          href="/inbox"
                          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 px-2 text-xs"
                        >
                          Open inbox
                          <ArrowUpRight className="size-3" />
                        </Link>
                      </div>
                    </div>
                    <div className="space-y-5 p-5 sm:p-6">
                      <div className="flex items-center justify-between">
                        <h4 className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                          Conversation & activity
                        </h4>
                        <span className="text-muted-foreground text-xs">
                          {timeline.length}{' '}
                          {timeline.length === 1 ? 'event' : 'events'}
                        </span>
                      </div>
                      {messages.length > 0 && (
                        <div className="grid gap-3 border-b pb-5">
                          {messages.map((message) => (
                            <div
                              key={message.id}
                              className={`max-w-[92%] rounded-xl px-4 py-3 ${message.direction === 'outbound' ? 'bg-primary/10 justify-self-end' : 'bg-muted justify-self-start'}`}
                            >
                              <p className="text-muted-foreground mb-1 text-[11px] font-medium">
                                {message.direction === 'outbound'
                                  ? 'Chris'
                                  : selected.identity.name}
                                {message.group ? ' · Introduction group' : ''}
                              </p>
                              <p className="text-sm leading-7 break-words whitespace-pre-wrap">
                                {message.text}
                              </p>
                              <p className="text-muted-foreground mt-2 text-[10px]">
                                {timeLabel(message.occurred_at)}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                      {timeline.length ? (
                        <ol className="space-y-5">
                          {timeline.map((event, index) => (
                            <li
                              key={event.event_id ?? index}
                              className="flex gap-3"
                            >
                              <span
                                className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full ${event.kind === 'inbound' ? 'bg-muted' : 'bg-primary/10 text-primary'}`}
                              >
                                {event.kind === 'inbound' ? (
                                  <MessageCircle className="size-3.5" />
                                ) : (
                                  <Check className="size-3.5" />
                                )}
                              </span>
                              <div className="min-w-0 flex-1">
                                <p className="text-sm leading-6 break-words whitespace-pre-wrap">
                                  {eventText(event)}
                                </p>
                                <p className="text-muted-foreground mt-1 text-[11px]">
                                  {event.occurred_at || event.ts
                                    ? timeLabel(
                                        event.occurred_at ?? event.ts ?? ''
                                      )
                                    : 'Recorded in this workspace'}
                                </p>
                              </div>
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p className="text-muted-foreground py-6 text-sm">
                          The conversation will appear here as this opportunity
                          moves forward.
                        </p>
                      )}
                      {pending.map((decision) => (
                        <div
                          key={decision.id}
                          className="border-primary/20 bg-primary/5 rounded-xl border p-4"
                        >
                          <div className="text-primary mb-3 flex items-center gap-2 text-xs font-medium">
                            <ShieldCheck className="size-4" />
                            {decision.stale
                              ? 'Draft needs updating'
                              : 'Ready for your review'}
                          </div>
                          <p className="text-sm leading-7 break-words whitespace-pre-wrap">
                            {decision.action?.frozen?.text ??
                              decision.payload ??
                              decision.ask ??
                              'Review the proposed next step.'}
                          </p>
                          {decision.action?.request?.proposal && (
                            <p className="mt-2 text-sm leading-6">
                              {decision.action.request.proposal.summary}
                              <br />
                              {timeLabel(
                                decision.action.request.proposal.start ?? '',
                                workspace?.timezone
                              )}
                              <br />
                              Until{' '}
                              {timeLabel(
                                decision.action.request.proposal.end ?? '',
                                workspace?.timezone
                              )}
                            </p>
                          )}
                          {decision.stale && (
                            <p className="text-muted-foreground mt-3 text-sm leading-6">
                              New conversation activity: prepare an updated
                              draft.
                            </p>
                          )}
                          <div className="mt-4 flex flex-wrap gap-2">
                            {simulated ? (
                              <Button
                                disabled={busy || decision.stale === true}
                                onClick={async () => {
                                  if (
                                    await request('approve', {
                                      decision_id: decision.id,
                                    })
                                  )
                                    toast.success(
                                      'Approved in simulation. No external message was sent.'
                                    );
                                }}
                              >
                                <Check />
                                Approve in simulation
                              </Button>
                            ) : (
                              <p className="text-muted-foreground mt-3 text-xs">
                                Review this action through your connected
                                approval workflow.
                              </p>
                            )}
                            <Button
                              variant="outline"
                              disabled={busy}
                              onClick={async () => {
                                if (
                                  await request('decline', {
                                    decision_id: decision.id,
                                    pursuit_id: selected.pursuit_id,
                                  })
                                )
                                  toast.success('Draft discarded.');
                              }}
                            >
                              Discard draft
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                    {!blocked &&
                      (!selected.introduced || selected.reply_required) && (
                        <div className="bg-muted/20 border-t p-5 sm:p-6">
                          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                            <h4 className="text-sm font-medium">
                              {selected.reply_required
                                ? 'Your reply'
                                : 'A thoughtful first approach'}
                            </h4>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={generateDraft}
                              disabled={busy}
                            >
                              <Sparkles />
                              Prepare wording
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={busy}
                              onClick={() => void draftWithAI()}
                            >
                              <Bot />
                              Draft with AI
                            </Button>
                          </div>
                          <Textarea
                            aria-label="Message draft"
                            rows={5}
                            value={draft}
                            disabled={busy}
                            placeholder={
                              selected.reply_required
                                ? 'Acknowledge their message and agree on the next step…'
                                : 'Prepare a personal message explaining why this connection makes sense…'
                            }
                            onChange={(e) => setDraft(e.target.value)}
                          />
                          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                            <p className="text-muted-foreground text-xs">
                              Prepared for review. You approve the next step.
                            </p>
                            <Button
                              disabled={busy || !draft.trim()}
                              onClick={async () => {
                                if (
                                  await request('draft', { text: draft.trim() })
                                ) {
                                  setDraft('');
                                  toast.success(
                                    'Message prepared for approval.'
                                  );
                                }
                              }}
                            >
                              Prepare for approval
                              <ArrowRight />
                            </Button>
                          </div>
                        </div>
                      )}
                  </section>
                ) : (
                  <div className="bg-card flex min-h-[420px] flex-col items-center justify-center rounded-xl border border-dashed px-8 py-12 text-center">
                    <div className="bg-primary/10 text-primary mb-5 rounded-2xl p-4">
                      <Link2 className="size-7" />
                    </div>
                    <h3 className="text-lg font-semibold">
                      One worthwhile introduction.
                    </h3>
                    <p className="text-muted-foreground mt-3 max-w-sm text-sm leading-7">
                      Choose someone from your CRM, explain the fit, and let
                      Chris help you start the conversation.
                    </p>
                    <Button className="mt-6" onClick={() => open('start')}>
                      <Plus />
                      Add your first opportunity
                    </Button>
                  </div>
                )}
              </main>
              <aside className="space-y-5">
                {selected && (
                  <>
                    <section className="bg-card rounded-xl border p-5">
                      <h3 className="text-sm font-semibold">The connection</h3>
                      <p className="text-muted-foreground mt-4 text-xs font-medium">
                        REPRESENTING
                      </p>
                      <p className="mt-1 text-sm">
                        {selected.identity.principal_name}
                      </p>
                      <p className="text-muted-foreground mt-4 text-xs font-medium">
                        LOOKING FOR
                      </p>
                      <p className="mt-1 text-sm leading-7">
                        {selected.identity.offer}
                      </p>
                      {safeLink(selected.identity.profile_url) && (
                        <a
                          href={safeLink(selected.identity.profile_url)!}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary mt-4 flex items-center gap-1 text-xs"
                        >
                          View contact profile
                          <ArrowUpRight className="size-3" />
                        </a>
                      )}
                      <Link
                        href="/pipelines"
                        className="text-muted-foreground hover:text-foreground mt-4 flex items-center gap-1 text-xs"
                      >
                        View pipelines
                        <ArrowUpRight className="size-3" />
                      </Link>
                    </section>
                    <section className="bg-card rounded-xl border p-5">
                      <div className="flex items-center justify-between">
                        <h3 className="text-sm font-semibold">
                          Permission, step by step
                        </h3>
                        <ShieldCheck className="text-muted-foreground size-4" />
                      </div>
                      <p className="text-muted-foreground mt-2 text-xs leading-6">
                        Record what each person has actually agreed to.
                      </p>
                      <div className="mt-4 space-y-3">
                        {Object.entries(SCOPE_LABELS).map(([scope, label]) => {
                          const consented = (party: string) =>
                            selected.consents?.some(
                              ([id, s]) => id === party && s === scope
                            );
                          return (
                            <div
                              className="flex items-center justify-between gap-2"
                              key={scope}
                            >
                              <span className="text-xs">{label}</span>
                              <span className="flex gap-1.5">
                                {[
                                  [
                                    selected.identity.principal_id,
                                    selected.identity.principal_name,
                                  ],
                                  [
                                    selected.identity.recipient_id,
                                    selected.identity.name,
                                  ],
                                ].map(([id, name]) => (
                                  <span
                                    key={id}
                                    title={`${name}: ${consented(id) ? 'agreed' : 'not recorded'}`}
                                    aria-label={`${name}: ${label} ${consented(id) ? 'agreed' : 'not recorded'}`}
                                    className={`flex size-5 items-center justify-center rounded-full text-[9px] ${consented(id) ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'}`}
                                  >
                                    {consented(id) ? (
                                      <Check className="size-3" />
                                    ) : (
                                      initials(name).slice(0, 1)
                                    )}
                                  </span>
                                ))}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                      <Button
                        variant="outline"
                        className="mt-5 w-full"
                        disabled={busy}
                        onClick={() => open('consent')}
                      >
                        Record permission
                      </Button>
                      <div className="mt-3 grid gap-2">
                        <Button
                          variant="secondary"
                          disabled={
                            busy ||
                            blocked ||
                            !selected.introduction_agreed ||
                            !selected.group_agreed ||
                            selected.reply_required ||
                            selected.introduced
                          }
                          onClick={async () => {
                            if (await request('introduce'))
                              toast.success(
                                'Introduction prepared for review.'
                              );
                          }}
                        >
                          <Link2 />
                          Make the introduction
                        </Button>
                        <Button
                          variant="outline"
                          disabled={
                            busy || blocked || !selected.scheduling_agreed
                          }
                          onClick={() => open('schedule')}
                        >
                          <CalendarDays />
                          Find a time
                        </Button>
                      </div>
                    </section>
                  </>
                )}
                {simulated && selected && (
                  <section className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-5">
                    <div className="flex items-center gap-2">
                      <FlaskConical className="size-4 text-amber-600 dark:text-amber-400" />
                      <h3 className="text-sm font-semibold">
                        Play the recipient
                      </h3>
                    </div>
                    <p className="text-muted-foreground mt-2 text-xs leading-6">
                      Type a reply as {selected.identity.name} to test the
                      conversation. Permission is recorded separately.
                    </p>
                    <Textarea
                      className="bg-background mt-4"
                      rows={3}
                      aria-label="Simulated recipient reply"
                      placeholder="What does the partnership involve?"
                      value={simulationReply}
                      onChange={(e) => setSimulationReply(e.target.value)}
                    />
                    <Button
                      variant="outline"
                      className="mt-3 w-full"
                      disabled={busy || !simulationReply.trim()}
                      onClick={async () => {
                        if (
                          await request('simulate_reply', {
                            text: simulationReply.trim(),
                          })
                        ) {
                          setSimulationReply('');
                          toast.success('Simulated reply added.');
                        }
                      }}
                    >
                      <MessageCircle />
                      Add simulated reply
                    </Button>
                  </section>
                )}
                <div className="text-muted-foreground flex gap-2 px-1 text-xs leading-6">
                  <CircleHelp className="mt-1 size-3.5 shrink-0" />
                  <p>
                    Your contacts, inbox and pipelines remain the home for
                    customer relationships.
                  </p>
                </div>
              </aside>
            </div>
          </>
        )
      )}
      <Dialog
        open={modal !== null}
        onOpenChange={(value) => {
          if (!value && !busy) setModal(null);
        }}
      >
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {modal === 'sync'
                ? 'Refresh the WhatsApp conversation'
                : modal === 'setup'
                  ? configured
                    ? 'Your brief for Chris'
                    : 'Give Chris your brief'
                  : modal === 'start'
                    ? 'Start with a real connection'
                    : modal === 'consent'
                      ? 'Record permission'
                      : modal === 'schedule'
                        ? 'Find a time to connect'
                        : modal === 'takeover'
                          ? 'Take over the conversation'
                          : 'Hand back to Chris'}
            </DialogTitle>
            <DialogDescription>
              {modal === 'setup'
                ? 'A clear offer helps Chris represent you accurately.'
                : modal === 'start'
                  ? 'Use a contact from your CRM and a specific, source-backed reason to talk.'
                  : modal === 'consent'
                    ? 'Record agreement already given. Each step and each person is separate.'
                    : modal === 'schedule'
                      ? 'Propose times within working hours, then prepare the agreed meeting.'
                      : 'Leave a clear note so the next step stays with the right person.'}
            </DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void submitModal();
            }}
          >
            {modal === 'setup' && (
              <fieldset className="grid gap-4" disabled={configured || busy}>
                <Field label="Your name">
                  <Input
                    value={fields.principal_name ?? ''}
                    onChange={(e) => change('principal_name', e.target.value)}
                    placeholder="Patrick Nesbitt"
                  />
                </Field>
                <Field
                  label="Your WhatsApp number"
                  hint="Include the country code. This is the person Chris introduces, not the assistant’s number."
                >
                  <Input
                    type="tel"
                    value={fields.principal_phone ?? ''}
                    onChange={(e) => change('principal_phone', e.target.value)}
                    placeholder="+27…"
                  />
                </Field>
                <Field label="What do you offer?">
                  <Textarea
                    rows={3}
                    value={fields.offer ?? ''}
                    onChange={(e) => change('offer', e.target.value)}
                    placeholder="Who you help, the problem you solve, and the outcome you deliver."
                  />
                </Field>
                {!configured && (
                  <Field
                    label="Who would make a good counterpart?"
                    hint="Optional. Describe the people or partners you want to meet."
                  >
                    <Textarea
                      rows={2}
                      value={fields.counterpart ?? ''}
                      onChange={(e) => change('counterpart', e.target.value)}
                    />
                  </Field>
                )}
                <Field label="Your timezone">
                  <Input
                    value={fields.timezone ?? ''}
                    onChange={(e) => change('timezone', e.target.value)}
                    placeholder="Africa/Johannesburg"
                  />
                </Field>
                <Field
                  label="Preferred booking link"
                  hint="Optional. Chris can offer this when coordinating a meeting."
                >
                  <Input
                    type="url"
                    value={fields.booking_link ?? ''}
                    onChange={(e) => change('booking_link', e.target.value)}
                    placeholder="https://…"
                  />
                </Field>
              </fieldset>
            )}
            {modal === 'start' && (
              <>
                <Field label="Who would you like to meet?">
                  <select
                    className={selectClass}
                    value={fields.contact_id ?? ''}
                    onChange={(e) => change('contact_id', e.target.value)}
                  >
                    <option value="">Choose a CRM contact</option>
                    {data?.contacts
                      .filter(
                        (c) =>
                          !pursuits.some(
                            (p) => p.pursuit_id === `wacrm:${c.id}`
                          )
                      )
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name || c.phone}
                          {c.company ? ` · ${c.company}` : ''}
                        </option>
                      ))}
                  </select>
                </Field>
                <Link href="/contacts" className="text-primary text-xs">
                  Add or import contacts in your CRM ↗
                </Link>
                <Field label="Why is this connection worth making?">
                  <Textarea
                    rows={4}
                    value={fields.fit ?? ''}
                    onChange={(e) => change('fit', e.target.value)}
                    placeholder="Explain what they need and how your work fits. Be specific."
                  />
                </Field>
                <Field
                  label="Where did you learn this?"
                  hint="A profile, website, conversation reference or another source you can verify."
                >
                  <Input
                    value={fields.source_ref ?? ''}
                    onChange={(e) => change('source_ref', e.target.value)}
                    placeholder="Source link or reference"
                  />
                </Field>
              </>
            )}
            {modal === 'consent' && (
              <>
                <Field label="Who agreed?">
                  <select
                    className={selectClass}
                    value={fields.party}
                    onChange={(e) => change('party', e.target.value)}
                  >
                    <option value="recipient">{selected?.identity.name}</option>
                    <option value="principal">
                      {selected?.identity.principal_name}
                    </option>
                  </select>
                </Field>
                <Field label="What did they agree to?">
                  <select
                    className={selectClass}
                    value={fields.scope}
                    onChange={(e) => change('scope', e.target.value)}
                  >
                    {Object.entries(SCOPE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Evidence of their agreement">
                  <Textarea
                    rows={3}
                    value={fields.source_ref ?? ''}
                    onChange={(e) => change('source_ref', e.target.value)}
                    placeholder="Reference the message or conversation where they agreed."
                  />
                </Field>
              </>
            )}
            {modal === 'sync' && (
              <Field
                label="WhatsApp conversation reference"
                hint="Use the conversation linked to this contact. Chris reads its latest messages before acting."
              >
                <Input
                  value={fields.chat_id ?? ''}
                  onChange={(e) => change('chat_id', e.target.value)}
                  placeholder="Conversation ID"
                />
              </Field>
            )}
            {(modal === 'takeover' || modal === 'resume') && (
              <Field
                label={
                  modal === 'takeover'
                    ? 'A note for Chris'
                    : 'What should happen next?'
                }
              >
                <Textarea
                  rows={4}
                  value={fields.reason ?? ''}
                  onChange={(e) => change('reason', e.target.value)}
                />
              </Field>
            )}
            {modal === 'schedule' && (
              <>
                <p className="text-muted-foreground text-xs leading-6">
                  Search dates use {selected?.identity.principal_name}’s
                  timezone: {workspace?.timezone ?? 'UTC'}.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="From">
                    <Input
                      type="date"
                      value={fields.start}
                      onChange={(e) => change('start', e.target.value)}
                    />
                  </Field>
                  <Field label="Through">
                    <Input
                      type="date"
                      value={fields.end}
                      onChange={(e) => change('end', e.target.value)}
                    />
                  </Field>
                </div>
                <Field label={`${selected?.identity.name}’s timezone`}>
                  <Input
                    value={fields.recipient_timezone}
                    onChange={(e) =>
                      change('recipient_timezone', e.target.value)
                    }
                    placeholder="e.g. America/Los_Angeles"
                  />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Available from">
                    <Input
                      type="time"
                      value={fields.hours_start}
                      onChange={(e) => change('hours_start', e.target.value)}
                    />
                  </Field>
                  <Field label="Available until">
                    <Input
                      type="time"
                      value={fields.hours_end}
                      onChange={(e) => change('hours_end', e.target.value)}
                    />
                  </Field>
                </div>
                <p className="text-muted-foreground text-xs">
                  Monday to Friday, in their timezone. Your preferences come
                  from your workspace brief.
                </p>
                <Field label="Meeting length">
                  <select
                    className={selectClass}
                    value={fields.duration}
                    onChange={(e) => change('duration', e.target.value)}
                  >
                    {[15, 30, 45, 60].map((m) => (
                      <option key={m} value={m}>
                        {m} minutes
                      </option>
                    ))}
                  </select>
                </Field>
                {calendar && (
                  <div
                    className="grid gap-3 rounded-xl border p-4"
                    aria-live="polite"
                  >
                    <h4 className="font-medium">
                      {calendar.status === 'needs_exception'
                        ? 'No shared time in these hours'
                        : calendar.status === 'tentative'
                          ? 'Possible times to confirm'
                          : 'Proposed times'}
                    </h4>
                    {Boolean(calendar.unverified_participants?.length) && (
                      <p className="text-muted-foreground text-xs leading-6">
                        Some calendar availability has not been verified.
                        Confirm the selected time with both people.
                      </p>
                    )}
                    {calendar.slots.map((slot, index) => (
                      <label
                        key={slot.start}
                        className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${chosenSlot === index ? 'border-primary bg-primary/5' : ''}`}
                      >
                        <input
                          type="radio"
                          name="slot"
                          className="mt-1"
                          checked={chosenSlot === index}
                          onChange={() => setChosenSlot(index)}
                        />
                        <span className="grid gap-1 text-xs leading-6">
                          <span>
                            {selected?.identity.principal_name}:{' '}
                            {timeLabel(slot.start, workspace?.timezone)}
                          </span>
                          <span>
                            {selected?.identity.name}:{' '}
                            {timeLabel(slot.start, fields.recipient_timezone)}
                          </span>
                        </span>
                      </label>
                    ))}
                    {calendar.slots.length === 0 && (
                      <p className="text-muted-foreground text-xs leading-6">
                        Try another date range or ask whether an evening
                        exception would work.
                      </p>
                    )}
                    {chosenSlot !== null && !selected?.booking_agreed && (
                      <p className="text-muted-foreground text-xs leading-6">
                        Record both people’s agreement to this meeting before
                        preparing a booking. Close this dialog and use Record
                        permission.
                      </p>
                    )}
                    {safeLink(calendar.fallback?.url) && (
                      <a
                        href={safeLink(calendar.fallback?.url)!}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary text-xs"
                      >
                        Open preferred booking page ↗
                      </a>
                    )}
                  </div>
                )}
              </>
            )}
            {formError && <ErrorBanner message={formError} />}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => setModal(null)}
              >
                {configured && modal === 'setup' ? 'Close' : 'Cancel'}
              </Button>
              {!(configured && modal === 'setup') && (
                <Button
                  type="submit"
                  disabled={
                    busy ||
                    (modal === 'schedule' &&
                      chosenSlot !== null &&
                      !selected?.booking_agreed)
                  }
                >
                  {busy && <Loader2 className="animate-spin" />}
                  {modal === 'setup'
                    ? 'Create workspace brief'
                    : modal === 'start'
                      ? 'Prepare the approach'
                      : modal === 'schedule'
                        ? chosenSlot !== null
                          ? 'Prepare meeting for approval'
                          : 'Find times'
                        : 'Save'}
                </Button>
              )}
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
