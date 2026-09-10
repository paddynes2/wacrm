import { object, type Row } from '@/lib/chris/contracts';

export function GroupThread({ detail }: { detail: Row }) {
  if (!Array.isArray(detail.threads)) return null;
  const names = new Map<string, string>();
  if (Array.isArray(detail.expected_participants)) {
    names.set(String(detail.expected_participants[0]), 'Chris');
    names.set(String(detail.expected_participants[1]), String(detail.principal_display_name));
    names.set(String(detail.expected_participants[2]), String(detail.prospect_display_name));
  }
  return <section className="space-y-3"><h3 className="font-semibold">Group conversation</h3>
    {detail.threads.length === 0 && <p className="text-sm text-slate-500">The group transcript has not yet been observed. Verified action receipts are shown separately below.</p>}
    {detail.threads.filter(object).flatMap(t => object(t.messages) ? Object.values(t.messages).filter(object) : []).map(row => object(row.message) && <div key={String(row.event_id)} className="rounded-lg bg-slate-50 p-3 text-sm"><strong>{names.get(String(row.message.sender_id)) ?? 'Unverified participant'}</strong><p className="whitespace-pre-wrap break-words">{String(row.message.text || 'Non-text event')}</p></div>)}
  </section>;
}
