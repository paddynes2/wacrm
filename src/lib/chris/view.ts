import { assert, object, type Row } from './contracts';

export type Overview = {
  schema_version: 1; revision: number; mode: 'simulation' | 'live'; brief: Row | null;
  counts: { researching: number; approached: number; awaiting_reply: number; introduced: number };
  authority: Row; settings: Row; readiness: Row; proposals: Row;
  activity: Row[]; chat: Row[];
};
export function overview(v: unknown): Overview {
  assert(object(v) && v.schema_version === 1 && Number.isSafeInteger(v.revision), 'invalid_service_response', 502);
  assert(v.mode === 'simulation' || v.mode === 'live');
  for (const key of ['counts', 'authority', 'settings', 'readiness', 'proposals']) assert(object(v[key]));
  assert(object(v.counts));
  for (const key of ['researching', 'approached', 'awaiting_reply', 'introduced']) assert(Number.isSafeInteger(v.counts[key]) && Number(v.counts[key]) >= 0);
  assert(Array.isArray(v.activity) && v.activity.every(object) && Array.isArray(v.chat) && v.chat.every(object));
  assert(v.brief === null || object(v.brief));
  return v as Overview;
}
const eventLabels: Record<string, string> = { 'brief.propose': 'Endeavour proposed', 'brief.save_proposal': 'Endeavour reviewed', 'brief.activate': 'Research mandate activated', action_started: 'Message submission started', action_verified: 'Message observed', introduction_completed: 'Introduction verified', person_registered: 'Person discovered', discovery_search: 'Public search completed', source_read: 'Source read', qualification: 'Relevance assessed', dossier_written: 'Research retained', 'workspace.pause': 'Chris paused', 'workspace.resume': 'Chris resumed', 'autonomy.set': 'Messaging setting updated' };
export const label = (v: unknown) => typeof v === 'string' ? eventLabels[v] ?? v.replaceAll('_', ' ').replaceAll('.', ' ') : '';
export function safeSource(v: unknown): string | undefined {
  if (typeof v !== 'string') return undefined;
  try { const u = new URL(v); return u.protocol === 'https:' && !u.username && !u.password ? u.href : undefined; }
  catch { return undefined; }
}
