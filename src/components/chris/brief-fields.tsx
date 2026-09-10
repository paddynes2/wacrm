'use client';
import { object, type Row } from '@/lib/chris/contracts';

export function BriefFields({ value, onChange, proposal, apply }: { value: Row; onChange: (value: Row) => void; proposal: unknown; apply: (value: Row) => void }) {
  const suggested = object(proposal) && object(proposal.suggested_brief) ? proposal.suggested_brief : null;
  const labels: Record<string,string> = { candidate_archetypes: 'People who could help', geography_include: 'Included regions (blank means global)', geography_exclude: 'Excluded regions', explicit_exclusions: 'People or organisations to exclude', confidentiality_rules: 'Information Chris must keep private' };
  return <div className="space-y-3">
    {suggested && <div className="rounded-lg bg-blue-50 p-3 text-sm"><p className="font-medium">Chris has proposed a structured brief.</p><p className="my-2">{String(suggested.objective)}</p><button className="rounded-lg border bg-white px-3 py-2" onClick={() => apply(suggested)}>Use this suggestion in the editable fields</button></div>}
    <details className="rounded-lg border p-3"><summary className="cursor-pointer text-sm font-medium">People, geography and exclusions</summary>
      <p className="my-3 text-xs text-slate-500">Optional, one item per line. Unknown geography stays global. These fields are reviewed with the endeavour before research starts.</p>
      {Object.entries(labels).map(([key,label]) => <label key={key} className="my-3 block text-sm">{label}<textarea className="mt-1 w-full rounded-lg border border-slate-300 p-2" rows={2} value={Array.isArray(value[key]) ? (value[key] as string[]).join('\n') : ''} onChange={e => onChange({ ...value, [key]: e.target.value.split('\n').filter(Boolean) })} /></label>)}
    </details>
  </div>;
}
