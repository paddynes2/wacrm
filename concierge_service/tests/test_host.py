"""Composition tests use Google-shaped fake IO and an isolated execution ledger."""
from fastapi.testclient import TestClient
from concierge_service.host import create_authorized_app
from concierge_service.tests.test_calendar_provider import live_engine
from concierge_service.tests.test_engine_safety import A

TOKEN = 'test-host-private-token-not-a-real-secret'


def test_calendar_composition_routes_only_explicit_authorized_actions(tmp_path):
    engine, rig, did = live_engine(tmp_path)
    url = f'/workspace/{A}/dogfood'
    headers = {'Authorization':'Bearer '+TOKEN}
    absent = TestClient(create_authorized_app(engine,TOKEN),headers=headers)
    assert absent.get(url).json()['readiness']['live_execution_enabled'] is False
    assert absent.post(url,json={'command':'approve','decision_id':did}).status_code == 409
    assert not rig.events
    plans = []
    def authorize(plan):
        plans.append(plan)
        return True  # Fixture gate; only fake IO can be reached by this engine.
    client = TestClient(create_authorized_app(engine,TOKEN,calendar_authorizer=authorize),headers=headers)
    result = client.post(url,json={'command':'approve','decision_id':did})
    assert result.status_code == 200, result.text
    assert result.json()['prospects'][0]['booking']['status'] == 'confirmed'
    assert 'sendUpdates=all' in plans[0]['url']
    prepared = client.post(url,json={'command':'prepare_amendment','prospect_id':'p',
                           'operation':'cancel','source_ref':'test:explicit-owner-cancellation'})
    assert prepared.status_code == 200, prepared.text
    digest = prepared.json()['prospects'][0]['amendment']['digest']
    result = client.post(url,json={'command':'approve_amendment','prospect_id':'p','digest':digest})
    assert result.status_code == 200, result.text
    assert result.json()['prospects'][0]['calendar_status'] == 'cancelled'
    assert result.json()['readiness']['live_delivery_verified'] is False
    assert client.post(url,json={'command':'approve_amendment','prospect_id':'p','digest':digest}).status_code == 409
