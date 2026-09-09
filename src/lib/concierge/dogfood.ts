import { BridgeError, isUuid } from './bridge';

type ObjectValue = Record<string, unknown>;
export const isObject = (value: unknown): value is ObjectValue =>
  !!value && typeof value === 'object' && !Array.isArray(value);
const commands: Record<string, string[]> = {
  save_brief: ['brief'],
  discover: ['source', 'limit'],
  qualify: ['prospect_id', 'verdict', 'reason'],
  start: ['prospect_id'],
  reply: ['prospect_id', 'text'],
  process: [],
  approve: ['decision_id'],
  discard: ['decision_id'],
  takeover: ['prospect_id'],
  resume: ['prospect_id'],
  consent: ['prospect_id', 'party', 'scope', 'source_ref'],
  introduce: ['prospect_id'],
  propose: ['prospect_id', 'start', 'end', 'timezone'],
  book: ['prospect_id', 'start', 'end'],
  review: ['prospect_id', 'useful', 'minutes', 'note'],
  readiness: [],
  promote: ['prospect_id'],
  enrich: ['prospect_id', 'phone', 'source_ref'],
  pause: [],
  unpause: [],
  advance: ['seconds'],
  followup: ['prospect_id', 'seconds'],
  attended: ['prospect_id', 'source_ref'],
  manual_reply: ['prospect_id', 'text'],
  retry_job: ['job_id'],
  new_pursuit: ['prospect_id'],
  sync: [],
  reconcile: [],
  research: ['prospect_id'],
  research_phone: ['prospect_id'],
  calendar_preferences: [
    'prospect_id',
    'party',
    'timezone',
    'windows',
    'calendar_access',
    'simulated_busy',
    'source_ref',
  ],
  request_calendar_exception: [
    'prospect_id',
    'party',
    'start',
    'end',
    'source_ref',
  ],
  booking_link: ['prospect_id'],
  prepare_amendment: ['prospect_id', 'operation', 'start', 'end', 'source_ref'],
  approve_amendment: ['prospect_id', 'digest'],
};
export type CalendarWindow = { weekday: number; start: string; end: string };
export type CalendarBusy = { start: string; end: string };
/** Forms load only on explicit context changes; background reports must not erase edits. */
export function calendarScenarioDraft(
  report: {
    brief?: { timezone?: string } | null;
    calendar_preferences?: unknown;
    prospects: { id: string; calendar_preferences?: unknown }[];
  },
  prospectId: string,
  party: string
) {
  const saved =
    party === 'principal'
      ? report.calendar_preferences
      : report.prospects.find((p) => p.id === prospectId)?.calendar_preferences;
  const settings = isObject(saved) ? saved : {};
  return {
    timezone:
      typeof settings.timezone === 'string'
        ? settings.timezone
        : report.brief?.timezone || 'Africa/Johannesburg',
    windows: (Array.isArray(settings.windows)
      ? settings.windows
      : [0, 1, 2, 3, 4].map((weekday) => ({
          weekday,
          start: '09:00',
          end: '17:00',
        }))) as CalendarWindow[],
    calendar_access:
      typeof settings.calendar_access === 'boolean'
        ? settings.calendar_access
        : true,
    simulated_busy: (Array.isArray(settings.simulated_busy)
      ? settings.simulated_busy
      : []) as CalendarBusy[],
  };
}
function fail(message: string): never {
  throw new BridgeError(message, 400);
}
function bounded(value: unknown, max = 4000, optional = false): boolean {
  return (
    typeof value === 'string' &&
    value.length <= max &&
    (optional || value.trim().length > 0)
  );
}
export function validateDogfoodCommand(value: unknown): ObjectValue {
  if (
    !isObject(value) ||
    typeof value.command !== 'string' ||
    !Object.hasOwn(commands, value.command)
  )
    fail('Unknown dogfood command.');
  const fields = commands[value.command as string];
  if (
    Object.keys(value).some((key) => key !== 'command' && !fields.includes(key))
  )
    fail('Unexpected command fields.');
  for (const key of fields) {
    if (
      value.command === 'calendar_preferences' &&
      key === 'simulated_busy' &&
      !(key in value)
    )
      continue;
    if (
      value.command === 'prepare_amendment' &&
      value.operation === 'cancel' &&
      ['start', 'end'].includes(key)
    )
      continue;
    if (!(key in value)) fail(`Missing ${key}.`);
    if (
      ['prospect_id', 'decision_id', 'job_id'].includes(key) &&
      (!bounded(value[key], 200) ||
        !/^[a-zA-Z0-9:_-]+$/.test(String(value[key])))
    )
      fail('Invalid record identifier.');
  }
  if (
    value.command === 'prepare_amendment' &&
    !['reschedule', 'cancel'].includes(String(value.operation))
  )
    fail('Choose reschedule or cancel.');
  if (
    ['calendar_preferences', 'request_calendar_exception'].includes(
      String(value.command)
    ) &&
    !['principal', 'recipient'].includes(String(value.party))
  )
    fail('Choose whose calendar is affected.');
  if (value.command === 'calendar_preferences') {
    if (!bounded(value.source_ref, 500))
      fail('Provide calendar preference evidence (up to 500 characters).');
    try {
      new Intl.DateTimeFormat('en', { timeZone: String(value.timezone) });
    } catch {
      fail('Invalid calendar timezone.');
    }
    if (
      typeof value.calendar_access !== 'boolean' ||
      !Array.isArray(value.windows) ||
      value.windows.length < 1 ||
      value.windows.length > 28
    )
      fail('Choose calendar access and working windows.');
    for (const window of value.windows) {
      if (
        !isObject(window) ||
        Object.keys(window).sort().join(',') !== 'end,start,weekday' ||
        !Number.isInteger(window.weekday) ||
        Number(window.weekday) < 0 ||
        Number(window.weekday) > 6 ||
        !/^([01]\d|2[0-3]):[0-5]\d$/.test(String(window.start)) ||
        !/^([01]\d|2[0-3]):[0-5]\d$/.test(String(window.end)) ||
        String(window.end) <= String(window.start)
      )
        fail('Working windows require valid days and increasing clock times.');
    }
    const busy = value.simulated_busy ?? [];
    if (!Array.isArray(busy) || busy.length > 500)
      fail('Invalid simulated busy intervals.');
    for (const interval of busy) {
      if (
        !isObject(interval) ||
        Object.keys(interval).sort().join(',') !== 'end,start'
      )
        fail('Invalid busy interval.');
      for (const key of ['start', 'end'])
        if (
          !/(Z|[+-]\d{2}:\d{2})$/.test(String(interval[key])) ||
          !Number.isFinite(Date.parse(String(interval[key])))
        )
          fail('Busy interval needs timezone offsets.');
      if (
        Date.parse(String(interval.end)) <= Date.parse(String(interval.start))
      )
        fail('Busy interval end must follow its start.');
    }
  }
  if (
    'digest' in value &&
    (typeof value.digest !== 'string' || !/^[a-f0-9]{64}$/.test(value.digest))
  )
    fail('Invalid amendment digest.');
  if (value.command === 'save_brief') {
    const b = value.brief;
    const required = [
      'principal_name',
      'offer',
      'audience',
      'geography',
      'timezone',
    ];
    const optional = ['exclusions', 'claims', 'booking_link'];
    if (
      !isObject(b) ||
      Object.keys(b).some(
        (k) => ![...required, ...optional, 'budget_usd'].includes(k)
      )
    )
      fail('Invalid brief fields.');
    for (const key of required)
      if (!bounded(b[key])) fail(`Complete ${key.replaceAll('_', ' ')}.`);
    for (const key of optional)
      if (b[key] !== undefined && !bounded(b[key], 4000, true))
        fail(`Invalid ${key}.`);
    if (
      typeof b.budget_usd !== 'number' ||
      !Number.isFinite(b.budget_usd) ||
      b.budget_usd < 0 ||
      b.budget_usd > 10000
    )
      fail('Budget must be between 0 and 10,000 USD.');
    try {
      new Intl.DateTimeFormat('en', { timeZone: String(b.timezone) });
    } catch {
      fail('Use a valid timezone.');
    }
    if (b.booking_link) {
      try {
        if (new URL(String(b.booking_link)).protocol !== 'https:')
          fail('Booking link must use HTTPS.');
      } catch {
        fail('Invalid booking link.');
      }
    }
  }
  if (
    value.command === 'discover' &&
    (!['fixture', 'treg'].includes(String(value.source)) ||
      !Number.isInteger(value.limit) ||
      Number(value.limit) < 1 ||
      Number(value.limit) > 20)
  )
    fail('Choose a source and 1–20 candidates.');
  if (
    value.command === 'qualify' &&
    !['qualified', 'rejected'].includes(String(value.verdict))
  )
    fail('Invalid qualification.');
  for (const key of ['reason', 'text', 'source_ref'])
    if (key in value && !bounded(value[key])) fail(`Provide ${key}.`);
  if (
    'phone' in value &&
    (typeof value.phone !== 'string' || !/^\+[1-9]\d{7,14}$/.test(value.phone))
  )
    fail('Use an international phone number with country code.');
  if (
    'seconds' in value &&
    (typeof value.seconds !== 'number' ||
      !Number.isFinite(value.seconds) ||
      value.seconds < 0 ||
      value.seconds > 30 * 86400)
  )
    fail('Choose a duration between 0 and 30 days.');
  if ('note' in value && !bounded(value.note, 4000, true))
    fail('Invalid review note.');
  if (
    value.command === 'review' &&
    (typeof value.useful !== 'boolean' ||
      typeof value.minutes !== 'number' ||
      !Number.isFinite(value.minutes) ||
      value.minutes < 0 ||
      value.minutes > 1440)
  )
    fail('Provide a usefulness judgment and 0–1,440 minutes.');
  if (
    value.command === 'consent' &&
    (!['principal', 'recipient'].includes(String(value.party)) ||
      !['contact', 'introduction', 'group', 'scheduling', 'booking'].includes(
        String(value.scope)
      ))
  )
    fail('Invalid permission scope or party.');
  if (
    ['propose', 'book', 'request_calendar_exception'].includes(
      String(value.command)
    ) ||
    (value.command === 'prepare_amendment' && value.operation === 'reschedule')
  ) {
    for (const key of ['start', 'end'])
      if (
        !bounded(value[key], 50) ||
        !/(Z|[+-]\d{2}:\d{2})$/.test(String(value[key])) ||
        !Number.isFinite(Date.parse(String(value[key])))
      )
        fail('Meeting times need an explicit timezone offset.');
    if (Date.parse(String(value.end)) <= Date.parse(String(value.start)))
      fail('Meeting end must follow its start.');
    if ('timezone' in value) {
      try {
        new Intl.DateTimeFormat('en', { timeZone: String(value.timezone) });
      } catch {
        fail('Invalid timezone.');
      }
    }
  }
  return value;
}

export async function dogfoodRequest(accountId: string, command?: ObjectValue) {
  if (!isUuid(accountId)) throw new BridgeError('Invalid account.', 400);
  const base = process.env.WACRM_BRIDGE_URL;
  const token = process.env.WACRM_BRIDGE_TOKEN;
  if (!base || !token)
    throw new BridgeError('The concierge service is not connected.', 503);
  let url: URL;
  try {
    url = new URL(base);
  } catch {
    throw new BridgeError('Invalid concierge service configuration.', 503);
  }
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw new BridgeError('Invalid concierge service configuration.', 503);
  let response: Response;
  try {
    response = await fetch(
      `${base.replace(/\/$/, '')}/workspace/${accountId}/dogfood`,
      {
        method: command ? 'POST' : 'GET',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: command ? JSON.stringify(command) : undefined,
        cache: 'no-store',
        signal: AbortSignal.timeout(30_000),
      }
    );
  } catch {
    throw new BridgeError(
      'The concierge service could not be reached. Refresh before retrying.',
      503
    );
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok)
    throw new BridgeError(
      isObject(body) && typeof body.detail === 'string'
        ? body.detail.slice(0, 500)
        : 'The concierge could not complete this action.',
      [400, 404, 409, 422, 503].includes(response.status)
        ? response.status
        : 502
    );
  if (!isObject(body)) throw new BridgeError('Invalid concierge response.');
  return body;
}

export function dogfoodApprovalEnabled(
  mode: unknown,
  readiness: Record<string, unknown> | undefined,
  amendment = false
): boolean {
  return (
    mode === 'simulation' ||
    (mode === 'live' &&
      readiness?.[
        amendment ? 'live_amendments_enabled' : 'live_execution_enabled'
      ] === true)
  );
}
