"""CRM is a durable projection; its retry cannot invoke WhatsApp dispatch."""
import json
import urllib.parse
import urllib.request
from uuid import UUID, uuid5
from ..providers import _NoRedirect
from .contracts import digest, require


def stage(state, account, source, kind, payload):
    person = state['people'].get(payload.get('person_id'), {})
    payload = {**payload, 'phone_e164': person.get('phone_e164'), 'synthetic': person.get('synthetic', False)}
    identity = str(uuid5(UUID(account), source['event_id'] + ':' + kind))
    state['projection_outbox'].setdefault(identity, dict(projection_id=identity, account_id=account,
        source_event_id=source['event_id'], kind=kind, payload=payload, payload_digest=digest(payload),
        status='pending', attempts=0, next_attempt_at=0))
    return identity


class Projection:
    def __init__(self, service, base=None, token=None, transport=None):
        self.service, self.base, self.token, self.transport = service, base, token, transport
        if base:
            url = urllib.parse.urlsplit(base)
            require(url.scheme == 'https' or (url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1', '::1'}), 'unsafe_projection_origin')
            require(not url.username and not url.password and not url.query and not url.fragment and url.path in {'', '/'}, 'unsafe_projection_origin')

    def run(self, account, payload=None):
        require(self.base and self.token, 'projection_not_configured', 503)
        state = self.service.snapshot(account)
        ids = [p['projection_id'] for p in state['projection_outbox'].values() if p['status'] != 'acknowledged' and p['next_attempt_at'] <= self.service.clock()][:50]
        if not ids: return
        body = dict(schema_version=1, account_id=account, projection_ids=ids)
        if self.transport:
            self.transport(body)
        else:
            request = urllib.request.Request(self.base.rstrip('/') + '/api/internal/chris/projection', data=json.dumps(body).encode(),
                headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}, method='POST')
            with urllib.request.build_opener(_NoRedirect).open(request, timeout=20) as response:
                require(response.status == 200, 'projection_unavailable', 503)
        with self.service.transaction(account) as (_, state):
            for identity in ids:
                row = state['projection_outbox'][identity]
                row['attempts'] += 1
                row['next_attempt_at'] = self.service.clock() + min(3600, 30 * 2 ** min(row['attempts'], 7))

    def acknowledge(self, account, identity, supplied_digest, result):
        require(result in {'written', 'existing', 'tombstone'}, 'invalid_projection_result')
        with self.service.transaction(account) as (_, state):
            row = self.service.entity(state, 'projection_outbox', identity)
            require(row['payload_digest'] == supplied_digest, 'projection_digest_mismatch', 409)
            row.update(status='acknowledged', acknowledged_at=self.service.clock(), result=result)
            if result == 'tombstone':
                state['people'][row['payload']['person_id']]['crm_tombstone'] = True
            elif row['kind']=='contact':
                state['people'][row['payload']['person_id']]['crm_contact_projected'] = True
