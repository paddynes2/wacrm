export interface CrmContact {
  id: string;
  name?: string;
  phone: string;
  company?: string;
  email?: string;
}
export interface Pursuit {
  pursuit_id: string;
  revision: string;
  status: string;
  identity: {
    name: string;
    principal_name: string;
    principal_id: string;
    recipient_id: string;
    offer: string;
    fit: string;
    profile_url?: string;
    crm_ref?: string;
  };
  consents?: [string, string][];
  introduction_agreed?: boolean;
  group_agreed?: boolean;
  scheduling_agreed?: boolean;
  booking_agreed?: boolean;
  reply_required?: boolean;
  latest_inbound?: {
    text?: string;
    chat_id?: string;
    sender_id?: string;
  } | null;
  unresolved?: Record<string, string>;
  introduced?: boolean;
}
export interface TimelineEvent {
  event_id?: string;
  pursuit_id?: string;
  kind?: string;
  occurred_at?: string;
  ts?: string;
  text?: string;
  data?: Record<string, unknown>;
}
export interface PendingDecision {
  id: string;
  stale?: boolean;
  pursuit_id?: string;
  headline?: string;
  ask?: string;
  payload?: string;
  action?: {
    kind?: string;
    context?: { pursuit_id?: string };
    request?: { proposal?: { start?: string; end?: string; summary?: string } };
    frozen?: {
      text?: string;
      to?: string;
      concierge?: { pursuit_id?: string };
    };
  };
}
export interface WorkspaceData {
  mode: 'simulation' | 'live';
  error?: string;
  contacts: CrmContact[];
  workspace: {
    principal_name?: string;
    principal_phone?: string;
    offer?: string;
    timezone?: string;
    booking_link?: string;
    configured?: boolean;
  } | null;
  report: {
    pursuits?: Pursuit[];
    pending_decisions?: PendingDecision[];
    timeline?: TimelineEvent[];
    setup?: Record<string, unknown>;
    direct_messages?: {
      id: string;
      contact_id: string;
      text: string;
      direction: string;
      occurred_at: string;
      simulated?: boolean;
      group?: boolean;
    }[];
  } | null;
}
export const SCOPE_LABELS = {
  contact: 'Initial contact',
  introduction: 'An introduction',
  group: 'A group conversation',
  scheduling: 'Calendar coordination',
  booking: 'The proposed meeting',
} as const;
export type ConsentScope = keyof typeof SCOPE_LABELS;

export function statusLabel(status: string): string {
  return (
    (
      {
        proposed: 'Ready to approach',
        replied: 'In conversation',
        agreed: 'Ready to connect',
        introduced: 'Introduced',
        scheduling: 'Finding a time',
        booked: 'Meeting booked',
        attended: 'Conversation held',
        human_owned: 'You’re handling this',
        opted_out: 'Do not contact',
        declined: 'Not a fit',
        reconcile: 'Needs a check',
      } as Record<string, string>
    )[status] ?? 'Needs review'
  );
}
export function nextStep(pursuit: Pursuit): string {
  if (pursuit.status === 'opted_out')
    return 'Their request to stop is recorded. No further contact.';
  if (pursuit.status === 'declined') return 'This opportunity is closed.';
  if (pursuit.status === 'human_owned')
    return 'Chris is paused while you handle the conversation.';
  if (pursuit.reply_required)
    return 'Reply to the latest message before moving the introduction forward.';
  if (pursuit.status === 'booked')
    return 'Your meeting is booked. Keep the context ready for the conversation.';
  if (pursuit.scheduling_agreed && pursuit.introduced)
    return 'Find a suitable time for both people to connect.';
  if (
    pursuit.introduction_agreed &&
    pursuit.group_agreed &&
    !pursuit.introduced
  )
    return 'Both people have agreed. Prepare their introduction.';
  if (pursuit.latest_inbound)
    return 'Understand their interest and agree on the next step.';
  return 'Review the fit and prepare a concise, personal approach.';
}
export function belongsToDecision(
  decision: PendingDecision,
  pursuitId: string
): boolean {
  return (
    (decision.pursuit_id ??
      decision.action?.frozen?.concierge?.pursuit_id ??
      decision.action?.context?.pursuit_id) === pursuitId
  );
}
export function eventText(event: TimelineEvent): string {
  const data = event.data ?? {};
  if (typeof event.text === 'string') return event.text;
  for (const key of ['text', 'message', 'reason'])
    if (typeof data[key] === 'string') return data[key];
  if (event.kind === 'consent')
    return `Permission recorded: ${SCOPE_LABELS[data.scope as ConsentScope] ?? 'next step'}.`;
  return (
    (
      {
        identified: 'Opportunity added from your CRM.',
        inbound: 'A new reply was received.',
        takeover: 'You took over this conversation.',
        resume: 'The conversation was handed back to Chris.',
        dispatch_started: 'The approved action started.',
        dispatch_verified: 'The action was verified.',
        introduced: 'Both people were connected.',
        booking_verified: 'The meeting was verified.',
        opted_out: 'A request to stop was recorded.',
      } as Record<string, string>
    )[event.kind ?? ''] ?? 'Conversation updated.'
  );
}
export function initials(name: string): string {
  return (
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0])
      .join('')
      .toUpperCase() || '?'
  );
}
export function safeLink(value?: string): string | null {
  try {
    const url = new URL(value ?? '');
    return url.protocol === 'https:' && !url.username && !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}

export function dateBoundary(
  date: string,
  timezone: string,
  afterDay = false
): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date))
    throw new Error('Choose a valid date.');
  let target = Date.parse(`${date}T00:00:00Z`);
  if (
    !Number.isFinite(target) ||
    new Date(target).toISOString().slice(0, 10) !== date
  )
    throw new Error('Choose a valid date.');
  if (afterDay) target += 86400000;
  let formatter: Intl.DateTimeFormat;
  try {
    formatter = new Intl.DateTimeFormat('en-GB', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    });
  } catch {
    throw new Error('Choose a valid timezone.');
  }
  const wall = (timestamp: number) => {
    const parts = Object.fromEntries(
      formatter.formatToParts(new Date(timestamp)).map((p) => [p.type, p.value])
    );
    return Date.parse(
      `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}Z`
    );
  };
  const candidates = new Set<number>();
  for (const hours of [-36, 0, 36]) {
    const sample = target + hours * 3600000;
    const candidate = target - (wall(sample) - sample);
    if (wall(candidate) === target) candidates.add(candidate);
  }
  if (candidates.size !== 1)
    throw new Error(
      'This date begins during a clock change. Choose another boundary date.'
    );
  return new Date([...candidates][0]).toISOString();
}
