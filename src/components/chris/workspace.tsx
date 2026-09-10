'use client';

import Link from 'next/link';
import { DossierEvidence } from './dossier-evidence';
import { BriefFields } from './brief-fields';
import { useAuth } from '@/hooks/use-auth';
import { BudgetControls } from './budget-controls';
import { GroupThread } from './group-thread';
import { EvidenceControls } from './evidence-controls';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Check, ChevronRight, Pause, RefreshCw, Search, Send, Users } from 'lucide-react';
import { assert, object, type Row } from '@/lib/chris/contracts';
import { overview, label, safeSource, type Overview } from '@/lib/chris/view';
import { acceptRead } from '@/lib/chris/read-fence';

type Section = 'home' | 'people' | 'introductions' | 'settings';
const button = 'inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:opacity-40';
const secondary = 'inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-blue-600 disabled:opacity-40';
const input = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 focus:outline-2 focus:outline-blue-600';

export function ChrisWorkspace({ section = 'home', entityId }: { section?: Section; entityId?: string }) {
  const { accountId } = useAuth();
  const accountRef = useRef(accountId); accountRef.current = accountId;
  const [report, setReport] = useState<Overview | null>(null);
  const [items, setItems] = useState<Row[]>([]), [detail, setDetail] = useState<Row | null>(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [notice, setNotice] = useState('');
  const [text, setText] = useState(''), [name, setName] = useState(''), [context, setContext] = useState('');
  const [timezone, setTimezone] = useState(''), [proposal, setProposal] = useState<string | null>(null);
  const [challenge, setChallenge] = useState(''), [cursor, setCursor] = useState<string | null>(null);
  const [pageCount, setPageCount] = useState(1);
  const [listLoading, setListLoading] = useState(true);
  const [briefExtras, setBriefExtras] = useState<Row>({});
  const revision = useRef(-1), alive = useRef(true), expired = useRef(false);
  const reportRef = useRef(report);
  useEffect(() => { reportRef.current = report; }, [report]);
  useEffect(() => { setDetail(null); setItems([]); setCursor(null); setListLoading(true); setPageCount(1); },[entityId,section,accountId]);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const requestedAccount = accountRef.current;
    const response = await fetch('/api/chris', { signal, cache: 'no-store' });
    if (requestedAccount !== accountRef.current || signal?.aborted) return;
    if (response.status === 401) { expired.current = true; throw new Error('Your session expired. Sign in again; your draft is still here.'); }
    const raw: unknown = await response.json();
    if (!response.ok) throw new Error('Chris is not connected. Your host can connect the private service. Your draft is safe here.');
    const next = overview(raw);
    if (acceptRead(requestedAccount, accountRef.current, Boolean(signal?.aborted), alive.current, next.revision, revision.current)) { revision.current = next.revision; reportRef.current = next; setReport(next); setError(''); }
  }, []);
  useEffect(() => {
    alive.current = true; expired.current = false; revision.current = -1;
    setBusy(false);
    setReport(null); reportRef.current = null; setItems([]); setDetail(null); setText(''); setName(''); setContext(''); setTimezone(''); setBriefExtras({}); setPageCount(1); setProposal(null); setChallenge(''); setNotice(''); setError('');
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>; let failures = 0;
    async function poll() {
      try { await refresh(controller.signal); failures = 0; }
      catch (e) { if (!controller.signal.aborted) { failures++; setError(e instanceof TypeError ? 'Connection interrupted. Your draft is preserved; refresh when you are back online.' : e instanceof Error ? e.message : 'Connection interrupted.'); } }
      if (!controller.signal.aborted && !expired.current) timer = setTimeout(poll, Math.min(60000, (document.hidden ? 15000 : 5000) * 2 ** failures));
    }
    void poll();
    return () => { alive.current = false; controller.abort(); clearTimeout(timer); };
  }, [refresh, accountId]);
  useEffect(() => {
    if (!['people', 'introductions'].includes(section)) return;
    const controller = new AbortController();
    setListLoading(true);
    async function readPages() {
      const accumulated: Row[] = []; let nextCursor: string | null = null;
      for (let page = 0; page < (entityId ? 1 : pageCount); page++) {
        const path = `/api/chris/${section}${entityId ? '/' + entityId : nextCursor ? '?cursor=' + encodeURIComponent(nextCursor) : ''}`;
        const response = await fetch(path, { signal: controller.signal, cache: 'no-store' });
        const body: unknown = await response.json(); if (controller.signal.aborted) return; assert(response.ok && object(body));
        if (entityId) { assert(object(body.item)); setDetail(body.item); return; }
        assert(Array.isArray(body.items) && body.items.every(object)); accumulated.push(...body.items);
        nextCursor = typeof body.next_cursor === 'string' ? body.next_cursor : null;
        if (!nextCursor) break;
      }
      setItems(accumulated); setCursor(nextCursor);
    }
    void readPages().catch(() => { if (!controller.signal.aborted) setError('This view could not be loaded. Refresh to check its current state.'); }).finally(() => { if (!controller.signal.aborted) setListLoading(false); });
    return () => controller.abort();
  }, [section, entityId, report?.revision, accountId, pageCount]);

  async function command(commandName: string, payload: Row, overrideRevision?: number) {
    const requestedAccount = accountRef.current;
    const current = () => requestedAccount === accountRef.current && alive.current;
    setBusy(true); setNotice('');
    const commandId = crypto.randomUUID();
    const envelope = { schema_version: 1, command_id: commandId, expected_revision: overrideRevision ?? reportRef.current?.revision ?? 0, command: commandName, payload };
    try {
      let response: Response;
      try { response = await fetch('/api/chris/commands', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(envelope) }); }
      catch {
        assert(current(), 'Account changed; check the original account for the command outcome.');
        const status = await fetch('/api/chris/commands/' + commandId, { cache: 'no-store' });
        const known: unknown = await status.json();
        assert(status.ok && object(known) && object(known.item) && object(known.item.result), 'Command outcome unknown. Check status before trying again.');
        assert(current()); await refresh(); assert(current()); return known.item.result;
      }
      const result: unknown = await response.json(); assert(object(result));
      assert(current(), 'Account changed; check the original account for the command outcome.');
      if (!response.ok) { await refresh(); throw new Error(response.status === 409 ? 'The workspace changed. Your draft is preserved. Review the latest state before saving again.' : object(result.error) ? String(result.error.message) : 'The action was not accepted.'); }
      await refresh(); assert(current()); setNotice('Saved. Chris will continue within the current permissions.'); return result;
    } catch (e) { if (current()) setError(e instanceof TypeError ? 'Connection interrupted. The command outcome needs checking before you try again. Your draft is preserved.' : e instanceof Error ? e.message : 'Unable to save.'); throw e; }
    finally { if (current()) setBusy(false); }
  }
  const invoke = (name: string, payload: Row) => { void command(name, payload).catch(() => undefined); };
  async function activate() {
    if (!proposal) return;
    const saved = await command('brief.save_proposal', { proposal_id: proposal, brief: { ...briefExtras, objective: text, principal_display_name: name, principal_public_context: context, timezone } });
    await command('brief.activate', { proposal_id: proposal }, Number(saved.revision)); setProposal(null);
  }
  async function loadMore() {
    setPageCount(count => count + 1);
  }

  const heading = section === 'home' ? 'Good connections start with a clear purpose.' : section === 'people' ? 'People with a reason to connect.' : section === 'introductions' ? 'Introductions, with the full story.' : 'Make Chris work on your terms.';
  return <div className="min-h-full bg-[#f7f8fa] p-4 text-slate-900 sm:p-8 lg:p-10">
    <div className="mx-auto max-w-6xl space-y-7">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <Link href="/chris" className="flex items-center gap-3 text-xl font-semibold tracking-tight"><span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-700 text-white">c</span>Chris<span className="hidden text-xs font-normal text-slate-500 sm:inline">Your commercial connector</span></Link>
        <nav aria-label="Chris" className="flex flex-wrap gap-1">{(['home', 'people', 'introductions', 'settings'] as Section[]).map(s => <Link key={s} aria-current={section === s ? 'page' : undefined} href={s === 'home' ? '/chris' : '/chris/' + s} className={`rounded-lg px-3 py-2 text-sm ${s === section ? 'bg-white font-semibold shadow-sm' : 'text-slate-500 hover:text-slate-900'}`}>{s === 'home' ? 'Chris' : s[0].toUpperCase() + s.slice(1)}</Link>)}</nav>
      </header>
      {report?.mode === 'simulation' && <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">Simulation · Synthetic people and provider responses. No live messages.</div>}
      <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-blue-700">{section === 'home' ? 'Your endeavour' : section}</p><h1 className="max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">{heading}</h1></div>{report && <button className={secondary} disabled={busy} onClick={() => invoke(report.authority.paused ? 'workspace.resume' : 'workspace.pause', report.authority.paused ? {} : { reason: 'Paused in console' })}><Pause size={15} />{report.authority.paused ? 'Resume work' : 'Pause Chris'}</button>}</div>
      {error && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900"><span>{error}</span><button className={secondary} onClick={() => void refresh().catch(() => undefined)}><RefreshCw size={14} />Refresh status</button></div>}
      {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}
      {!report && !error && <p role="status">Loading your workspace…</p>}
      {report && <div className="flex flex-wrap gap-3 text-xs text-slate-600"><span className="rounded-full border bg-white px-3 py-1.5">{report.authority.paused ? 'Paused' : report.authority.external_enabled ? 'Eligible messaging enabled' : 'Messaging off'}</span><span className="rounded-full border bg-white px-3 py-1.5">{object(report.readiness.research) && report.readiness.research.configured ? 'Research connected' : 'Research setup needed'}</span><span className="rounded-full border bg-white px-3 py-1.5">{object(report.readiness.worker) && report.readiness.worker.running ? 'Worker active' : 'Worker unavailable'}</span></div>}
      {report && object(report.readiness.projection) && Number(report.readiness.projection.pending) > 0 && <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{String(report.readiness.projection.pending)} CRM updates are waiting for sync. Verified WhatsApp outcomes remain recorded; projection repair will not resend messages.</p>}
      {report && object(report.readiness.storage) && report.readiness.storage.discovery_paused === true && <p role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">Storage needs attention. New discovery is paused so Chris can preserve messages, withdrawals and receipts. Export the account and ask your host to review capacity.</p>}
      {section === 'home' && <>
        {report?.brief && <section className="rounded-2xl border border-blue-100 bg-blue-50/60 p-6"><p className="text-xs font-medium text-blue-700">CURRENT ENDEAVOUR</p><h2 className="mt-2 text-xl font-medium">{String(report.brief.objective)}</h2><p className="mt-2 text-sm text-slate-500">Working for {String(report.brief.principal_display_name)} · {String(report.brief.timezone)} · Unspecified geography stays global</p></section>}
        {report && <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{Object.entries(report.counts).map(([key, count]) => <div key={key} className="rounded-xl border border-slate-200 bg-white p-5"><p className="text-3xl font-semibold tabular-nums">{count}</p><p className="mt-2 text-sm capitalize text-slate-500">{label(key)}</p></div>)}</div>}
        <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]"><section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6"><h2 className="text-lg font-semibold">Talk to Chris</h2><p className="mt-1 text-sm leading-relaxed text-slate-500">Tell Chris what you are trying to achieve. He researches useful people and helps make an agreed three-person WhatsApp introduction.</p><div aria-live="polite" className="my-5 max-h-80 space-y-3 overflow-y-auto">{report?.chat.map((message, i) => <div key={i} className={`rounded-xl p-3 text-sm leading-relaxed ${message.role === 'principal' ? 'ml-8 bg-blue-50' : 'mr-4 bg-slate-50'}`}><p className="mb-1 text-xs font-semibold">{message.role === 'principal' ? 'You' : 'Chris'}</p>{String(message.text)}</div>)}</div><label htmlFor="endeavour" className="mb-2 block text-sm font-medium">Your endeavour or question</label><textarea id="endeavour" value={text} onChange={e => setText(e.target.value)} rows={4} maxLength={4000} className={input} placeholder="I’m looking for distribution partners for…" /><div className="mt-3 flex justify-end"><button disabled={busy || !report || !text.trim()} className={button} onClick={() => void command('brief.propose', { text }).then(r => { if (typeof r.proposal_id === 'string') setProposal(r.proposal_id); }).catch(() => undefined)}>Send to Chris <Send size={15} /></button></div>
          {proposal && <div className="mt-5 space-y-4 border-t pt-5"><h3 className="font-semibold">Review before starting research</h3><BriefFields value={briefExtras} onChange={setBriefExtras} proposal={report?.proposals[proposal]} apply={suggestion => { setText(String(suggestion.objective ?? '')); setName(String(suggestion.principal_display_name ?? '')); setContext(String(suggestion.principal_public_context ?? '')); setTimezone(String(suggestion.timezone ?? '')); setBriefExtras(Object.fromEntries(Object.entries(suggestion).filter(([key]) => !['objective','principal_display_name','principal_public_context','timezone'].includes(key)))); }} /><label className="block text-sm">Your public name<input className={input + ' mt-1'} value={name} onChange={e => setName(e.target.value)} maxLength={120} /></label><label className="block text-sm">Public background<textarea className={input + ' mt-1'} value={context} onChange={e => setContext(e.target.value)} rows={3} /></label><label className="block text-sm">Operating timezone<input className={input + ' mt-1'} placeholder="Europe/London" value={timezone} onChange={e => setTimezone(e.target.value)} /></label><button className={secondary} onClick={() => setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone)}>Use this browser’s timezone</button><p className="text-xs text-slate-500">Starting research covers routine candidate selection. Messaging remains a separate setting.</p><button disabled={busy || !name || !timezone} className={button} onClick={() => void activate().catch(() => undefined)}>Start research <ArrowUpRight size={15} /></button></div>}
        </section><section className="rounded-2xl border border-slate-200 bg-white p-6"><h2 className="text-lg font-semibold">What’s happening</h2><p className="mt-1 text-sm text-slate-500">Recorded progress, including what still needs attention.</p><ol className="mt-6 space-y-5">{report?.activity.slice(-8).reverse().map((item, i) => <li key={String(item.event_id ?? i)} className="flex gap-3"><span className="mt-1 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-blue-50 text-blue-700"><Check size={12} /></span><div><p className="text-sm capitalize">{label(item.kind)}</p><p className="text-xs text-slate-400" title={typeof item.occurred_at === 'number' ? new Date(item.occurred_at * 1000).toISOString() : undefined}>{typeof item.occurred_at === 'number' ? new Date(item.occurred_at * 1000).toLocaleString(undefined, { timeZone: String(report?.settings.timezone ?? 'UTC') }) : ''}</p></div></li>)}</ol>{!report?.activity.length && <div className="py-12 text-center"><Search className="mx-auto mb-3 text-slate-300" size={30} /><p className="text-sm text-slate-500">A clear endeavour is the first step.<br />Your activity will appear here.</p></div>}</section></div>
      </>}
      {['people', 'introductions'].includes(section) && !entityId && <section className="space-y-3">{listLoading && items.length === 0 && <p role="status">Loading the latest records...</p>}{!listLoading && !error && items.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center"><Users className="mx-auto mb-4 text-slate-300" size={36} /><h2 className="font-semibold">{section === 'people' ? 'No people researched yet' : 'No introductions yet'}</h2><p className="mx-auto mt-2 max-w-md text-sm text-slate-500">{section === 'people' ? 'Activate an endeavour to begin. Missing WhatsApp setup does not stop configured research.' : 'An introduction appears here as complete only after the intended group and substantive message are verified.'}</p></div>}{items.map(item => { const pursuit = object(item.pursuit) ? item.pursuit : item; return <Link className="flex min-w-0 items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-5 hover:border-blue-300" key={String(item.person_id ?? item.intro_id)} href={`/chris/${section}/${item.person_id ?? item.intro_id}`}><div className="min-w-0"><h2 className="break-words font-semibold">{String(item.display_name ?? item.subject ?? 'Introduction')}</h2><p className="mt-1 break-words text-sm text-slate-500">{String(item.company_name ?? pursuit.rank_rationale ?? '')}</p><p className="mt-2 text-xs capitalize text-blue-700">{label(pursuit.state)}{pursuit.attention ? ' · ' + label(pursuit.attention) : ''}</p></div><ChevronRight className="shrink-0 text-slate-400" size={18} /></Link>; })}{cursor && <button className={secondary} onClick={() => void loadMore().catch(() => setError('Could not load more.'))}>Load more</button>}</section>}
      {entityId && !detail && !error && <p role="status">Loading the latest evidence?</p>}{detail && entityId && <EntityDetail detail={detail} invoke={invoke} busy={busy} />}
      {section === 'settings' && report && <div className="grid gap-5 md:grid-cols-2"><section className="space-y-4 rounded-2xl border bg-white p-6"><h2 className="text-lg font-semibold">WhatsApp identities</h2><p className="text-sm leading-relaxed text-slate-500">Chris needs his own connected WhatsApp number, separate from yours. Your host supplies the provider connection. Registration and linking happen through that provider.</p><p className="text-sm">{object(report.readiness.whatsapp) && report.readiness.whatsapp.connected ? 'Chris is connected.' : 'Chris’s WhatsApp connection needs setup.'}</p><button className={secondary} disabled={busy} onClick={() => invoke('connection.refresh', {})}>Check connection</button><hr /><h3 className="font-medium">Prove your separate number</h3><p className="text-sm text-slate-500">Generate a code, then send it from your number directly to Chris. The code lasts ten minutes and can be used once.</p><button className={secondary} disabled={busy} onClick={() => void command('principal.challenge', {}).then(r => setChallenge(String(r.challenge ?? 'Generate a new code if the first response was lost.'))).catch(() => undefined)}>Generate control code</button>{challenge && <p className="break-all rounded-lg bg-blue-50 p-3 font-mono text-sm">{challenge}</p>}</section><section className="space-y-4 rounded-2xl border bg-white p-6"><h2 className="text-lg font-semibold">Authority and limits</h2><p className="text-sm leading-relaxed text-slate-500">Future eligible invitations, replies and three-person introductions can proceed within your mandate. Contact permission, identity, current consent and provider checks still apply. Existing drafts will not be released.</p><p className="text-sm">Research allowance: ${Number(report.settings.daily_micro_usd) / 1000000} per day · up to {String(report.settings.daily_operations)} paid operations.</p><button className={secondary} disabled={busy} onClick={() => invoke('settings.update', { research_enabled: !report.settings.research_enabled })}>{report.settings.research_enabled ? 'Pause research' : 'Enable research'}</button><button className={button} disabled={busy} onClick={() => invoke('autonomy.set', { enabled: !report.authority.external_enabled, displayed_authority_revision: report.authority.revision, scope_kinds: ['invite', 'reply', 'permission_clarification', 'followup', 'group_create', 'group_introduction', 'principal_reply'] })}>{report.authority.external_enabled ? 'Turn messaging off' : 'Enable future eligible messaging'}</button><p className="text-xs text-slate-500">Only the account owner can enable messaging. In-flight requests may still be awaiting observation after you pause.</p><BudgetControls settings={report.settings} busy={busy} invoke={invoke} /><hr /><Link className={secondary} href="/api/chris/export">Export account evidence</Link><Link className="ml-3 text-sm underline" href="/dogfood">Advanced simulator</Link></section></div>}
    </div>
  </div>;
}

function EntityDetail({ detail, invoke, busy }: { detail: Row; invoke: (name: string, payload: Row) => void; busy: boolean }) {
  const [draft, setDraft] = useState('');
  const pursuit = object(detail.pursuit) ? detail.pursuit : null;
  const dossier = object(detail.dossier) ? detail.dossier : null;
  const thread = object(detail.thread) ? detail.thread : null;
  return <article className="space-y-5 rounded-2xl border bg-white p-5 sm:p-7"><h2 className="break-words text-2xl font-semibold">{String(detail.display_name ?? detail.subject)}</h2><p className="text-sm capitalize text-blue-700">{label(pursuit?.state ?? detail.state)}</p>{pursuit?.attention && pursuit.state !== 'introduced' ? <p role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{label(pursuit.attention)}. Group permission is not inferred from an unclear answer.</p> : null}{dossier && <><h3 className="font-semibold">Why this person</h3><p className="whitespace-pre-wrap text-sm leading-relaxed">{String(dossier.why_this_person)}</p><h3 className="font-semibold">Evidence and gaps</h3><DossierEvidence dossier={dossier} sources={detail.sources} />{Array.isArray(dossier.unknowns) && dossier.unknowns.map((gap, i) => <p key={i} className="text-sm text-amber-800">Unresolved: {String(gap)}</p>)}</>}{Array.isArray(detail.canonical_profile_urls) && detail.canonical_profile_urls.map((url, i) => safeSource(url) && <a key={i} href={safeSource(url)} target="_blank" rel="noopener noreferrer" className="block break-all text-sm text-blue-700 underline">{String(url)}</a>)}{!detail.intro_id && <p className="text-xs text-slate-500">Relationship check: {String(detail.relationship_coverage ?? 'Not yet checked')}</p>}{Boolean(detail.intro_id) && <section className="space-y-3 rounded-lg bg-blue-50 p-4 text-sm"><h3 className="font-semibold">The intended three-person introduction</h3><p>Chris &middot; {String(detail.principal_display_name ?? 'Principal')} &middot; {String(detail.prospect_display_name ?? 'Prospect')}</p><p>{detail.state === 'introduced' ? 'Group membership and the substantive introduction were independently observed.' : detail.state === 'membership_pending' ? 'Chris is checking that both people joined. The substantive introduction has not been sent.' : detail.state === 'membership_failed' ? 'The group membership could not be verified. Chris will not create a replacement group or add people automatically.' : 'This introduction is still in progress. A group alone is not a completed introduction.'}</p>{detail.last_failure && detail.state !== 'introduced' ? <p role="status">Needs attention: {label(detail.last_failure)}</p> : null}</section>}{thread && object(thread.messages) && <section className="space-y-3"><h3 className="font-semibold">Conversation</h3>{Object.values(thread.messages).filter(object).map((row, i) => object(row.message) && <div key={i} className="rounded-lg bg-slate-50 p-3 text-sm"><strong>{row.message.outbound ? 'Chris’s account' : String(detail.display_name)}</strong><p className="whitespace-pre-wrap break-words">{String(row.message.text ?? 'Unsupported message')}</p></div>)}</section>}{Array.isArray(detail.actions) && detail.actions.filter(object).map(action => <div className="rounded-lg border p-3 text-sm" key={String(action.action_id)}><p className="capitalize">{label(action.kind)} · {label(action.status)}</p>{object(action.frozen) && <p className="mt-2 whitespace-pre-wrap break-words">{String(action.frozen.text)}</p>}{['unknown', 'needs_attention', 'provider_accepted', 'started'].includes(String(action.status)) && <button className={secondary + ' mt-3'} disabled={busy} onClick={() => invoke('action.reconcile', { action_id: action.action_id })}>Check whether this happened</button>}</div>)}{pursuit && <><label className="block text-sm font-medium">Draft a reply<textarea value={draft} onChange={e => setDraft(e.target.value)} className={input + ' mt-2'} rows={3} /></label><div className="flex flex-wrap gap-3"><button className={button} disabled={busy || !draft} onClick={() => invoke('message.draft', { pursuit_id: pursuit.pursuit_id, text: draft })}>Save reply draft</button><button className={secondary} disabled={busy} onClick={() => invoke('pursuit.takeover', { pursuit_id: pursuit.pursuit_id, reason: 'Taking over in console' })}>Take over</button><button className={secondary} disabled={busy} onClick={() => invoke('person.exclude', { person_id: detail.person_id, reason: 'Excluded in console' })}>Exclude person</button></div></>}<GroupThread detail={detail} /><EvidenceControls detail={detail} invoke={invoke} busy={busy} />{detail.state === 'introduced' && <p className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-800">Substantive introduction observed in the intended group. This does not assert that both people read it.</p>}</article>;
}
