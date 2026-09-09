'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

type Row = Record<string, unknown>;
type Prospect = {
  id: string;
  name: string;
  company?: string;
  role?: string;
  phone?: string;
  source?: string;
  fit?: string;
  status?: string;
  qualification?: unknown;
  phone_status?: string;
  contact_id?: string;
  brief_stale?: boolean;
  calendar?: { status: string; slots: { start: string; end: string }[] };
  conversation?: { status?: string };
  booking?: Row;
  amendment?: { status: string; digest: string; proposal: Row };
  research?: Row;
  phone_research?: Row;
  candidate_phone?: string;
  calendar_preferences?: Row;
  calendar_exception?: Row;
};
type Brief = {
  principal_name: string;
  offer: string;
  audience: string;
  geography: string;
  exclusions: string;
  claims: string;
  timezone: string;
  booking_link: string;
  budget_usd: number;
};
type Report = {
  mode: 'simulation' | 'live';
  brief: Brief | null;
  brief_revision: number;
  prospects: Prospect[];
  messages: {
    id: string;
    prospect_id: string;
    direction: string;
    text: string;
    simulated: boolean;
    created_at: string;
  }[];
  decisions: {
    id: string;
    prospect_id: string;
    purpose: string;
    text: string;
    status: string;
    revision?: string;
  }[];
  jobs: Row[];
  metrics: Row;
  readiness: Row;
  events: Row[];
};
const emptyBrief: Brief = {
  principal_name: '',
  offer: '',
  audience: '',
  geography: '',
  exclusions: '',
  claims: '',
  timezone: 'Africa/Johannesburg',
  booking_link: '',
  budget_usd: 0,
};
const input = 'w-full rounded-md border bg-background px-3 py-2 text-sm';
const button =
  'rounded-md border px-3 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50';
const panel = 'space-y-4 rounded-xl border bg-card p-5';
const display = (value: unknown) =>
  typeof value === 'string' ? value : JSON.stringify(value ?? null);

export function DogfoodWorkspace() {
  const [report, setReport] = useState<Report | null>(null);
  const [brief, setBrief] = useState<Brief>(emptyBrief);
  const [tab, setTab] = useState('Brief');
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reply, setReply] = useState('');
  const [reason, setReason] = useState('');
  const [source, setSource] = useState('fixture');
  const [limit, setLimit] = useState(10);
  const [phone, setPhone] = useState('');
  const [evidence, setEvidence] = useState('');
  const [party, setParty] = useState('recipient');
  const [scope, setScope] = useState('contact');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [minutes, setMinutes] = useState(0);
  const [note, setNote] = useState('');
  const [useful, setUseful] = useState(true);
  const [hours, setHours] = useState(24);
  const [amendmentOperation, setAmendmentOperation] = useState('reschedule');
  const [calendarTimezone, setCalendarTimezone] = useState(
    'Africa/Johannesburg'
  );
  const [workingStart, setWorkingStart] = useState('09:00');
  const [workingEnd, setWorkingEnd] = useState('17:00');
  const [workingDays, setWorkingDays] = useState([0, 1, 2, 3, 4]);
  const [calendarAccess, setCalendarAccess] = useState(true);
  const [busyInterval, setBusyInterval] = useState(false);
  const initialized = useRef(false);
  const pending = useRef(false);
  const refresh = useCallback(async () => {
    const response = await fetch('/api/concierge/dogfood', {
      cache: 'no-store',
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(data.error || 'Workspace could not be loaded.');
    if (
      !['simulation', 'live'].includes(data.mode) ||
      !Array.isArray(data.prospects) ||
      !Array.isArray(data.messages) ||
      !Array.isArray(data.decisions)
    )
      throw new Error('The service returned an incomplete workspace.');
    setReport(data);
    if (!initialized.current) {
      setBrief({ ...emptyBrief, ...data.brief });
      initialized.current = true;
    }
  }, []);
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
  }, [refresh]);
  const workPending = report?.jobs?.some((job) =>
    ['queued', 'running'].includes(String(job.state))
  );
  useEffect(() => {
    if (!workPending) return;
    // Worker completion must become visible without requiring another operator action.
    const timer = setInterval(() => {
      if (!pending.current) void refresh().catch((e) => setError(e.message));
    }, 2000);
    return () => clearInterval(timer);
  }, [workPending, refresh]);
  async function act(command: string, fields: Row = {}) {
    if (pending.current) return false;
    pending.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const response = await fetch('/api/concierge/dogfood', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, ...fields }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Action failed.');
      try {
        await refresh();
      } catch {
        throw new Error(
          'The action completed, but the workspace could not refresh. Refresh before repeating it.'
        );
      }
      setNotice(
        typeof data.crm_warning === 'string'
          ? data.crm_warning
          : 'Workspace updated.'
      );
      return true;
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : 'Action failed. Refresh before retrying.'
      );
      return false;
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  const prospect = report?.prospects.find((p) => p.id === selected);
  const simulation = report?.mode === 'simulation';
  const selectedFields = { prospect_id: selected };
  function selectProspect(id: string) {
    if (id === selected) return;
    setSelected(id);
    // A draft or permission belongs to its person; switching must not redirect it.
    setReply('');
    setEvidence('');
    setReason('');
    setStart('');
    setEnd('');
    setNote('');
    setMinutes(0);
    setUseful(true);
    setPhone(report?.prospects.find((p) => p.id === id)?.phone || '');
  }
  function exportPilot() {
    if (!report) return;
    const url = URL.createObjectURL(
      new Blob(
        [
          JSON.stringify(
            { exported_at: new Date().toISOString(), ...report },
            null,
            2
          ),
        ],
        { type: 'application/json' }
      )
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `chris-pilot-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <main className="mx-auto max-w-6xl space-y-6 p-4 md:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Chris · Outbound dogfood</h1>
          <p className="text-muted-foreground text-sm">
            Brief → find people → converse → introduce → measure.
          </p>
        </div>
        <button
          className={button}
          disabled={busy}
          onClick={() => void refresh().catch((e) => setError(e.message))}
        >
          Refresh
        </button>
      </div>
      <div className="rounded-lg border p-3 text-sm">
        {report
          ? simulation
            ? 'Simulation: messages and calendar effects stay local. Fixture results are fictional; real research and model calls may incur configured costs.'
            : 'Live workspace: review and prepare here. This screen does not execute external messages or calendar invitations.'
          : 'Connecting to your workspace…'}
      </div>
      {error && (
        <div
          role="alert"
          className="border-destructive rounded-lg border p-3 text-sm"
        >
          {error}
        </div>
      )}
      {notice && (
        <p role="status" className="text-sm">
          {notice}
        </p>
      )}
      <nav aria-label="Dogfood workflow" className="flex flex-wrap gap-2">
        {[
          'Brief',
          'Prospects',
          'Conversation',
          'Review',
          'Connections & pilot',
        ].map((name) => (
          <button
            key={name}
            className={`${button} ${tab === name ? 'bg-muted' : ''}`}
            aria-current={tab === name ? 'page' : undefined}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </nav>
      {report && (
        <div className="flex flex-wrap gap-2">
          <button
            className={button}
            disabled={busy}
            onClick={() => void act('pause')}
          >
            Pause all work
          </button>
          <button
            className={button}
            disabled={busy}
            onClick={() => void act('unpause')}
          >
            Resume workspace
          </button>
          <button className={button} onClick={exportPilot}>
            Download pilot evidence
          </button>
          <button
            className={button}
            disabled={busy}
            onClick={() => void act('reconcile')}
          >
            Reconcile CRM
          </button>
          {!simulation && (
            <button
              className={button}
              disabled={busy}
              onClick={() => void act('sync')}
            >
              Sync provider replies
            </button>
          )}
        </div>
      )}
      {prospect?.brief_stale && (
        <div role="status" className="space-y-2 rounded-lg border p-3 text-sm">
          <p>
            This conversation belongs to an earlier brief. Preserve its history
            and create a new pursuit for the revised brief.
          </p>
          <button
            className={button}
            disabled={busy}
            onClick={() => void act('new_pursuit', selectedFields)}
          >
            Start a new pursuit for this brief
          </button>
        </div>
      )}
      {tab === 'Prospects' && prospect && (
        <section className={panel}>
          <h3 className="font-semibold">Research {prospect.name}</h3>
          <p className="text-sm">
            Provider calls use the approved brief and configured budget. A
            suggested phone needs your identity/evidence review before it
            becomes a contact route.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              className={button}
              disabled={busy}
              onClick={() => void act('research', selectedFields)}
            >
              Research and assess fit
            </button>
            <button
              className={button}
              disabled={busy}
              onClick={() => void act('research_phone', selectedFields)}
            >
              Research contact route
            </button>
            {prospect.candidate_phone && (
              <button
                className={button}
                onClick={() => {
                  setPhone(prospect.candidate_phone || '');
                  setEvidence('');
                }}
              >
                Review suggested phone: {prospect.candidate_phone}
              </button>
            )}
          </div>
          {prospect.research && (
            <details>
              <summary>Qualification evidence</summary>
              <pre className="overflow-auto text-xs whitespace-pre-wrap">
                {JSON.stringify(prospect.research, null, 2)}
              </pre>
            </details>
          )}
          {prospect.phone_research && (
            <details>
              <summary>Phone research evidence</summary>
              <pre className="overflow-auto text-xs whitespace-pre-wrap">
                {JSON.stringify(prospect.phone_research, null, 2)}
              </pre>
            </details>
          )}
        </section>
      )}
      {tab === 'Brief' && (
        <form
          className={panel}
          onSubmit={(e) => {
            e.preventDefault();
            void act('save_brief', { brief });
          }}
        >
          <h2 className="text-lg font-semibold">Your outbound brief</h2>
          <p className="text-muted-foreground text-sm">
            Use one offer, audience and geography. Saving a revision may
            invalidate queued work. Budget 0 keeps paid work blocked.
          </p>
          {(
            [
              'principal_name',
              'offer',
              'audience',
              'geography',
              'exclusions',
              'claims',
              'timezone',
              'booking_link',
            ] as const
          ).map((key) => (
            <label key={key} className="block space-y-1 text-sm">
              <span>
                {
                  {
                    principal_name: 'Your name',
                    offer: 'What you offer',
                    audience: 'Who Chris should find',
                    geography: 'Geography',
                    exclusions: 'Exclusions and existing relationships',
                    claims: 'Supported claims and evidence',
                    timezone: 'Your timezone',
                    booking_link: 'Booking link (optional)',
                  }[key]
                }
              </span>
              <textarea
                className={input}
                rows={['offer', 'audience', 'claims'].includes(key) ? 3 : 1}
                value={brief[key]}
                onChange={(e) => setBrief({ ...brief, [key]: e.target.value })}
                required={
                  !['exclusions', 'claims', 'booking_link'].includes(key)
                }
              />
            </label>
          ))}
          <label className="block text-sm">
            Research and model budget (USD)
            <input
              className={input}
              type="number"
              min="0"
              max="10000"
              step="0.01"
              value={brief.budget_usd}
              onChange={(e) =>
                setBrief({ ...brief, budget_usd: Number(e.target.value) })
              }
            />
          </label>
          <button className={button} disabled={busy || !report}>
            Save brief
          </button>
          <span className="text-muted-foreground ml-3 text-sm">
            Saved revision: {report?.brief_revision ?? 0}
          </span>
        </form>
      )}
      {tab === 'Prospects' && (
        <div className="space-y-5">
          <section className={panel}>
            <h2 className="text-lg font-semibold">Find and qualify people</h2>
            <div className="flex flex-wrap gap-3">
              <label className="text-sm">
                Source
                <select
                  className={input}
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                >
                  <option value="fixture">
                    Fictional fixtures (no research spend)
                  </option>
                  <option value="treg">
                    Real research (configured treg provider)
                  </option>
                </select>
              </label>
              <label className="text-sm">
                Candidates
                <input
                  className={input}
                  type="number"
                  min="1"
                  max="20"
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value))}
                />
              </label>
              <button
                className={button}
                disabled={busy || !report?.brief}
                onClick={() => void act('discover', { source, limit })}
              >
                Find candidates
              </button>
              <button
                className={button}
                disabled={busy || !report}
                onClick={() => void act('process')}
              >
                Process queued work
              </button>
            </div>
            <p className="text-muted-foreground text-sm">
              A profile or phone number does not establish permission to
              contact. Missing numbers stay visible.
            </p>
          </section>
          <div className="grid gap-4 md:grid-cols-2">
            {report?.prospects.map((p) => (
              <button
                key={p.id}
                className={`${panel} text-left ${selected === p.id ? 'ring-primary ring-2' : ''}`}
                onClick={() => {
                  selectProspect(p.id);
                }}
              >
                <h3 className="font-semibold">{p.name}</h3>
                <p className="text-sm">
                  {[p.role, p.company].filter(Boolean).join(' · ')}
                </p>
                <p className="text-sm">{p.fit || 'Fit needs review'}</p>
                <p className="text-muted-foreground text-xs break-words">
                  Source: {p.source || 'No source'}
                  <br />
                  Status: {p.status} · {p.phone_status || 'Phone unresolved'}
                  <br />
                  {p.phone || 'No phone found'}
                </p>
              </button>
            ))}
          </div>
          {!report?.prospects.length && (
            <p className="text-sm">
              Save a brief, then find the first candidates.
            </p>
          )}
          {prospect && (
            <section className={panel}>
              <h3 className="font-semibold">Review {prospect.name}</h3>
              <p className="text-sm break-words">
                Qualification: {display(prospect.qualification)}
              </p>
              <label className="block text-sm">
                Reason
                <textarea
                  className={input}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <div className="flex gap-2">
                {['qualified', 'rejected'].map((verdict) => (
                  <button
                    key={verdict}
                    className={button}
                    disabled={busy || !reason.trim()}
                    onClick={() =>
                      void act('qualify', {
                        ...selectedFields,
                        verdict,
                        reason,
                      })
                    }
                  >
                    {verdict === 'qualified' ? 'Qualify' : 'Reject'}
                  </button>
                ))}
              </div>
              <label className="block text-sm">
                International phone
                <input
                  className={input}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+…"
                />
              </label>
              <label className="block text-sm">
                Evidence linking this number to the person
                <textarea
                  className={input}
                  value={evidence}
                  onChange={(e) => setEvidence(e.target.value)}
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  className={button}
                  disabled={busy || !phone || !evidence.trim()}
                  onClick={() =>
                    void act('enrich', {
                      ...selectedFields,
                      phone,
                      source_ref: evidence,
                    })
                  }
                >
                  Record contact evidence
                </button>
                <button
                  className={button}
                  disabled={busy || !prospect.phone}
                  onClick={() => void act('promote', selectedFields)}
                >
                  Save qualified person to CRM
                </button>
                <button
                  className={button}
                  onClick={() => setTab('Conversation')}
                >
                  Open conversation
                </button>
              </div>
            </section>
          )}
        </div>
      )}
      {tab === 'Conversation' && (
        <div className="space-y-5">
          <section className={panel}>
            <h2 className="text-lg font-semibold">
              {simulation ? 'Play the recipient' : 'Conversation preparation'}
            </h2>
            <label className="block text-sm">
              Person
              <select
                className={input}
                value={selected}
                onChange={(e) => selectProspect(e.target.value)}
              >
                <option value="">Choose a prospect</option>
                {report?.prospects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                className={button}
                disabled={busy || !selected}
                onClick={() => void act('start', selectedFields)}
              >
                Let Chris initiate
              </button>
              <button
                className={button}
                disabled={busy || !selected}
                onClick={() => void act('takeover', selectedFields)}
              >
                Take over
              </button>
              <button
                className={button}
                disabled={busy || !selected}
                onClick={() => void act('resume', selectedFields)}
              >
                Resume Chris
              </button>
              <button
                className={button}
                disabled={busy || !report}
                onClick={() => void act('process')}
              >
                Process queued work
              </button>
            </div>
            <p className="text-muted-foreground text-sm">
              Model:{' '}
              {display(report?.readiness?.model ?? 'Check connection status')}.
              Review prepared actions below. Taking over pauses Chris.
            </p>
          </section>
          <section className={panel} aria-label="Conversation messages">
            {report?.messages
              .filter((m) => m.prospect_id === selected)
              .map((m) => (
                <article
                  key={m.id}
                  className={`max-w-[90%] rounded-lg border p-3 ${['outbound', 'out'].includes(m.direction) ? 'bg-muted ml-auto' : ''}`}
                >
                  <p className="text-muted-foreground text-xs">
                    {['outbound', 'out'].includes(m.direction)
                      ? 'Chris'
                      : prospect?.name || 'Recipient'}{' '}
                    · {m.simulated ? 'simulated' : 'provider record'} ·{' '}
                    {m.created_at}
                  </p>
                  <p className="text-sm whitespace-pre-wrap">{m.text}</p>
                </article>
              ))}
            {simulation && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void act('reply', { ...selectedFields, text: reply }).then(
                    (ok) => {
                      if (ok) setReply('');
                    }
                  );
                }}
              >
                <label className="block text-sm">
                  Type as the recipient
                  <textarea
                    className={input}
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                  />
                </label>
                <button
                  className={`${button} mt-2`}
                  disabled={busy || !selected || !reply.trim()}
                >
                  Add recipient reply
                </button>
              </form>
            )}
          </section>
          <section className={panel}>
            <h3 className="font-semibold">Permission and introduction</h3>
            <p className="text-muted-foreground text-sm">
              Record what each party actually agreed to, with its source. This
              is an attestation, not inferred permission.
            </p>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="text-sm">
                Party
                <select
                  className={input}
                  value={party}
                  onChange={(e) => setParty(e.target.value)}
                >
                  <option value="recipient">Recipient</option>
                  <option value="principal">You</option>
                </select>
              </label>
              <label className="text-sm">
                Permission
                <select
                  className={input}
                  value={scope}
                  onChange={(e) => setScope(e.target.value)}
                >
                  {[
                    'contact',
                    'introduction',
                    'group',
                    'scheduling',
                    'booking',
                  ].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
            </div>
            <label className="block text-sm">
              Supporting message or evidence
              <textarea
                className={input}
                value={evidence}
                onChange={(e) => setEvidence(e.target.value)}
              />
            </label>
            <button
              className={button}
              disabled={busy || !selected || !evidence.trim()}
              onClick={() =>
                void act('consent', {
                  ...selectedFields,
                  party,
                  scope,
                  source_ref: evidence,
                })
              }
            >
              Record permission
            </button>
            <button
              className={`${button} ml-2`}
              disabled={busy || !selected}
              onClick={() => void act('introduce', selectedFields)}
            >
              Prepare introduction
            </button>
          </section>
          <section className={panel}>
            <h3 className="font-semibold">Meeting proposal</h3>
            <p className="text-muted-foreground text-sm">
              Use ISO timestamps with offsets, for example
              2026-10-01T10:00:00+02:00. A prepared proposal is not a booked
              meeting.
            </p>
            <label className="block text-sm">
              Start
              <input
                className={input}
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              End
              <input
                className={input}
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </label>
            <button
              className={button}
              disabled={busy || !selected || !start || !end}
              onClick={() =>
                void act('propose', {
                  ...selectedFields,
                  start,
                  end,
                  timezone: brief.timezone,
                })
              }
            >
              Prepare time proposal
            </button>
            <button
              className={`${button} ml-2`}
              disabled={busy || !selected || !start || !end}
              onClick={() =>
                void act('book', { ...selectedFields, start, end })
              }
            >
              Prepare booking
            </button>
          </section>
        </div>
      )}
      {tab === 'Conversation' && simulation && prospect && (
        <section className={panel}>
          <h3 className="font-semibold">Calendar scenario</h3>
          <p className="text-sm">
            Use the Party and Supporting evidence fields above. Changes
            invalidate previous proposals. Missing calendar access yields
            tentative times; it never proves availability.
          </p>
          <label className="block text-sm">
            Calendar timezone
            <input
              className={input}
              value={calendarTimezone}
              onChange={(e) => setCalendarTimezone(e.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-3">
            {[
              'Monday',
              'Tuesday',
              'Wednesday',
              'Thursday',
              'Friday',
              'Saturday',
              'Sunday',
            ].map((label, day) => (
              <label key={day} className="flex gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={workingDays.includes(day)}
                  onChange={(e) =>
                    setWorkingDays(
                      e.target.checked
                        ? [...workingDays, day].sort()
                        : workingDays.filter((value) => value !== day)
                    )
                  }
                />
                {label}
              </label>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm">
              Working hours start
              <input
                className={input}
                type="time"
                value={workingStart}
                onChange={(e) => setWorkingStart(e.target.value)}
              />
            </label>
            <label className="text-sm">
              Working hours end
              <input
                className={input}
                type="time"
                value={workingEnd}
                onChange={(e) => setWorkingEnd(e.target.value)}
              />
            </label>
          </div>
          <label className="flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={calendarAccess}
              onChange={(e) => setCalendarAccess(e.target.checked)}
            />
            Simulated calendar access available
          </label>
          <label className="flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={busyInterval}
              onChange={(e) => setBusyInterval(e.target.checked)}
            />
            Mark the Start/End interval above as busy
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              className={button}
              disabled={
                busy ||
                !evidence.trim() ||
                !workingDays.length ||
                (busyInterval && (!start || !end))
              }
              onClick={() =>
                void act('calendar_preferences', {
                  ...selectedFields,
                  party,
                  timezone: calendarTimezone,
                  windows: workingDays.map((weekday) => ({
                    weekday,
                    start: workingStart,
                    end: workingEnd,
                  })),
                  calendar_access: calendarAccess,
                  simulated_busy: busyInterval ? [{ start, end }] : [],
                  source_ref: evidence,
                })
              }
            >
              Save calendar scenario
            </button>
            <button
              className={button}
              disabled={busy || !start || !end || !evidence.trim()}
              onClick={() =>
                void act('request_calendar_exception', {
                  ...selectedFields,
                  party,
                  start,
                  end,
                  source_ref: evidence,
                })
              }
            >
              Request working-hours exception
            </button>
            <button
              className={button}
              disabled={busy || !brief.booking_link}
              onClick={() => void act('booking_link', selectedFields)}
            >
              Prepare booking-link fallback
            </button>
          </div>
          {prospect.calendar_exception && (
            <p className="text-sm break-words">
              Exception: {display(prospect.calendar_exception)}
            </p>
          )}
        </section>
      )}
      {tab === 'Conversation' && simulation && prospect?.booking && (
        <section className={panel}>
          <h3 className="font-semibold">Change the simulated booking</h3>
          <p className="text-sm">
            Record the agreed change in the supporting evidence field above. For
            rescheduling, enter the new start and end above. Review the exact
            change before approval.
          </p>
          <label className="block text-sm">
            Change
            <select
              className={input}
              value={amendmentOperation}
              onChange={(e) => setAmendmentOperation(e.target.value)}
            >
              <option value="reschedule">Reschedule</option>
              <option value="cancel">Cancel</option>
            </select>
          </label>
          <button
            className={button}
            disabled={
              busy ||
              !evidence.trim() ||
              (amendmentOperation === 'reschedule' && (!start || !end))
            }
            onClick={() =>
              void act('prepare_amendment', {
                ...selectedFields,
                operation: amendmentOperation,
                source_ref: evidence,
                ...(amendmentOperation === 'reschedule' ? { start, end } : {}),
              })
            }
          >
            Prepare booking change
          </button>
          {prospect.amendment && (
            <div className="space-y-3 rounded-md border p-3">
              <p className="text-sm">{prospect.amendment.status}</p>
              <pre className="overflow-auto text-xs whitespace-pre-wrap">
                {JSON.stringify(prospect.amendment.proposal, null, 2)}
              </pre>
              <button
                className={button}
                disabled={busy || prospect.amendment.status !== 'pending'}
                onClick={() =>
                  void act('approve_amendment', {
                    ...selectedFields,
                    digest: prospect.amendment?.digest,
                  })
                }
              >
                Approve change in simulation
              </button>
            </div>
          )}
        </section>
      )}
      {tab === 'Conversation' && prospect?.calendar && (
        <section className={panel}>
          <h3 className="font-semibold">
            Available simulated slots · {prospect.calendar.status}
          </h3>
          <p className="text-sm">
            Select a returned slot to prepare its booking. New conversation
            evidence or expiration requires a fresh proposal.
          </p>
          {prospect.calendar.slots.map((slot) => (
            <button
              key={slot.start}
              className={`${button} mr-2`}
              disabled={busy}
              onClick={() => {
                setStart(slot.start);
                setEnd(slot.end);
              }}
            >
              {slot.start} → {slot.end}
            </button>
          ))}
        </section>
      )}
      {tab === 'Conversation' && simulation && (
        <section className={panel}>
          <h3 className="font-semibold">Follow-up and recovery testing</h3>
          <label className="block text-sm">
            Hours
            <input
              className={input}
              type="number"
              min="0"
              max="720"
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              className={button}
              disabled={busy || !selected}
              onClick={() =>
                void act('followup', {
                  ...selectedFields,
                  seconds: hours * 3600,
                })
              }
            >
              Schedule follow-up
            </button>
            <button
              className={button}
              disabled={busy || !report}
              onClick={() => void act('advance', { seconds: hours * 3600 })}
            >
              Advance simulated clock
            </button>
            <button
              className={button}
              disabled={busy || !selected || !reply.trim()}
              onClick={() =>
                void act('manual_reply', {
                  ...selectedFields,
                  text: reply,
                }).then((ok) => {
                  if (ok) setReply('');
                })
              }
            >
              Send typed text as human after takeover
            </button>
            <button
              className={button}
              disabled={busy || !selected || !evidence.trim()}
              onClick={() =>
                void act('attended', {
                  ...selectedFields,
                  source_ref: evidence,
                })
              }
            >
              Record meeting attendance
            </button>
          </div>
        </section>
      )}
      {(tab === 'Conversation' || tab === 'Review') && (
        <section className={panel}>
          <h2 className="text-lg font-semibold">Action review</h2>
          {report?.decisions
            .filter((d) => tab === 'Review' || d.prospect_id === selected)
            .map((d) => (
              <article key={d.id} className="space-y-2 rounded-lg border p-3">
                <p className="text-sm font-medium">
                  {report.prospects.find((p) => p.id === d.prospect_id)?.name ||
                    d.prospect_id}{' '}
                  · {d.purpose} · {d.status}
                </p>
                <p className="text-sm whitespace-pre-wrap">{d.text}</p>
                {[
                  'pending',
                  'prepared',
                  'proposed',
                  'awaiting_review',
                ].includes(d.status) && (
                  <div className="flex gap-2">
                    <button
                      className={button}
                      disabled={busy || !simulation}
                      onClick={() => void act('approve', { decision_id: d.id })}
                    >
                      {simulation
                        ? 'Approve in simulation'
                        : 'Live execution unavailable here'}
                    </button>
                    <button
                      className={button}
                      disabled={busy}
                      onClick={() => void act('discard', { decision_id: d.id })}
                    >
                      Discard
                    </button>
                  </div>
                )}
              </article>
            ))}
          {!report?.decisions.length && (
            <p className="text-muted-foreground text-sm">
              Chris’s proposed actions appear here.
            </p>
          )}
        </section>
      )}
      {tab === 'Review' && (
        <section className={panel}>
          <h2 className="text-lg font-semibold">Your effort and judgment</h2>
          <label className="block text-sm">
            Prospect
            <select
              className={input}
              value={selected}
              onChange={(e) => selectProspect(e.target.value)}
            >
              <option value="">Choose a prospect</option>
              {report?.prospects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={useful}
              onChange={(e) => setUseful(e.target.checked)}
            />
            This opportunity was useful
          </label>
          <label className="block text-sm">
            Your minutes spent
            <input
              className={input}
              type="number"
              min="0"
              max="1440"
              value={minutes}
              onChange={(e) => setMinutes(Number(e.target.value))}
            />
          </label>
          <label className="block text-sm">
            Corrections, intervention and outcome
            <textarea
              className={input}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <button
            className={button}
            disabled={busy || !selected}
            onClick={() =>
              void act('review', { ...selectedFields, useful, minutes, note })
            }
          >
            Record review
          </button>
        </section>
      )}
      {tab === 'Connections & pilot' && (
        <div className="space-y-5">
          <section className={panel}>
            <h2 className="text-lg font-semibold">
              Wabi → WhatsApp → Unipile → Chris
            </h2>
            <p className="text-sm">
              Obtain and retain your Wabi number, register its WhatsApp account,
              then link that account to Unipile. Verify Chris’s identity and a
              controlled round-trip before approaching prospects.
            </p>
            <p className="text-sm">
              The experiment starts with controlled participants, then a
              proposed first wave of 5 qualified prospects and up to 20 total
              after review. Provider configuration alone is not live acceptance.
            </p>
            <button
              className={button}
              disabled={busy || !report}
              onClick={() => void act('readiness')}
            >
              Check readiness
            </button>
            <Link className="ml-3 text-sm underline" href="/contacts">
              CRM contacts
            </Link>
            <dl className="grid gap-3 sm:grid-cols-2">
              {Object.entries(report?.readiness ?? {}).map(([key, value]) => (
                <div key={key} className="rounded-md border p-3">
                  <dt className="text-muted-foreground text-xs">
                    {key.replaceAll('_', ' ')}
                  </dt>
                  <dd className="text-sm break-words">{display(value)}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className={panel}>
            <h2 className="text-lg font-semibold">Pilot measures</h2>
            <dl className="grid gap-3 sm:grid-cols-3">
              {Object.entries(report?.metrics ?? {}).map(([key, value]) => (
                <div key={key}>
                  <dt className="text-muted-foreground text-xs">
                    {key.replaceAll('_', ' ')}
                  </dt>
                  <dd className="text-lg">{display(value)}</dd>
                </div>
              ))}
            </dl>
            <p className="text-muted-foreground text-sm">
              Compare your manual baseline with total supervision time and cost.
              Distinguish delivery failures from poor fit or conversation
              quality.
            </p>
          </section>
          <section className={panel}>
            <h2 className="text-lg font-semibold">Work and evidence</h2>
            <details>
              <summary className="cursor-pointer text-sm">
                Queued work ({report?.jobs?.length ?? 0})
              </summary>
              <pre className="overflow-auto text-xs whitespace-pre-wrap">
                {JSON.stringify(report?.jobs, null, 2)}
              </pre>
            </details>
            <details>
              <summary className="cursor-pointer text-sm">
                Execution evidence
              </summary>
              <pre className="overflow-auto text-xs whitespace-pre-wrap">
                {JSON.stringify(report?.events, null, 2)}
              </pre>
            </details>
          </section>
        </div>
      )}
      {tab === 'Connections & pilot' &&
        report?.jobs.some((job) =>
          ['failed', 'cancelled'].includes(String(job.state))
        ) && (
          <section className={panel}>
            <h3 className="font-semibold">Work needing attention</h3>
            <p className="text-sm">
              Resolve the reported issue first. Retrying does not bypass budget
              or stale-context checks.
            </p>
            {report.jobs
              .filter((job) =>
                ['failed', 'cancelled'].includes(String(job.state))
              )
              .map((job) => (
                <div
                  key={String(job.id)}
                  className="flex flex-wrap items-center gap-3"
                >
                  <span className="text-sm">
                    {String(job.kind)} · {String(job.error || job.state)}
                  </span>
                  <button
                    className={button}
                    disabled={busy}
                    onClick={() => void act('retry_job', { job_id: job.id })}
                  >
                    Retry work
                  </button>
                </div>
              ))}
          </section>
        )}
    </main>
  );
}
