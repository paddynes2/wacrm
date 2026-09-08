'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  Clock3,
  Inbox,
  ListChecks,
  Loader2,
  Pause,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

type Step = { hours: string; text: string };
type Contact = { id: string; name: string; phone: string; started?: boolean };
type Campaign = {
  id: string;
  name: string;
  steps: { delay_seconds: number; text: string }[];
  pace_seconds: number;
  daily_cap: number;
  paused: boolean;
};
type Job = {
  id: string;
  contact: string | { id?: string; name?: string; phone?: string };
  state: string;
  due: string | number;
  error?: string;
  payload?: { campaign_id?: string; step?: number; text?: string };
};
type Watch = {
  contact_id: string;
  chat_id: string;
  enabled: boolean;
  last_sync?: string;
  error?: string;
};
type Operations = {
  mode: string;
  draft_only: boolean;
  last_tick?: string;
  worker_error?: string;
  campaigns: Campaign[];
  jobs: Job[];
  enrollments: unknown[];
  suggestions: {
    contact_id: string;
    name: string;
    intent: string;
    suggestion: string;
    requires_review: boolean;
    revision: number;
  }[];
  watches: Watch[];
  contacts: Contact[];
};
const INITIAL_STEPS: Step[] = [
  {
    hours: '0',
    text: "Hi {{name}}, I'm Chris, {{principal_name}}'s AI assistant. {{fit}} Would you be open to an introduction?",
  },
  {
    hours: '48',
    text: 'Hi {{name}}, following up on the possible connection with {{principal_name}}. Would an introduction be useful?',
  },
];
const selectClass =
  'h-9 w-full rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50';
function time(value: string | number | undefined) {
  if (value === undefined || value === null || value === '') return 'Not yet';
  const date = new Date(
    typeof value === 'number' && value < 1e12 ? value * 1000 : value
  );
  return Number.isNaN(date.getTime()) ? 'Unavailable' : date.toLocaleString();
}
function label(value: string) {
  return value.replaceAll('_', ' ');
}

export function ConciergeOperations() {
  const [data, setData] = useState<Operations | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [name, setName] = useState('');
  const [steps, setSteps] = useState<Step[]>(INITIAL_STEPS);
  const [pace, setPace] = useState('60');
  const [cap, setCap] = useState('20');
  const [campaignId, setCampaignId] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [watchContact, setWatchContact] = useState('');
  const [chatId, setChatId] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [reply, setReply] = useState<{
    contactId: string;
    name: string;
    revision: number;
    text: string;
    generated: boolean;
    stale: boolean;
  } | null>(null);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyError, setReplyError] = useState('');
  const mutation = useRef(false);
  const activeRead = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    activeRead.current?.abort();
    const controller = new AbortController();
    activeRead.current = controller;
    setLoading(true);
    try {
      const response = await fetch('/api/concierge/operations', {
        cache: 'no-store',
        signal: controller.signal,
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          body.error || 'Operations are temporarily unavailable.'
        );
      if (
        !body ||
        !Array.isArray(body.campaigns) ||
        !Array.isArray(body.contacts) ||
        !Array.isArray(body.jobs) ||
        !Array.isArray(body.watches) ||
        !Array.isArray(body.suggestions)
      )
        throw new Error(
          'Operations returned an incomplete response. Please refresh.'
        );
      setData(body);
      return true;
    } catch (err) {
      if (!controller.signal.aborted)
        setError(
          err instanceof Error ? err.message : 'Operations could not be loaded.'
        );
      return false;
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);
  useEffect(() => {
    void refresh();
    return () => activeRead.current?.abort();
  }, [refresh]);
  async function command(
    commandName: string,
    payload: Record<string, unknown> = {},
    success = 'Changes saved.'
  ) {
    if (mutation.current) return false;
    mutation.current = true;
    setBusy(commandName);
    setError('');
    setNotice('');
    try {
      const response = await fetch(
        commandName === 'reconcile'
          ? '/api/concierge/reconcile'
          : '/api/concierge/operations',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(
            commandName === 'reconcile'
              ? {}
              : { command: commandName, ...payload }
          ),
        }
      );
      const body = await response.json();
      if (!response.ok)
        throw new Error(body.error || 'The operation could not be completed.');
      let partial = false;
      if (commandName === 'enroll') {
        const results: {
          contact_id: string;
          error?: string;
          created?: boolean;
          state?: string;
        }[] = Array.isArray(body.result)
          ? body.result
          : Array.isArray(body.results)
            ? body.results
            : [];
        if (!results.length)
          throw new Error(
            'Enrollment returned no row outcomes. Check the queue before retrying.'
          );
        const failures = results.filter((row) => row.error);
        partial = failures.length > 0;
        setSelected(failures.map((row) => row.contact_id));
        setNotice(
          `${results.filter((row) => !row.error && row.created).length} newly enrolled; ${results.filter((row) => !row.error && !row.created).length} already enrolled; ${failures.length} need attention.`
        );
        if (partial)
          setError(
            failures
              .map(
                (row) =>
                  `${data?.contacts.find((contact) => contact.id === row.contact_id)?.name || row.contact_id}: ${row.error}`
              )
              .join(' ')
          );
      } else if (commandName === 'reconcile') {
        const totals = body.totals;
        if (!totals)
          throw new Error(
            'CRM sync returned no record counts. Refresh before retrying.'
          );
        setNotice(
          `CRM sync: ${totals.contacts} contacts checked, ${totals.message_inserts_confirmed} message copies inserted, ${totals.notes_created} notes created, ${totals.notes_existing} notes already present. ${body.skipped_contacts ?? 0} contacts skipped.`
        );
        partial = body.status === 'partial';
        if (partial) {
          const failures = (body.contacts ?? []).flatMap(
            (contact: { contact_id: string; errors: string[] }) =>
              (contact.errors ?? []).map(
                (message) =>
                  `${data?.contacts.find((item) => item.id === contact.contact_id)?.name || contact.contact_id}: ${message}`
              )
          );
          setError(
            `Some CRM records still need syncing. ${failures.join(' ')} You can safely run Sync CRM records again; it does not resend messages.`
          );
        }
      } else setNotice(success);
      await refresh();
      return !partial;
    } catch (err) {
      setError(
        `${err instanceof Error ? err.message : 'Request failed.'} Refresh before repeating an action if its result is uncertain.`
      );
      return false;
    } finally {
      mutation.current = false;
      setBusy('');
    }
  }
  async function prepareReply(suggestion: Operations['suggestions'][number]) {
    if (mutation.current) return;
    mutation.current = true;
    setBusy('prepare_reply');
    setReplyError('');
    setReply({
      contactId: suggestion.contact_id,
      name: suggestion.name,
      revision: suggestion.revision,
      text: '',
      generated: false,
      stale: false,
    });
    setReplyOpen(true);
    try {
      const response = await fetch('/api/concierge/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_id: suggestion.contact_id,
          purpose: 'reply',
        }),
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(body.error || 'The AI draft could not be prepared.');
      if (typeof body.draft !== 'string' || !body.draft.trim())
        throw new Error('The provider returned an empty draft.');
      setReply((current) =>
        current ? { ...current, text: body.draft, generated: true } : current
      );
    } catch (err) {
      setReplyError(
        err instanceof Error
          ? err.message
          : 'AI drafting is temporarily unavailable.'
      );
    } finally {
      mutation.current = false;
      setBusy('');
    }
  }
  async function stageReply() {
    if (
      mutation.current ||
      !reply ||
      !reply.text.trim() ||
      reply.stale ||
      !Number.isInteger(reply.revision)
    )
      return;
    mutation.current = true;
    setBusy('stage_reply');
    setReplyError('');
    try {
      const response = await fetch('/api/concierge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'draft',
          contact_id: reply.contactId,
          revision: reply.revision,
          text: reply.text.trim(),
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        if (response.status === 409) {
          setReply((current) =>
            current ? { ...current, stale: true } : current
          );
          throw new Error(
            `${body.error || 'The conversation changed.'} Your edited draft is retained. Refresh Operations and review the latest conversation in Concierge before preparing another reply. This draft keeps its original revision and cannot be staged again.`
          );
        }
        throw new Error(body.error || 'The draft could not be staged.');
      }
      setReplyOpen(false);
      setReply(null);
      setNotice('Reply staged for approval in Concierge. No message was sent.');
      if (body.crm_warning) setError(body.crm_warning);
      await refresh();
    } catch (err) {
      setReplyError(
        err instanceof Error
          ? err.message
          : 'The result is uncertain. Check Concierge before trying again.'
      );
    } finally {
      mutation.current = false;
      setBusy('');
    }
  }
  async function createCampaign() {
    const delays = steps.map((step) => Number(step.hours));
    if (
      !name.trim() ||
      name.length > 100 ||
      steps.some(
        (step) =>
          !step.hours.trim() || !step.text.trim() || step.text.length > 4000
      ) ||
      delays.some(
        (value, index) =>
          !Number.isFinite(value) ||
          value < 0 ||
          value > 720 ||
          (index > 0 && (value - delays[index - 1]) * 3600 < Number(pace))
      ) ||
      !Number.isInteger(Number(pace)) ||
      Number(pace) < 60 ||
      Number(pace) > 86400 ||
      !Number.isInteger(Number(cap)) ||
      Number(cap) < 1 ||
      Number(cap) > 100
    ) {
      setError(
        'Enter a name, complete each draft, and use increasing delays from enrollment (0 to 720 hours). Pacing must be 60 to 86,400 seconds; daily cap 1 to 100. Step gaps must meet the pacing interval.'
      );
      return;
    }
    if (
      await command(
        'create_campaign',
        {
          name: name.trim(),
          steps: steps.map((step, i) => ({
            delay_seconds: Math.round(delays[i] * 3600),
            text: step.text.trim(),
          })),
          pace_seconds: Number(pace),
          daily_cap: Number(cap),
        },
        'Sequence created. Enroll contacts to queue its drafts.'
      )
    ) {
      setName('');
      setShowCreate(false);
    }
  }
  const disabled = !!busy || loading || !data;
  const contacts =
    data?.contacts.filter((contact) => contact.started !== false) ?? [];
  const campaigns =
    data?.campaigns.filter((campaign) => !campaign.paused) ?? [];
  const queued =
    data?.jobs.filter((job) =>
      ['queued', 'pending', 'scheduled', 'retry'].includes(job.state)
    ).length ?? 0;
  const contactName = (id: string) =>
    data?.contacts.find((contact) => contact.id === id)?.name || id;
  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 p-4 sm:p-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-muted-foreground mb-2 flex items-center gap-2 text-sm">
            <ListChecks className="size-4" /> Concierge workspace
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Operations</h1>
          <p className="text-muted-foreground mt-2 text-sm leading-6">
            Prepare thoughtful follow-ups and keep incoming conversations
            moving.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="secondary">Drafts only</Badge>
          {data?.mode === 'simulation' && (
            <Badge variant="outline">Simulation</Badge>
          )}
          <Button
            variant="outline"
            disabled={loading || !!busy}
            onClick={() => {
              setError('');
              void refresh();
            }}
            aria-label="Refresh operations"
          >
            <RefreshCw className={loading ? 'size-4 animate-spin' : 'size-4'} />{' '}
            Refresh
          </Button>
        </div>
      </header>
      <div className="bg-muted/30 flex items-start gap-3 rounded-xl border p-4">
        <ShieldCheck className="text-primary mt-0.5 size-5 shrink-0" />
        <p className="text-sm leading-6">
          Sequences prepare drafts for review in{' '}
          <Link
            href="/concierge"
            className="text-primary underline underline-offset-4"
          >
            Concierge
          </Link>
          . Running a queue does not approve or send messages. Replies and
          permission checks can stop a follow-up.
        </p>
      </div>
      {error && (
        <div
          role="alert"
          className="border-destructive/30 bg-destructive/5 text-destructive rounded-lg border p-4 text-sm"
        >
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="bg-card rounded-lg border p-4 text-sm">
          {notice}
        </div>
      )}
      {reply?.generated && !replyOpen && (
        <Button
          variant="outline"
          disabled={!!busy}
          onClick={() => setReplyOpen(true)}
        >
          <Sparkles className="size-4" /> Resume reply review for {reply.name}
        </Button>
      )}
      {loading && !data && (
        <div
          role="status"
          className="text-muted-foreground flex items-center gap-2 p-8 text-sm"
        >
          <Loader2 className="size-4 animate-spin" /> Loading sequences and
          conversations…
        </div>
      )}
      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              ['Active sequences', campaigns.length],
              ['Queued drafts', queued],
              ['Last worker check', time(data.last_tick)],
            ].map(([title, value]) => (
              <div key={title} className="bg-card rounded-xl border p-4">
                <p className="text-muted-foreground text-xs">{title}</p>
                <p className="mt-2 text-lg font-medium">{value}</p>
              </div>
            ))}
          </div>
          {data.worker_error && (
            <p
              role="alert"
              className="border-destructive/30 text-destructive rounded-lg border p-4 text-sm"
            >
              Worker needs attention: {data.worker_error}
            </p>
          )}
          <section className="bg-card space-y-4 rounded-xl border p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-medium">Draft sequences</h2>
                <p className="text-muted-foreground mt-1 text-sm">
                  Reusable outreach with a clear reason and a measured
                  follow-up.
                </p>
              </div>
              <Button
                variant="outline"
                disabled={disabled}
                onClick={() => setShowCreate(!showCreate)}
              >
                <Plus className="size-4" />{' '}
                {showCreate ? 'Close editor' : 'New sequence'}
              </Button>
            </div>
            {showCreate && (
              <div className="bg-muted/20 space-y-4 rounded-lg border p-4">
                <label className="block space-y-2 text-sm">
                  <span>Sequence name</span>
                  <Input
                    value={name}
                    maxLength={100}
                    disabled={!!busy}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Implementation partner introductions"
                  />
                </label>
                <p className="text-muted-foreground text-xs leading-5">
                  Delays are cumulative hours from enrollment, not from the
                  previous step. Personalize with {'{{name}}'},{' '}
                  {'{{principal_name}}'}, {'{{fit}}'} and {'{{offer}}'}. Review
                  the resolved wording before approval.
                </p>
                {steps.map((step, index) => (
                  <div
                    key={index}
                    className="bg-background space-y-3 rounded-lg border p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <span className="text-sm font-medium">
                        Step {index + 1}
                      </span>
                      <div className="flex items-center gap-2">
                        <label className="flex items-center gap-2 text-xs">
                          <span>Hours after enrollment</span>
                          <Input
                            className="w-24"
                            type="number"
                            min="0"
                            max="720"
                            step="0.25"
                            value={step.hours}
                            disabled={!!busy}
                            onChange={(event) =>
                              setSteps((current) =>
                                current.map((item, i) =>
                                  i === index
                                    ? { ...item, hours: event.target.value }
                                    : item
                                )
                              )
                            }
                          />
                        </label>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Remove step ${index + 1}`}
                          disabled={!!busy || steps.length === 1}
                          onClick={() =>
                            setSteps((current) =>
                              current.filter((_, i) => i !== index)
                            )
                          }
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    </div>
                    <Textarea
                      aria-label={`Step ${index + 1} draft`}
                      value={step.text}
                      maxLength={4000}
                      disabled={!!busy}
                      className="min-h-24"
                      onChange={(event) =>
                        setSteps((current) =>
                          current.map((item, i) =>
                            i === index
                              ? { ...item, text: event.target.value }
                              : item
                          )
                        )
                      }
                    />
                  </div>
                ))}
                <Button
                  variant="ghost"
                  disabled={!!busy || steps.length >= 5}
                  onClick={() =>
                    setSteps((current) => [
                      ...current,
                      {
                        hours: String(Number(current.at(-1)?.hours || 0) + 48),
                        text: '',
                      },
                    ])
                  }
                >
                  <Plus className="size-4" /> Add step ({steps.length}/5)
                </Button>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="space-y-2 text-sm">
                    <span>Minimum seconds between queued drafts</span>
                    <Input
                      type="number"
                      min="60"
                      max="86400"
                      value={pace}
                      disabled={!!busy}
                      onChange={(event) => setPace(event.target.value)}
                    />
                  </label>
                  <label className="space-y-2 text-sm">
                    <span>Daily draft cap</span>
                    <Input
                      type="number"
                      min="1"
                      max="100"
                      value={cap}
                      disabled={!!busy}
                      onChange={(event) => setCap(event.target.value)}
                    />
                  </label>
                </div>
                <Button disabled={disabled} onClick={createCampaign}>
                  {busy === 'create_campaign' && (
                    <Loader2 className="size-4 animate-spin" />
                  )}{' '}
                  Create sequence
                </Button>
              </div>
            )}
            {!data.campaigns.length && !showCreate && (
              <div className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">
                No sequences yet. Create one, then enroll an opportunity you
                have started in Concierge.
              </div>
            )}
            <div className="divide-y">
              {data.campaigns.map((campaign) => (
                <div
                  key={campaign.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-4"
                >
                  <div>
                    <p className="font-medium">
                      {campaign.name}{' '}
                      {campaign.paused && (
                        <Badge variant="secondary">Paused</Badge>
                      )}
                    </p>
                    <p className="text-muted-foreground mt-1 text-xs">
                      {campaign.steps.length} steps ·{' '}
                      {campaign.steps
                        .map((step) => `${step.delay_seconds / 3600}h`)
                        .join(' / ')}{' '}
                      from enrollment · {campaign.daily_cap} drafts/day ·{' '}
                      {campaign.pace_seconds}s pacing
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    disabled={disabled || campaign.paused}
                    onClick={() =>
                      command(
                        'pause_campaign',
                        { campaign_id: campaign.id },
                        'Sequence paused. Queued tasks are cancelled; discard any existing approval drafts in Concierge.'
                      )
                    }
                  >
                    <Pause className="size-4" /> Pause
                  </Button>
                </div>
              ))}
            </div>
            <p className="text-muted-foreground text-xs leading-5">
              Pausing cancels queued tasks. Drafts already awaiting approval
              must be discarded separately in Concierge.
            </p>
          </section>
          <div className="grid items-start gap-5 lg:grid-cols-2">
            <section className="bg-card space-y-4 rounded-xl border p-5">
              <h2 className="font-medium">Enroll opportunities</h2>
              <p className="text-muted-foreground text-sm leading-6">
                Choose contacts whose opportunities are already started in
                Concierge. Enrollment queues work; it does not grant permission
                to contact anyone.
              </p>
              <label className="block space-y-2 text-sm">
                <span>Sequence</span>
                <select
                  className={selectClass}
                  value={campaignId}
                  disabled={disabled || !campaigns.length}
                  onChange={(event) => setCampaignId(event.target.value)}
                >
                  <option value="">Choose a sequence</option>
                  {campaigns.map((campaign) => (
                    <option key={campaign.id} value={campaign.id}>
                      {campaign.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="max-h-60 space-y-2 overflow-y-auto rounded-lg border p-3">
                {contacts.length ? (
                  contacts.map((contact) => (
                    <label
                      key={contact.id}
                      className="hover:bg-muted flex items-start gap-3 rounded-md p-2 text-sm"
                    >
                      <input
                        type="checkbox"
                        className="accent-primary mt-1 size-4"
                        disabled={disabled}
                        checked={selected.includes(contact.id)}
                        onChange={(event) =>
                          setSelected((current) =>
                            event.target.checked
                              ? [...current, contact.id]
                              : current.filter((id) => id !== contact.id)
                          )
                        }
                      />
                      <span className="min-w-0 break-words">
                        {contact.name || contact.phone}
                        <span className="text-muted-foreground block text-xs">
                          {contact.phone}
                        </span>
                      </span>
                    </label>
                  ))
                ) : (
                  <p className="text-muted-foreground text-sm">
                    Start an opportunity in Concierge to make it available here.
                  </p>
                )}
              </div>
              <Button
                disabled={disabled || !campaignId || !selected.length}
                onClick={async () => {
                  if (
                    await command(
                      'enroll',
                      { campaign_id: campaignId, contact_ids: selected },
                      'Selected opportunities enrolled. Due work will prepare review drafts.'
                    )
                  )
                    setSelected([]);
                }}
              >
                Enroll {selected.length} selected
              </Button>
            </section>
            <section className="bg-card space-y-4 rounded-xl border p-5">
              <h2 className="flex items-center gap-2 font-medium">
                <Inbox className="size-4" /> Incoming next steps
              </h2>
              <p className="text-muted-foreground text-sm">
                Suggestions are for review; they do not change consent or send
                replies.
              </p>
              {!data.suggestions.length && (
                <p className="text-muted-foreground rounded-lg border border-dashed p-5 text-sm">
                  No next-step suggestions yet. Sync a conversation in Concierge
                  or register a watch below.
                </p>
              )}
              {data.suggestions.map((suggestion, i) => (
                <div
                  key={`${suggestion.contact_id}:${i}`}
                  className="space-y-2 rounded-lg border p-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">
                      {suggestion.name}
                    </span>
                    <Badge variant="secondary">
                      {label(suggestion.intent)}
                    </Badge>
                  </div>
                  <p className="text-sm leading-6 whitespace-pre-wrap">
                    {suggestion.suggestion}
                  </p>
                  <Link
                    href="/concierge"
                    className="text-primary inline-flex items-center gap-1 text-sm underline underline-offset-4"
                  >
                    Review in Concierge <ArrowRight className="size-3" />
                  </Link>
                  <div>
                    <Button
                      variant="outline"
                      disabled={
                        disabled || !Number.isInteger(suggestion.revision)
                      }
                      onClick={() => prepareReply(suggestion)}
                    >
                      <Sparkles className="size-4" /> Prepare AI reply
                    </Button>
                  </div>
                </div>
              ))}
            </section>
          </div>
          <section className="bg-card space-y-4 rounded-xl border p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="flex items-center gap-2 font-medium">
                  <Clock3 className="size-4" /> Draft queue
                </h2>
                <p className="text-muted-foreground mt-1 text-sm">
                  A completed queue job means its preparation finished, not that
                  a message was sent.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={disabled}
                  onClick={() => command('reconcile')}
                >
                  {busy === 'reconcile' && (
                    <Loader2 className="size-4 animate-spin" />
                  )}{' '}
                  Sync CRM records
                </Button>
                <Button
                  disabled={disabled}
                  onClick={() =>
                    command(
                      'tick',
                      {},
                      'Due work checked. Review prepared drafts in Concierge.'
                    )
                  }
                >
                  {busy === 'tick' ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <RefreshCw className="size-4" />
                  )}{' '}
                  Run due drafts
                </Button>
              </div>
            </div>
            {!data.jobs.length && (
              <p className="text-muted-foreground rounded-lg border border-dashed p-5 text-sm">
                Your queue is empty. Enroll an opportunity to prepare its first
                draft.
              </p>
            )}
            <div className="divide-y">
              {data.jobs.map((job) => (
                <div key={job.id} className="space-y-2 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-medium">
                      {typeof job.contact === 'string'
                        ? contactName(job.contact)
                        : job.contact?.name || job.contact?.phone || 'Contact'}
                    </span>
                    <Badge variant="outline">{label(job.state)}</Badge>
                  </div>
                  <p className="text-muted-foreground text-xs">
                    Due {time(job.due)}
                    {job.payload?.campaign_id
                      ? ` · ${data.campaigns.find((c) => c.id === job.payload?.campaign_id)?.name || 'Sequence'}`
                      : ''}
                  </p>
                  {job.payload?.text && (
                    <p className="text-muted-foreground text-sm break-words whitespace-pre-wrap">
                      {job.payload.text}
                    </p>
                  )}
                  {job.error && (
                    <p className="text-destructive text-sm">{job.error}</p>
                  )}
                </div>
              ))}
            </div>
          </section>
          <section className="bg-card space-y-4 rounded-xl border p-5">
            <h2 className="font-medium">Conversation watches</h2>
            <p className="text-muted-foreground max-w-3xl text-sm leading-6">
              Register a provider chat ID for an existing opportunity so the
              worker can check incoming messages. Use the exact chat ID from
              your WhatsApp connection.
              {data.mode === 'simulation'
                ? ' Simulation does not read the provider; use simulated replies in Concierge.'
                : ' An active provider connection is required.'}
            </p>
            <div className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]">
              <label className="space-y-2 text-sm">
                <span>Opportunity</span>
                <select
                  className={selectClass}
                  value={watchContact}
                  disabled={disabled}
                  onChange={(event) => setWatchContact(event.target.value)}
                >
                  <option value="">Choose a contact</option>
                  {contacts.map((contact) => (
                    <option key={contact.id} value={contact.id}>
                      {contact.name || contact.phone}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-2 text-sm">
                <span>Provider chat ID</span>
                <Input
                  value={chatId}
                  maxLength={300}
                  disabled={disabled}
                  onChange={(event) => setChatId(event.target.value)}
                  placeholder="Exact provider chat ID"
                />
              </label>
              <Button
                disabled={disabled || !watchContact || !chatId.trim()}
                onClick={async () => {
                  if (
                    await command(
                      'watch',
                      {
                        contact_id: watchContact,
                        chat_id: chatId.trim(),
                        enabled: true,
                      },
                      'Conversation watch saved.'
                    )
                  ) {
                    setChatId('');
                    setWatchContact('');
                  }
                }}
              >
                Add watch
              </Button>
            </div>
            <div className="divide-y">
              {data.watches.map((watch) => (
                <div
                  key={watch.contact_id}
                  className="flex flex-wrap items-center justify-between gap-3 py-4"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {contactName(watch.contact_id)}
                    </p>
                    <p className="text-muted-foreground mt-1 text-xs break-all">
                      {watch.chat_id} · Last sync: {time(watch.last_sync)}
                    </p>
                    {watch.error && (
                      <p className="text-destructive mt-1 text-sm">
                        {watch.error}
                      </p>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    disabled={disabled}
                    onClick={() =>
                      command(
                        'watch',
                        {
                          contact_id: watch.contact_id,
                          chat_id: watch.chat_id,
                          enabled: !watch.enabled,
                        },
                        watch.enabled ? 'Watch paused.' : 'Watch enabled.'
                      )
                    }
                  >
                    {watch.enabled ? 'Pause watch' : 'Enable watch'}
                  </Button>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
      <Dialog
        open={replyOpen}
        onOpenChange={(open) => {
          if (!mutation.current) setReplyOpen(open);
        }}
      >
        <DialogContent
          showCloseButton={!busy}
          className="max-h-[90dvh] overflow-y-auto sm:max-w-xl"
        >
          <DialogHeader>
            <DialogTitle>
              Review reply to {reply?.name || 'contact'}
            </DialogTitle>
            <DialogDescription>
              Review the wording against the conversation. Staging creates an
              approval draft in Concierge; it does not send a message.
            </DialogDescription>
          </DialogHeader>
          {busy === 'prepare_reply' && (
            <p
              role="status"
              className="text-muted-foreground flex items-center gap-2 text-sm"
            >
              <Loader2 className="size-4 animate-spin" /> Preparing a reply from
              the conversation and your brief…
            </p>
          )}
          {reply?.generated && (
            <>
              <Badge variant="secondary" className="w-fit">
                Source: AI draft · Review required
              </Badge>
              <label className="space-y-2 text-sm">
                <span>Editable reply</span>
                <Textarea
                  aria-label="Editable AI reply"
                  className="min-h-56"
                  value={reply.text}
                  maxLength={4000}
                  disabled={!!busy}
                  onChange={(event) =>
                    setReply((current) =>
                      current
                        ? { ...current, text: event.target.value }
                        : current
                    )
                  }
                />
              </label>
              <p className="text-muted-foreground text-xs">
                {reply.text.length}/4,000 characters · Based on conversation
                revision {reply.revision}
              </p>
            </>
          )}
          {replyError && (
            <p
              role="alert"
              className="border-destructive/30 bg-destructive/5 text-destructive rounded-lg border p-3 text-sm"
            >
              {replyError}
            </p>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={!!busy}
              onClick={() => setReplyOpen(false)}
            >
              Close
            </Button>
            {reply?.stale && (
              <Button
                variant="outline"
                disabled={!!busy || loading}
                onClick={() => void refresh()}
              >
                <RefreshCw className="size-4" /> Refresh Operations
              </Button>
            )}
            <Button
              disabled={
                !!busy ||
                !reply?.generated ||
                !reply.text.trim() ||
                reply.text.length > 4000 ||
                reply.stale ||
                !Number.isInteger(reply.revision)
              }
              onClick={stageReply}
            >
              {busy === 'stage_reply' ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <ArrowRight className="size-4" />
              )}{' '}
              Stage for approval
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
