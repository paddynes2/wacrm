'use client';
import { useState } from 'react';
import { useAuth } from '@/hooks/use-auth';
import { object, type Row } from '@/lib/chris/contracts';

const field = 'mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm';
const button = 'rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-40';

export function EvidenceControls({ detail, invoke, busy }: { detail: Row; invoke: (name: string, payload: Row) => void; busy: boolean }) {
  const { accountRole } = useAuth();
  const [phone, setPhone] = useState(''), [source, setSource] = useState(''), [attestation, setAttestation] = useState('');
  const [scope, setScope] = useState(''), [granted, setGranted] = useState(''), [date, setDate] = useState('');
  const pursuit = object(detail.pursuit) ? detail.pursuit : null;
  const thread = object(detail.thread) ? detail.thread : null;
  if (!pursuit) return null;
  return <section className="space-y-4 border-t pt-5">
    <h3 className="font-semibold">Contact evidence and control</h3>
    <p className="text-sm text-slate-500">A public number is not permission to contact someone. Record the actual source and scope of their permission. Chris still verifies the WhatsApp identity separately.</p>
    {accountRole === 'owner' && <details className="rounded-lg border p-4"><summary className="cursor-pointer font-medium">Record identity and permission evidence</summary>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="text-sm">International phone number<input value={phone} onChange={e => setPhone(e.target.value)} placeholder="+…" className={field} /></label>
        <label className="text-sm">Evidence source reference<input value={source} onChange={e => setSource(e.target.value)} className={field} /></label>
        <label className="text-sm sm:col-span-2">What you verified<textarea value={attestation} onChange={e => setAttestation(e.target.value)} className={field} /></label>
        <button className={button} disabled={busy || !phone || !source || !attestation} onClick={() => invoke('person.identity_attest', { person_id: detail.person_id, phone_e164: phone, evidence_refs: [source], attestation_text: attestation })}>Record identity evidence</button>
        <label className="text-sm sm:col-span-2">Exact contact permission scope<textarea value={scope} onChange={e => setScope(e.target.value)} className={field} /></label>
        <label className="text-sm">When permission was granted<input type="datetime-local" value={granted} onChange={e => setGranted(e.target.value)} className={field} /></label>
        <button className={button} disabled={busy || !source || !scope || !granted || !attestation || !detail.business_sender_identity} onClick={() => invoke('permission.record', { person_id: detail.person_id, kind: 'contact', source_ref: source, scope_text: scope, granted_at: new Date(granted).toISOString(), business_sender_identity: detail.business_sender_identity, attestation_text: attestation })}>Record contact permission</button>
      </div>
    </details>}
    {Array.isArray(detail.permissions) && detail.permissions.filter(object).map(p => <div className="flex flex-wrap items-center gap-3 text-sm" key={String(p.permission_id)}><span>{String(p.kind)} permission: {String(p.status)}</span>{p.status === 'valid' && <button disabled={busy} className={button} onClick={() => invoke('permission.revoke', { permission_id: p.permission_id, reason: 'Revoked in console' })}>Revoke permission</button>}</div>)}
    {pursuit.human_takeover === true && accountRole === 'owner' && <button disabled={busy || !thread?.history_ready} className={button} onClick={() => invoke('pursuit.resume', { pursuit_id: pursuit.pursuit_id, reviewed_thread_watermark: thread?.last_observed_seq })}>Resume after reviewing this conversation</button>}
    <label className="block text-sm">Defer until<input type="datetime-local" value={date} onChange={e => setDate(e.target.value)} className={field} /></label>
    <button className={button} disabled={busy || !date} onClick={() => invoke('person.defer', { person_id: detail.person_id, not_before: new Date(date).toISOString(), reason: 'Deferred in console' })}>Defer this person</button>
    {accountRole === 'owner' && Array.isArray(detail.actions) && detail.actions.filter(object).filter(a => a.status === 'draft').map(a => <button key={String(a.action_id)} disabled={busy} className={button} onClick={() => invoke('message.approve', { action_id: a.action_id, displayed_digest: a.digest })}>Approve the displayed reply draft</button>)}
  </section>;
}
