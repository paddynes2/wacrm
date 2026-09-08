import type { SupabaseClient } from '@supabase/supabase-js';

export interface DirectMessage {
  id: string;
  text: string;
  direction: 'inbound' | 'outbound';
  manual?: boolean;
  occurred_at: string;
  chat_id?: string;
  group?: boolean;
  simulated?: boolean;
}

function text(value: unknown, label: string, max = 500): asserts value is string {
  if (typeof value !== 'string' || !value.trim() || value.length > max || /[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(value)) {
    throw new Error(`Invalid ${label}`);
  }
}

/** Mirror observed direct messages only. This never creates an outbound receipt for a draft. */
export async function mirrorDirectMessages(db: SupabaseClient, input: {
  accountId: string; userId: string; contactId: string; messages: DirectMessage[];
}): Promise<{ conversationId: string; count: number }> {
  text(input.accountId, 'account');
  text(input.userId, 'user');
  text(input.contactId, 'contact');
  if (!Array.isArray(input.messages) || input.messages.length > 1000) throw new Error('Invalid message batch');
  const prepared = new Map<string, { message_id: string; content_text: string; sender_type: string; created_at: string }>();
  for (const message of input.messages) {
    if (!message || typeof message !== 'object' || Object.keys(message).some(k => !['id', 'text', 'direction', 'manual', 'occurred_at', 'chat_id', 'group', 'simulated'].includes(k))) throw new Error('Invalid message fields');
    text(message.id, 'message id', 200);
    text(message.text, 'message text', 16000);
    if (message.chat_id !== undefined) text(message.chat_id, 'chat id', 200);
    if (!['inbound', 'outbound'].includes(message.direction)) throw new Error('Invalid direction');
    for (const flag of ['manual', 'group', 'simulated'] as const) {
      if (message[flag] !== undefined && typeof message[flag] !== 'boolean') throw new Error('Invalid message flag');
    }
    if (message.manual && message.direction !== 'outbound') throw new Error('Inbound cannot be manual outbound');
    const parts = typeof message.occurred_at === 'string'
      ? /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.exec(message.occurred_at) : null;
    if (!parts) throw new Error('Message timestamp needs offset');
    const [, y, m, d, h, minute, second] = parts.map(Number);
    if (m < 1 || m > 12 || d < 1 || d > new Date(Date.UTC(y, m, 0)).getUTCDate() || h > 23 || minute > 59 || second > 59) throw new Error('Invalid calendar date');
    const occurred = Date.parse(message.occurred_at);
    if (!Number.isFinite(occurred) || occurred > Date.now() + 60000) throw new Error('Invalid message timestamp');
    if (message.group) continue;
    const id = `${message.simulated ? 'simulation' : 'unipile'}:${encodeURIComponent(message.chat_id ?? 'direct')}:${encodeURIComponent(message.id)}`;
    const row = { message_id: id, content_text: `${message.simulated ? '[Simulation] ' : ''}${message.text}`,
      sender_type: message.direction === 'inbound' ? 'customer' : message.manual ? 'agent' : 'bot',
      created_at: new Date(occurred).toISOString() };
    if (prepared.has(id) && JSON.stringify(prepared.get(id)) !== JSON.stringify(row)) throw new Error('Message id collision');
    prepared.set(id, row);
  }
  const { data: contact, error: contactError } = await db.from('contacts').select('id, account_id')
    .eq('id', input.contactId).eq('account_id', input.accountId).maybeSingle();
  if (contactError || !contact || contact.account_id !== input.accountId) throw new Error('Contact not found in account');

  const findConversation = () => db.from('conversations').select('id').eq('account_id', input.accountId)
    .eq('contact_id', input.contactId).maybeSingle();
  let found = await findConversation();
  if (found.error) throw new Error('Conversation lookup failed');
  if (!found.data) {
    found = await db.from('conversations').insert({ account_id: input.accountId, user_id: input.userId, contact_id: input.contactId })
      .select('id').single();
    if (found.error?.code === '23505') found = await findConversation();
    if (found.error || !found.data) throw new Error('Conversation creation failed');
  }
  const conversationId = found.data.id as string;
  let count = 0;
  for (const row of prepared.values()) {
    const { error } = await db.from('messages').insert({ ...row, conversation_id: conversationId,
      // The operator importing history is not evidence of who authored a manual send.
      content_type: 'text', status: 'sent', sender_id: null });
    if (error?.code === '23505') {
      const previous = await db.from('messages').select('message_id, content_text, sender_type, created_at')
        .eq('conversation_id', conversationId).eq('message_id', row.message_id).single();
      if (previous.error || !previous.data || previous.data.content_text !== row.content_text || previous.data.sender_type !== row.sender_type || Date.parse(previous.data.created_at) !== Date.parse(row.created_at)) throw new Error('Stored message id collision');
    } else if (error) throw new Error('Message mirror failed');
    else count++;
  }
  const latest = [...prepared.values()].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
  if (latest) {
    const { error } = await db.from('conversations').update({ last_message_text: latest.content_text, last_message_at: latest.created_at })
      .eq('id', conversationId).eq('account_id', input.accountId)
      .or(`last_message_at.is.null,last_message_at.lte.${latest.created_at}`);
    if (error) throw new Error('Conversation preview update failed');
  }
  return { conversationId, count };
}
