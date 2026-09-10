"""Frozen single-attempt outbox. Uncertainty permits reads, never a resend."""
import json
import secrets
import re
import urllib.request
from uuid import uuid4
from ..providers import _NoRedirect
from .contracts import require, digest, text
from .permissions import eligibility, applicable
from .state import event, transition

UNRESOLVED = {'started', 'provider_accepted', 'unknown', 'reconciling', 'needs_attention'}


def multipart(fields):
    boundary = 'chris-' + secrets.token_hex(20)
    output = bytearray()
    for name, value in fields:
        require(name in {'account_id', 'attendees_ids', 'subject', 'text'}, 'invalid_multipart_field')
        text(value, 16000)
        output.extend(('--' + boundary + '\r\nContent-Disposition: form-data; name="' + name + '"\r\n\r\n').encode())
        output.extend(value.encode('utf-8')); output.extend(b'\r\n')
    output.extend(('--' + boundary + '--\r\n').encode())
    return bytes(output), 'multipart/form-data; boundary=' + boundary


def freeze(state, account, pursuit, kind, content, now, *, claim_ids=None, intro=None):
    text(content, 16000)
    require('\u2014' not in content and '\u2013' not in content, 'content_style_violation')
    person = state['people'][pursuit['person_id']]
    if kind=='invite':
        brief = state['brief_versions'].get(str(state['active_brief_revision']),{})
        require('chris' in content.lower() and re.search(r'\bAI\b',content,re.I)
            and brief.get('principal_display_name','').lower() in content.lower(),'assistant_disclosure_required',409)
    connection, principal = state['connection'] or {}, state['principal'] or {}
    recipients = [person.get('provider_id')]
    if intro or kind in {'group_create', 'group_introduction'}:
        recipients = [principal.get('provider_id'), person.get('provider_id')]
    thread = state['threads'].get(pursuit.get('direct_thread_key'), {})
    frozen = dict(account_id=account, connection_generation=connection.get('generation'),
                  provider_account_id=connection.get('provider_account_id'), self_provider_id=connection.get('self_provider_id'),
                  principal_binding_revision=principal.get('revision'), principal_provider_id=principal.get('provider_id'),
                  recipients=recipients, chat_id=intro.get('group_chat_id') if intro else thread.get('provider_chat_id'),
                  group_subject=intro.get('subject') if intro and kind == 'group_create' else None,
                  text=content, purpose=kind, brief_revision=state['active_brief_revision'],
                  research_revision=state['research_revision'], pursuit_revision=pursuit['state_revision'],
                  authority_revision=state['authority']['revision'],
                  permission_ids=sum((applicable(state, pursuit, scope, now) for scope in ['contact', 'introduction', 'group']), []),
                  source_claim_ids=claim_ids or [], history_watermark=thread.get('last_observed_seq', 0),
                  review_chat_id=thread.get('provider_chat_id'),
                  not_before=now, expires_at=now + 86400)
    action = dict(action_id=str(uuid4()), kind=kind, pursuit_id=pursuit['pursuit_id'], intro_id=intro.get('intro_id') if intro else None,
                  created_at=now, status='draft', frozen=frozen, digest=digest(frozen), dispatch_generation=0, attempts=0)
    state['actions'][action['action_id']] = action
    if kind in {'invite', 'permission_clarification'}:
        brief = state['brief_versions'].get(str(state['active_brief_revision']), {})
        name = brief.get('principal_display_name', '')
        folded = content.lower()
        frozen['question_scope'] = dict(principal_id=principal.get('provider_id'),
            introduction=bool(name and name in content and 'introduction' in folded and '?' in content
                              and not re.search(r"\b(not|without|unless|if|but)\b|don.t", folded)),
            group=bool('group' in folded and name in content and ('and me' in folded or 'chris' in folded)),
            number_visibility=('see' in folded and 'number' in folded),
            pending_question_count=content.count('?'))
        action['digest'] = digest(frozen)
    return action


class V1Transport:
    def __init__(self, client, http=None):
        self.client, self.http = client, http

    def mutate(self, frozen):
        if frozen['chat_id'] and frozen['purpose'] != 'group_create':
            route = '/chats/' + frozen['chat_id'] + '/messages'
            fields = [('text', frozen['text'])]
        else:
            route = '/chats'
            fields = [('account_id', frozen['provider_account_id'])]
            fields += [('attendees_ids', recipient) for recipient in frozen['recipients']]
            if frozen['group_subject']:
                fields.append(('subject', frozen['group_subject']))
            fields.append(('text', frozen['text']))
        body, content_type = multipart(fields)
        headers = {'X-API-KEY': self.client.key, 'Content-Type': content_type, 'Accept': 'application/json'}
        if self.http:
            status, response = self.http('POST', self.client.base + route, headers, body)
        else:
            request = urllib.request.Request(self.client.base + route, data=body, headers=headers, method='POST')
            with urllib.request.build_opener(_NoRedirect).open(request, timeout=30) as response:
                raw = response.read(100001)
                require(len(raw) <= 100000, 'provider_response_limit')
                status, response = response.status, json.loads(raw)
        require(200 <= status < 300 and isinstance(response, dict), 'dispatch_unknown', 409)
        if route == '/chats':
            require(response.get('object') == 'ChatStarted' and response.get('chat_id') and response.get('message_id'), 'dispatch_unknown', 409)
        else:
            require(response.get('message_id'), 'dispatch_unknown', 409)
        return response


class Dispatcher:
    def __init__(self, service, providers, authorizer=None):
        self.service, self.providers, self.authorizer = service, providers, authorizer

    def execute(self, account, payload):
        service = self.service
        current = service.snapshot(account)
        action = service.entity(current, 'actions', payload['action_id'])
        if action['status'] in UNRESOLVED:
            return self.reconcile(account, payload)
        require(action['status'] == 'queued', 'action_not_queued', 409)
        provider = self.providers.get(account)
        require(provider is not None and callable(self.authorizer), 'host_authorizer_missing', 409)
        # Refresh complete owned evidence outside the writer transaction.
        observation = provider.preflight(action['frozen'])
        require(observation.get('history_ready'), 'history_incomplete', 409)
        with service.transaction(account) as (_, state):
            action = service.entity(state, 'actions', payload['action_id'])
            require(action['status'] == 'queued', 'action_already_claimed', 409)
            f = action['frozen']; pursuit = state['pursuits'].get(action['pursuit_id'])
            now = service.clock()
            require(digest(f) == action['digest'], 'action_changed', 409)
            require(f['account_id'] == account and f['research_revision'] == state['research_revision']
                    and f['authority_revision'] == state['authority']['revision']
                    and f['connection_generation'] == (state['connection'] or {}).get('generation')
                    and f['principal_binding_revision'] == (state['principal'] or {}).get('revision')
                    and f['pursuit_revision'] == (pursuit['state_revision'] if pursuit else None), 'action_stale', 409)
            require(f['not_before'] <= now < f['expires_at'], 'action_expired', 409)
            require(not state['storage'].get('outbound_paused'), 'storage_attention', 409)
            if action['kind']=='principal_reply':
                from .principal import eligibility as principal_eligibility
                reasons=principal_eligibility(state)
            else: reasons = eligibility(state, pursuit, now, action['kind'])
            require(not reasons, reasons[0] if reasons else 'ineligible', 409)
            require(action['created_at'] >= state['authority']['future_actions_from'], 'old_draft', 409)
            require(observation.get('account_id') == f['provider_account_id'] and observation.get('self_provider_id') == f['self_provider_id'], 'provider_identity_changed', 409)
            require(not observation.get('stop') and not observation.get('manual') and not observation.get('pending_inbound'), 'thread_changed', 409)
            if action['kind'] == 'group_introduction' or (action.get('intro_id') and action['kind'] == 'reply'):
                require(observation.get('membership_verified') and set(observation.get('recipients', [])) == set(f['recipients']), 'membership_mismatch', 409)
                require(not state['introductions'][action['intro_id']].get('membership_changed'), 'membership_mismatch', 409)
            require(self.authorizer(account, state, action), 'host_authority_denied', 409)
            require(not any(a['action_id'] != action['action_id'] and a['status'] in UNRESOLVED
                            and (a['pursuit_id'] == action['pursuit_id'] or a['status'] == 'started')
                            for a in state['actions'].values()), 'account_dispatch_busy', 409)
            import datetime as dt
            from zoneinfo import ZoneInfo
            zone = ZoneInfo(state['settings']['timezone'])
            day = max(dt.datetime.fromtimestamp(now,zone).date().isoformat(),state['budgets'].get('outbound_latest_day',''))
            dispatched = [a for a in state['actions'].values() if a.get('started_at') and a.get('outbound_day',dt.datetime.fromtimestamp(a['started_at'],zone).date().isoformat()) == day]
            require(len(dispatched) < state['settings']['daily_total'], 'daily_outbound_limit', 409)
            if action['kind'] == 'invite':
                require(sum(a['kind'] == 'invite' for a in dispatched) < state['settings']['daily_invites'], 'daily_invite_limit', 409)
                require(not any(a.get('started_at') and a['kind'] == 'invite' and a['pursuit_id'] == action['pursuit_id'] for a in state['actions'].values()), 'invitation_already_attempted', 409)
            action.update(status='started', started_at=now, dispatch_generation=action['dispatch_generation'] + 1, attempts=action['attempts'] + 1,
                          preflight=observation, outbound_day=day)
            state['budgets']['outbound_latest_day'] = day
            frozen = dict(f)
            event(state, 'action_started', now, action['action_id'], digest=action['digest'])
        try:
            response = provider.mutate(frozen)
            response_ref = service.blobs.put(response)
            with service.transaction(account, recovery=True) as (_, state):
                row = state['actions'][payload['action_id']]
                row.update(status='provider_accepted', provider_response_ref=response_ref,
                           provider_message_id=response['message_id'], provider_chat_id=response.get('chat_id', frozen['chat_id']))
        except Exception:
            with service.transaction(account, recovery=True) as (_, state):
                state['actions'][payload['action_id']].update(status='unknown', last_error_code='dispatch_unknown', next_reconcile_at=service.clock() + 10)
            return
        self.reconcile(account, payload)

    def reconcile(self, account, payload):
        service = self.service
        current = service.snapshot(account)
        action = service.entity(current, 'actions', payload['action_id'])
        if action['status'] == 'verified':
            return
        require(action['status'] in UNRESOLVED, 'action_not_started', 409)
        require(digest(action['frozen'])==action['digest'],'action_changed',409)
        provider = self.providers.get(account)
        require(provider is not None, 'connection_unavailable', 503)
        candidates = provider.observe_action(action)
        valid = [row for row in candidates if self.matches(action, row)]
        with service.transaction(account, recovery=True) as (_, state):
            row = state['actions'][action['action_id']]
            if row['status'] == 'verified':
                return
            row['reconcile_attempts'] = row.get('reconcile_attempts', 0) + 1
            if len(valid) != 1:
                row.update(status='needs_attention' if len(valid) > 1 or row['reconcile_attempts'] >= 5 else 'unknown',
                           last_error_code='ambiguous_receipt' if len(valid) > 1 else 'receipt_unobserved',
                           next_reconcile_at=service.clock() + [10, 60, 300, 1800, 86400][min(row['reconcile_attempts'] - 1, 4)])
                return
            receipt = valid[0]
            row.update(status='verified', verified_at=service.clock(), receipt=receipt,
                       provider_chat_id=receipt['chat_id'], provider_message_id=receipt['message_id'], last_error_code=None)
            pursuit = state['pursuits'].get(row['pursuit_id'])
            if row['kind']=='principal_reply':
                event(state,'principal_reply_verified',service.clock(),row['action_id'])
                return
            if row['kind'] in {'invite','followup'}: pursuit['last_verified_outbound_at'] = service.clock()
            if row['kind'] in {'invite', 'followup'} and pursuit['state'] not in {'suppressed', 'declined', 'excluded'}:
                if pursuit['state'] in {'qualified', 'contact_unresolved'}:
                    transition(pursuit, 'ready_to_invite', service.clock())
                transition(pursuit, 'awaiting_reply', service.clock())
                pursuit['last_verified_outbound_at'] = service.clock()
                if row['kind'] == 'followup':
                    pursuit['followup_count_verified'] += 1
                    pursuit.pop('useful_followup_reason',None)
                pursuit['active_invitation_action_id'] = row['action_id']
                from .timing import next_followup
                due = next_followup(service.clock(), state['people'][pursuit['person_id']].get('timezone'), pursuit['followup_count_verified'])
                pursuit['not_before'] = due
                if pursuit['followup_count_verified']>=2:
                    pursuit['no_response_after'] = next_followup(service.clock(),state['people'][pursuit['person_id']].get('timezone'),1)
            if row['kind'] == 'permission_clarification':
                pursuit['active_invitation_action_id'] = row['action_id']
                pursuit['clarification_count'] = pursuit.get('clarification_count',0)+1
            if row['kind'] in {'reply', 'permission_clarification'}:
                pursuit['reply_required'] = False
            if row['kind'] in {'invite', 'reply', 'permission_clarification', 'followup'} and not row.get('intro_id'):
                from .projection import stage
                source = event(state, 'direct_message_verified', service.clock(), row['action_id'])
                import datetime as dt
                stamp = dt.datetime.fromtimestamp(receipt['timestamp'], dt.timezone.utc).isoformat()
                stage(state, account, source, 'direct_messages', dict(person_id=pursuit['person_id'], messages=[dict(id=receipt['message_id'], text=receipt['text'], direction='outbound', occurred_at=stamp, chat_id=receipt['chat_id'])]))
            event(state, 'action_verified', service.clock(), row['action_id'], digest=row['digest'], message_id=receipt['message_id'])

    @staticmethod
    def matches(action, receipt):
        f = action['frozen']
        return (receipt.get('account_id') == f['provider_account_id']
                and receipt.get('self_provider_id') == f['self_provider_id']
                and receipt.get('sender_id') == f['self_provider_id']
                and receipt.get('text') == f['text']
                and set(receipt.get('recipients', [])) == set(f['recipients'])
                and receipt.get('timestamp', 0) >= action['started_at'] - 60
                and receipt.get('timestamp', float('inf')) <= action['started_at'] + 300
                and not (receipt.get('message_id') in action.get('preflight', {}).get('message_ids', [])
                         and receipt.get('chat_id') == action.get('preflight', {}).get('chat_id', f.get('chat_id')))
                and (not f['chat_id'] or receipt.get('chat_id') == f['chat_id'])
                and (not action.get('provider_message_id') or receipt.get('message_id') == action['provider_message_id'])
                and receipt.get('membership_verified') is True)


def product_authorizer(account, state, action):
    """Installed explicitly by the standalone host, never an unconditional callback."""
    authority = state['authority']
    return (action['frozen']['account_id'] == account and authority['external_enabled']
            and not authority['paused'] and not authority['emergency_stop']
            and action['kind'] in authority['allowed_action_kinds']
            and bool(authority.get('enabled_by_user_id')))
