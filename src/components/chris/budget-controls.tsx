'use client';
import { useState } from 'react';
import { useAuth } from '@/hooks/use-auth';
import type { Row } from '@/lib/chris/contracts';

export function BudgetControls({ settings, busy, invoke }: { settings: Row; busy: boolean; invoke: (name: string, payload: Row) => void }) {
  const { accountRole } = useAuth();
  const [daily, setDaily] = useState(String(Number(settings.daily_micro_usd) / 1000000));
  const [operations, setOperations] = useState(String(settings.daily_operations));
  const [invites, setInvites] = useState(String(settings.daily_invites));
  if (accountRole !== 'owner') return null;
  const valid = Number(daily) >= 0 && Number(daily) <= Number(settings.daily_micro_usd)/1000000 && Number.isInteger(Number(operations)) && Number(operations) >= 0 && Number(operations) <= Number(settings.daily_operations) && Number.isInteger(Number(invites)) && Number(invites) >= 0 && Number(invites) <= Number(settings.daily_invites);
  return <details className="space-y-3 rounded-lg border p-3"><summary className="cursor-pointer text-sm font-medium">Working limits and replies to you</summary>
    <p className="text-xs text-slate-500">These are ceilings, not targets. Raising the host allowance is a separate host operation.</p>
    <label className="block text-sm">Research dollars per day<input className="mt-1 w-full rounded border p-2" type="number" min="0" step="0.01" value={daily} onChange={e => setDaily(e.target.value)} /></label>
    <label className="block text-sm">Paid operations per day<input className="mt-1 w-full rounded border p-2" type="number" min="0" value={operations} onChange={e => setOperations(e.target.value)} /></label>
    <label className="block text-sm">New invitations per day<input className="mt-1 w-full rounded border p-2" type="number" min="0" value={invites} onChange={e => setInvites(e.target.value)} /></label>
    <button className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40" disabled={busy || !valid} onClick={() => invoke('settings.update', { daily_micro_usd: Math.round(Number(daily)*1000000), daily_operations: Number(operations), daily_invites: Number(invites) })}>Save lower limits</button>
    <p className="text-xs text-slate-500">Replies to your verified number also require future messaging authority. They cannot enable sending to prospects.</p>
    <button className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40" disabled={busy} onClick={() => invoke('settings.update', { principal_messages_enabled: !settings.principal_messages_enabled })}>{settings.principal_messages_enabled ? 'Turn status replies to me off' : 'Allow status replies to my number'}</button>
  </details>;
}
