"""Account-scoped CRM lookup through the authenticated projection bridge."""
import json
import urllib.request
from ..providers import _NoRedirect
from .contracts import require


class Relationships:
    def __init__(self, projection):
        self.projection = projection

    def lookup(self, account, person):
        bridge = self.projection
        if not bridge.base or not bridge.token:
            return dict(known=None, fresh=False, coverage='WACRM lookup not configured')
        body = dict(schema_version=1, account_id=account, person_id=person['person_id'])
        request = urllib.request.Request(bridge.base.rstrip('/')+'/api/internal/chris/relationship',
            data=json.dumps(body).encode(), headers={'Authorization':'Bearer '+bridge.token,'Content-Type':'application/json'}, method='POST')
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=20) as response:
            require(response.status == 200, 'relationship_unavailable', 503)
            result = json.loads(response.read(32769))
        require(type(result.get('known')) in (bool,type(None)) and type(result.get('fresh')) is bool and isinstance(result.get('coverage'),str), 'relationship_schema_changed')
        return result
