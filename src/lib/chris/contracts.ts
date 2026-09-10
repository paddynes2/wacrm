import schema from './schema.json';

export type Row = Record<string, unknown>;
export async function parseRequest(request: Request): Promise<unknown> {
  const reader=request.body?.getReader();
  if (!reader) return parse('');
  const chunks: Uint8Array[]=[]; let total=0;
  for (;;) {
    const { done,value }=await reader.read(); if (done) break;
    total+=value.byteLength;
    if (total>32768) { await reader.cancel(); throw new ChrisError('body_too_large',413); }
    chunks.push(value);
  }
  const bytes=new Uint8Array(total);let offset=0;
  for (const chunk of chunks) { bytes.set(chunk,offset);offset+=chunk.byteLength; }
  let raw: string;
  try { raw=new TextDecoder('utf-8',{fatal:true}).decode(bytes); }
  catch { throw new ChrisError('invalid_unicode'); }
  return parse(raw);
}
export const object = (v: unknown): v is Row => !!v && typeof v === 'object' && !Array.isArray(v);
export class ChrisError extends Error {
  constructor(public code: string, public status = 400) { super(code.replaceAll('_', ' ')); }
}
export function assert(value: unknown, code = 'invalid_contract', status = 400): asserts value {
  if (!value) throw new ChrisError(code, status);
}
export const uuid = (v: unknown) => typeof v === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(v);
const integer = (v: unknown) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
function timestamp(v: unknown): boolean {
  if (typeof v!=='string') return false;
  const parts=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.exec(v);
  if (!parts) return false;
  const [year,month,day,hour,minute,second]=parts.slice(1).map(Number);
  const leap=year%4===0 && (year%100!==0 || year%400===0);
  const days=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31];
  return year>=1 && month>=1 && month<=12 && day>=1 && day<=days[month-1] && hour<24 && minute<60 && second<60 && Number.isFinite(Date.parse(v));
}
export function exact(v: unknown, required: string[], optional: string[] = []): asserts v is Row {
  assert(object(v) && required.every(k => k in v) && Object.keys(v).every(k => required.includes(k) || optional.includes(k)));
}
export function bounded(v: unknown, max = 500, min = 1): asserts v is string {
  assert(typeof v === 'string' && [...v].length >= min && [...v].length <= max && !/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(v));
  assert(!/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(v), 'invalid_unicode');
}

/** JSON.parse cannot detect duplicate object keys, so validate the grammar first. */
export function parse(raw: string): unknown {
  assert(new TextEncoder().encode(raw).length <= 32768, 'body_too_large', 413);
  let position = 0;
  const space = () => { while (/\s/.test(raw[position] ?? '') && position < raw.length) position++; };
  function string(): string {
    const start = position++;
    while (position < raw.length) {
      if (raw[position++] === '"') return JSON.parse(raw.slice(start, position));
      if (raw[position - 1] === '\\') position++;
    }
    throw new ChrisError('invalid_json');
  }
  function value(): void {
    space();
    if (raw[position] === '{') {
      position++; space(); const seen = new Set<string>();
      if (raw[position] !== '}') while (true) {
        space(); assert(raw[position] === '"', 'invalid_json'); const key = string();
        assert(!seen.has(key), 'duplicate_key'); seen.add(key); space();
        assert(raw[position++] === ':', 'invalid_json'); value(); space();
        if (raw[position] !== ',') break; position++;
      }
      assert(raw[position++] === '}', 'invalid_json');
    } else if (raw[position] === '[') {
      position++; space();
      if (raw[position] !== ']') while (true) { value(); space(); if (raw[position] !== ',') break; position++; }
      assert(raw[position++] === ']', 'invalid_json');
    } else if (raw[position] === '"') { string(); }
    else {
      const match = /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(raw.slice(position));
      assert(match, 'invalid_json'); position += match[0].length;
      if (/^-?\d/.test(match[0])) {
        assert(Number.isFinite(Number(match[0])), 'non_finite');
        assert(!/[.eE]/.test(match[0]), 'invalid_integer');
      }
    }
  }
  try { value(); space(); assert(position === raw.length, 'invalid_json'); return JSON.parse(raw); }
  catch (e) { if (e instanceof ChrisError) throw e; throw new ChrisError('invalid_json'); }
}

export type Command = { schema_version: 1; command_id: string; expected_revision: number; command: string; payload: Row };
export function validateCommand(v: unknown): Command {
  exact(v, ['schema_version', 'command_id', 'expected_revision', 'command', 'payload']);
  assert(v.schema_version === 1, 'upgrade_required', 409);
  assert(uuid(v.command_id), 'invalid_uuid'); assert(integer(v.expected_revision), 'invalid_integer');
  assert(typeof v.command === 'string' && Object.hasOwn(schema.commands, v.command));
  const name = v.command;
  exact(v.payload, (schema.commands as Record<string, string[]>)[name], name === 'settings.update' ? schema.settings : []);
  for (const [key, item] of Object.entries(v.payload)) {
    if (key.endsWith('_id')) assert(uuid(item), 'invalid_uuid');
    else if (['enabled', 'research_enabled', 'principal_messages_enabled'].includes(key)) assert(typeof item === 'boolean');
    else if (key.startsWith('daily_') || ['job_micro_usd', 'displayed_authority_revision', 'reviewed_thread_watermark'].includes(key)) assert(integer(item));
    else if (['not_before', 'granted_at'].includes(key)) assert(timestamp(item),'invalid_timestamp');
    else if (key === 'scope_kinds') assert(Array.isArray(item) && new Set(item).size === item.length && item.every(k => schema.kinds.includes(k)));
    else if (key === 'kind') assert(item === 'contact');
    else if (key === 'evidence_refs') { assert(Array.isArray(item) && item.length >= 1 && item.length <= 20); item.forEach(x => bounded(x)); }
    else if (key === 'brief') {
      exact(item, ['objective', 'principal_display_name', 'principal_public_context', 'timezone'], ['candidate_archetypes', 'geography_include', 'geography_exclude', 'explicit_exclusions', 'approved_claims', 'confidentiality_rules', 'known_relationship_policy']);
      bounded(item.objective, 4000); bounded(item.principal_display_name, 120); bounded(item.principal_public_context, 4000, 0); bounded(item.timezone);
      try { new Intl.DateTimeFormat('en', { timeZone: item.timezone }); } catch { throw new ChrisError('invalid_timezone'); }
      for (const field of ['candidate_archetypes', 'geography_include', 'geography_exclude', 'explicit_exclusions', 'confidentiality_rules']) {
        if (item[field] !== undefined) { assert(Array.isArray(item[field]) && item[field].length <= (field === 'candidate_archetypes' ? 12 : 50)); item[field].forEach(x => bounded(x, 300)); }
      }
      if (item.known_relationship_policy !== undefined) assert(['wacrm', 'strict_first_degree'].includes(String(item.known_relationship_policy)));
      if (item.approved_claims !== undefined) { assert(Array.isArray(item.approved_claims) && item.approved_claims.length <= 50); for (const claim of item.approved_claims) { exact(claim, ['id', 'text', 'evidence_ref', 'public']); bounded(claim.id); bounded(claim.text, 1000); bounded(claim.evidence_ref); assert(typeof claim.public === 'boolean'); } }
    } else bounded(item, name === 'brief.propose' ? 8000 : key === 'text' ? 16000 : 500);
  }
  return v as Command;
}
export const ownerCommand = (name: string) => schema.owner.includes(name);
export function canonical(v: unknown): string {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (object(v)) return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}';
  assert(v !== undefined && (typeof v !== 'number' || Number.isFinite(v)));
  return JSON.stringify(v);
}
