import { object, type Row } from '@/lib/chris/contracts';
import { safeSource } from '@/lib/chris/view';

export function DossierEvidence({ dossier, sources }: { dossier: Row; sources: unknown }) {
  const rows = object(sources) ? sources : {};
  return <div className="space-y-3">{Array.isArray(dossier.facts) && dossier.facts.filter(object).map((fact,i) => <div key={i} className="text-sm text-slate-600"><p>{String(fact.text)}</p><div className="mt-1 flex flex-wrap gap-3">{Array.isArray(fact.source_ids) && fact.source_ids.map(id => {
    const source=rows[String(id)]; if (!object(source)) return null; const url=safeSource(source.url); if (!url) return null;
    return <a key={String(id)} href={url} target="_blank" rel="noopener noreferrer" className="break-words text-blue-700 underline" title={String(source.published_at ?? 'Publication date not supplied')}>{String(source.title || 'Retained source')}{source.published_at ? ' · '+String(source.published_at) : ''}</a>;
  })}</div></div>)}{Array.isArray(dossier.inferences) && dossier.inferences.map((inference,i) => <p key={i} className="text-sm text-slate-500">Inference: {String(inference)}</p>)}</div>;
}
