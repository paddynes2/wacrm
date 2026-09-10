"""Strict Unipile v1 evidence adapter. Unproven self fields stay unavailable."""
import datetime as dt
from .contracts import require
from .dispatch import V1Transport


class Provider:
    def __init__(self, client, expected_self=None, http=None):
        from copy import copy
        from functools import partial
        from ..providers import http_request
        self.client, self.expected_self = copy(client), expected_self
        self.pinned_self = expected_self
        if hasattr(self.client,'http') and self.client.http is None:
            self.client.http = partial(http_request,timeout=45)
        self.writer = V1Transport(client, http)

    def connection(self):
        row = self.client._get('/accounts/' + self.client.account_id)
        require(row.get('id') == self.client.account_id and row.get('type') == 'WHATSAPP', 'account_identity_changed', 409)
        # Current v1 account reference exposes sources.status, but its default
        # example is MOBILE, not evidence of a WhatsApp self identity mapping.
        # Prove self from an account-scoped attendee carrying is_self instead.
        self_ids = {a.get('provider_id') for a in self.client._pages('/chat_attendees')
                    if a.get('account_id') == self.client.account_id and a.get('is_self') in (True, 1)}
        require(len(self_ids) == 1 and None not in self_ids, 'account_identity_unresolved', 409)
        self_id = next(iter(self_ids))
        require(not self.pinned_self or self_id == self.pinned_self, 'account_identity_changed', 409)
        self.expected_self = self_id
        healthy = bool(row.get('sources')) and all(s.get('status') == 'OK' for s in row['sources'])
        return dict(provider_account_id=self.client.account_id, self_provider_id=self_id, type='WHATSAPP', connected=healthy, contract_verified=True)

    def members(self, chat_id):
        attendees = self.client._pages('/chats/' + chat_id + '/attendees')
        require(attendees and all(a.get('account_id') == self.client.account_id and a.get('provider_id') and type(a.get('is_self')) in (int, bool) for a in attendees), 'membership_unverified', 409)
        return attendees

    def resolve_identity(self, phone_e164):
        from .identity import phone
        phone(phone_e164)
        rows = [r for r in self.client._pages('/chat_attendees')
                if r.get('account_id') == self.client.account_id and not r.get('is_self')
                and r.get('phone_number') == phone_e164 and r.get('provider_id')]
        identities = {r['provider_id'] for r in rows}
        require(len(identities) == 1, 'recipient_identity_unresolved', 409)
        return dict(provider_id=next(iter(identities)), phone_e164=phone_e164,
                    provider_account_id=self.client.account_id, source='account_scoped_attendee')

    def membership(self, chat_id):
        chat = self.client._get('/chats/' + chat_id)
        require(chat.get('account_id') == self.client.account_id and chat.get('id') == chat_id, 'foreign_chat')
        rows = self.members(chat_id)
        self_rows = [a for a in rows if a['is_self']]
        return dict(participants=[a['provider_id'] for a in rows], self_verified=len(self_rows) == 1 and self_rows[0]['provider_id'] == self.expected_self,
                    chat_id=chat_id, account_id=self.client.account_id)

    def chats(self):
        result = []
        for chat in self.client.list_chats():
            try:
                members = self.members(chat['id'])
                result.append(dict(chat_id=chat['id'], account_id=self.client.account_id,
                                   recipients=[a['provider_id'] for a in members if not a['is_self']], is_group=bool(chat.get('is_group'))))
            except ValueError:
                continue
        return result

    def read_chat(self, chat_id):
        membership = self.membership(chat_id)
        attendees = self.members(chat_id)
        aliases = {a.get('id'): a['provider_id'] for a in attendees if a.get('id')}
        messages = []
        for row in self.client._pages('/chats/' + chat_id + '/messages'):
            require(row.get('account_id', self.client.account_id) == self.client.account_id and row.get('chat_id', chat_id) == chat_id, 'foreign_message')
            stamp = dt.datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            require(stamp.tzinfo is not None, 'invalid_timestamp')
            sender = self.expected_self if row.get('is_sender') else aliases.get(row.get('sender_id'))
            if not sender and row.get('sender_id') in membership['participants']: sender = row['sender_id']
            require(sender in membership['participants'], 'sender_identity_unresolved')
            content = row.get('text')
            kind = 'deleted' if row.get('is_deleted') or row.get('deleted_at') else 'text' if isinstance(content, str) else 'media' if row.get('attachments') else 'unsupported'
            messages.append(dict(message_id=row['id'], sender_id=sender, timestamp=stamp.timestamp(), text=(content or '')[:16000],
                                 original_timestamp=row['timestamp'],
                                 edited_at=row.get('edited_at'), deleted_at=row.get('deleted_at'),
                                 truncated=isinstance(content, str) and len(content) > 16000, kind=kind, outbound=bool(row.get('is_sender')),
                                 forwarded=bool(row.get('is_forwarded')), quoted=bool(row.get('quoted')), reply_to=row.get('reply_to_id')))
        return dict(account_id=self.client.account_id, chat_id=chat_id, recipients=[p for p in membership['participants'] if p != self.expected_self],
                    messages=messages, complete=True, truncated=False, coverage='Provider pagination complete; historical retention unverified', membership=membership)

    def preflight(self, frozen):
        connection = self.connection()
        review_chat = frozen.get('review_chat_id') if frozen['purpose'] == 'group_create' else frozen['chat_id']
        if not review_chat:
            candidates = [c for c in self.chats() if not c['is_group'] and set(c['recipients']) == set(frozen['recipients'])]
            # Existing matching chats must be bound and reviewed, never bypassed by new-chat creation.
            require(not candidates, 'existing_thread_review_needed', 409)
            return dict(account_id=self.client.account_id, self_provider_id=connection['self_provider_id'], history_ready=connection['connected'], message_ids=[], coverage='Complete current chat listing; no matching direct chat observed')
        batch = self.read_chat(review_chat)
        from .ingestion import STOP, DECLINE
        messages = batch['messages']
        return dict(account_id=self.client.account_id, self_provider_id=connection['self_provider_id'],
                    chat_id=batch['chat_id'],
                    history_ready=batch['complete'] and batch['membership']['self_verified'],
                    membership_verified=batch['membership']['self_verified'], recipients=batch['recipients'],
                    stop=any(not m['outbound'] and (STOP.search(m['text']) or DECLINE.search(m['text'])) for m in messages),
                    manual=any(m['outbound'] and m['timestamp'] > frozen['not_before'] for m in messages),
                    pending_inbound=any(not m['outbound'] and m['timestamp'] > frozen['not_before'] for m in messages),
                    message_ids=[m['message_id'] for m in messages])

    def mutate(self, frozen):
        return self.writer.mutate(frozen)

    def observe_action(self, action):
        f = action['frozen']
        chat_id = action.get('provider_chat_id') or f['chat_id']
        chats = [dict(chat_id=chat_id)] if chat_id else [c for c in self.chats() if set(c['recipients']) == set(f['recipients'])]
        observations = []
        for chat in chats[:20]:
            batch = self.read_chat(chat['chat_id'])
            for m in batch['messages']:
                observations.append(dict(account_id=batch['account_id'], self_provider_id=self.expected_self,
                    sender_id=m['sender_id'], text=m['text'], recipients=batch['recipients'], timestamp=m['timestamp'],
                    message_id=m['message_id'], chat_id=batch['chat_id'], membership_verified=batch['membership']['self_verified']))
        return observations
