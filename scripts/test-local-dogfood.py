"""Black-box standalone acceptance, with unique retained loopback-only fixtures.

Uses the existing verified local Supabase test-session helper. No external calls,
live delivery, purchased data, existing account modifications or database reset.
"""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import time

spec = importlib.util.spec_from_file_location('local_fixture', Path(__file__).with_name('test-local-concierge.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def main():
    config = fixture.local_config()
    owner = fixture.User(config, 'standalone')
    url = fixture.WEB + '/api/concierge/dogfood'
    def request(command=None, expected=200, **fields):
        response = fixture.local_request(owner.web, 'POST' if command else 'GET', url,
            **({'json': {'command':command, **fields}} if command else {}))
        value = fixture.checked(response, expected)
        if expected == 200:
            assert value['mode'] == 'simulation'
            assert value['account_id'] == owner.account_id
            assert not value.get('crm_warning'), 'CRM reconciliation requires repair'
        return value
    def wait_for(predicate):
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            report = request()
            if predicate(report): return report
            time.sleep(1)
        raise AssertionError('Durable worker did not reach expected state')
    def person(report, pid):
        return next(p for p in report['prospects'] if p['id'] == pid)
    def approve_pending(report):
        card = next(d for d in reversed(report['decisions']) if d['status'] == 'pending')
        return request('approve', decision_id=card['id'])

    assert request()['prospects'] == []
    request('save_brief',brief={'principal_name':'QA principal','offer':'Synthetic workflow assessment',
        'audience':'Synthetic operations directors','geography':'South Africa','exclusions':'Existing customers',
        'claims':'Test only','timezone':'Africa/Johannesburg','booking_link':'','budget_usd':0})
    request('discover',source='fixture',limit=2)
    report = wait_for(lambda r: len(r['prospects']) == 2)
    pid, stopped = [p['id'] for p in report['prospects']]
    request('research',prospect_id=pid)
    wait_for(lambda r: person(r,pid).get('qualification') == 'qualified')
    request('enrich',prospect_id=pid,phone='+27820000123',source_ref='simulation:synthetic-number-never-contact')
    report = request('promote',prospect_id=pid)
    contact_id = person(report,pid)['contact_id']
    assert person(request('promote',prospect_id=pid),pid)['contact_id'] == contact_id
    request('start',prospect_id=pid)
    wait_for(lambda r: len(r['messages']) == 1)
    request('reply',prospect_id=pid,text='What does the offer involve?')
    report = wait_for(lambda r: len(r['messages']) == 3)
    for scope in ('introduction','group','scheduling','booking'):
        for party in ('principal','recipient'):
            request('consent',prospect_id=pid,scope=scope,party=party,source_ref='simulation:explicit-test-agreement')
    report = approve_pending(request('introduce',prospect_id=pid))
    assert report['metrics']['introduced'] == 1
    start = datetime.now(timezone.utc) + timedelta(days=1)
    report = request('propose',prospect_id=pid,start=start.isoformat(),end=(start+timedelta(days=7)).isoformat(),timezone='Africa/Johannesburg')
    slot = person(report,pid)['calendar']['slots'][0]
    report = approve_pending(request('book',prospect_id=pid,start=slot['start'],end=slot['end']))
    assert report['metrics']['booked'] == 1
    report = request('prepare_amendment',prospect_id=pid,operation='cancel',source_ref='simulation:agreed-cancellation')
    card = person(report,pid)['amendment']
    report = request('approve_amendment',prospect_id=pid,digest=card['digest'])
    assert person(report,pid)['calendar_status'] == 'cancelled'
    request('review',prospect_id=pid,useful=True,minutes=5,note='Synthetic acceptance outcome, not product traction')
    request('qualify',prospect_id=stopped,verdict='qualified',reason='Synthetic STOP test')
    request('start',prospect_id=stopped)
    wait_for(lambda r: any(m['prospect_id']==stopped and m['direction']=='outbound' for m in r['messages']))
    request('reply',prospect_id=stopped,text='STOP')
    report = request('process')
    assert person(report,stopped)['conversation']['status'] == 'opted_out'
    assert report['metrics']['customer_minutes'] == 5 and report['metrics']['cost_usd'] == 0
    assert report['readiness']['live_delivery_verified'] is False
    cross = fixture.local_request(owner.web,'POST',url,headers={'Origin':'http://foreign.invalid'},json={'command':'process'})
    assert cross.status_code == 403
    foreign = fixture.User(config,'standalone-foreign')
    foreign_response = fixture.checked(fixture.local_request(foreign.web,'GET',url))
    assert foreign_response['prospects'] == []
    assert fixture.local_request(foreign.web,'POST',url,json={'command':'takeover','prospect_id':pid}).status_code == 409
    messages = owner.inbox({'id':contact_id})
    assert len(messages) == 3, 'Introduction/booking must not leak into a direct inbox'
    assert all(m['content_text'].startswith('[Simulation] ') for m in messages)
    notes = fixture.checked(fixture.local_request(owner.rest,'GET',owner.base+
        f'/rest/v1/contact_notes?contact_id=eq.{contact_id}&select=id,note_text'))
    assert len([n for n in notes if 'Calendar cancellation verified.' in n['note_text']]) == 1
    request('reconcile')
    repeated = fixture.checked(fixture.local_request(owner.rest,'GET',owner.base+
        f'/rest/v1/contact_notes?contact_id=eq.{contact_id}&select=id,note_text'))
    assert {n['id'] for n in repeated} == {n['id'] for n in notes}, 'Outcome reconciliation duplicated notes'
    print(f'PASS: {fixture.COUNT} loopback HTTP requests; durable automatic replies, CRM dedup, introduction, booking/cancellation, STOP, isolation and cost labels.')
    print('Unique test fixtures retained; no live sends or provider charges.')


if __name__ == '__main__':
    main()
