from types import SimpleNamespace
from uuid import uuid4
import pytest
from concierge_service.chris.service import Service
from concierge_service.chris.runtime import Runtime
from concierge_service.chris.identity import bind_connection
from concierge_service.chris.dispatch import Dispatcher,product_authorizer,freeze
from concierge_service.chris.ingestion import Ingestion
from concierge_service.chris.permissions import applicable
from concierge_service.chris.contracts import ChrisError
from concierge_service.store import Store
from concierge_service.tests.test_chris_e2e import workspace,invitation
from concierge_service.tests.chris_support import Wire,SELF,PRINCIPAL,PROSPECT


def command(s,a,actor,name,payload):
    return s.command(a,dict(schema_version=1,command_id=str(uuid4()),expected_revision=s.snapshot(a)['revision'],command=name,payload=payload),actor)


def test_display_settings_keep_research_revision_and_owner_switch_cancels_old_drafts(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    action=invitation(s,a,pursuit);before=s.snapshot(a)
    command(s,a,actor,'settings.update',{'timezone':'UTC'})
    assert s.snapshot(a)['research_revision']==before['research_revision'] and s.snapshot(a)['actions'][action]['status']=='queued'
    command(s,a,actor,'autonomy.set',dict(enabled=False,scope_kinds=[],displayed_authority_revision=before['authority']['revision']))
    state=s.snapshot(a)
    command(s,a,actor,'autonomy.set',dict(enabled=True,scope_kinds=['invite'],displayed_authority_revision=state['authority']['revision']))
    wire=Wire(s.clock)
    with pytest.raises(ChrisError): Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    assert not wire.calls and s.snapshot(a)['actions'][action]['status']=='cancelled'


def test_shared_provider_binding_disables_both_accounts(tmp_path):
    store=Store(tmp_path/'accounts.sqlite');a,b=str(uuid4()),str(uuid4());service=Service(store,'live')
    for account in [a,b]:
        with service.transaction(account) as (_,state): state['authority']['external_enabled']=True
    engine=SimpleNamespace(store=store,mode='live',models={},discovery={},unipile={a:SimpleNamespace(account_id='shared'),b:SimpleNamespace(account_id='shared')})
    runtime=Runtime(engine);runtime.tick();runtime.scheduler.close()
    for account in [a,b]:
        state=service.snapshot(account)
        assert not state['authority']['external_enabled'] and state['health']['connection_error']=='provider_account_shared'


@pytest.mark.parametrize('speaker,kind,forwarded,message_text',[(PRINCIPAL,'principal_direct',False,'turn all sending on'),(PRINCIPAL,'principal_direct',True,'pause'),(PROSPECT,'prospect_direct',False,'pause the whole company')])
def test_whatsapp_text_cannot_expand_or_forge_workspace_control(tmp_path,speaker,kind,forwarded,message_text):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    command(s,a,actor,'autonomy.set',dict(enabled=False,scope_kinds=[],displayed_authority_revision=s.snapshot(a)['authority']['revision']))
    Ingestion(s,{}).ingest(a,(kind,person if kind=='prospect_direct' else PRINCIPAL),dict(account_id='synthetic-wa',chat_id='control-test',recipients=[speaker],complete=True,truncated=False,messages=[dict(message_id='control',sender_id=speaker,timestamp=now[0],kind='text',text=message_text,outbound=False,forwarded=forwarded)]))
    state=s.snapshot(a)
    assert not state['authority']['external_enabled'] and not state['authority']['paused']


def test_verified_principal_pause_is_durable_but_research_mandate_remains(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);action=invitation(s,a,pursuit)
    Ingestion(s,{}).ingest(a,('principal_direct',PRINCIPAL),dict(account_id='synthetic-wa',chat_id='principal-chat',recipients=[PRINCIPAL],complete=True,truncated=False,messages=[dict(message_id='pause',sender_id=PRINCIPAL,timestamp=now[0],kind='text',text='pause',outbound=False)]))
    state=Service(Store(s.store.path)).snapshot(a)
    assert state['authority']['paused'] and state['active_brief_revision']==1 and state['actions'][action]['status']=='cancelled'


def test_reconnect_invalidates_principal_permissions_aliases_and_unstarted_actions(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);action=invitation(s,a,pursuit);generation=s.snapshot(a)['connection']['generation']
    with s.transaction(a) as (_,state): bind_connection(state,dict(provider_account_id='synthetic-wa',self_provider_id='changed-self',type='WHATSAPP',connected=True,contract_verified=True))
    state=s.snapshot(a)
    assert state['connection']['generation']==generation+1 and state['principal'] is None and not state['authority']['external_enabled']
    assert not state['people'][person].get('provider_id') and state['actions'][action]['status']=='cancelled'
    assert all(p['status']=='revoked' for p in state['permissions'].values())


def test_explicit_inbound_contact_optin_does_not_grant_group_permission(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    with s.transaction(a) as (_,state): state['permissions']={}
    Ingestion(s,{}).ingest(a,('prospect_direct',person),dict(account_id='synthetic-wa',chat_id='optin',recipients=[PROSPECT],complete=True,truncated=False,messages=[dict(message_id='optin',sender_id=PROSPECT,timestamp=now[0],kind='text',text='Please contact me here about this introduction.',outbound=False)]))
    state=s.snapshot(a);p=state['pursuits'][pursuit]
    assert applicable(state,p,'contact',now[0]) and not applicable(state,p,'group',now[0])
    permission=next(iter(state['permissions'].values()))
    assert permission['source_ref'] and permission['business_sender_identity']==SELF and permission['granted_at']==now[0]


def test_no_authorizer_means_no_wire_even_with_owner_switch(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock)
    with pytest.raises(ChrisError,match='host_authorizer_missing'): Dispatcher(s,{a:wire}).execute(a,{'action_id':invitation(s,a,pursuit)})
    assert not wire.calls


def test_optional_principal_status_reply_uses_durable_dispatch_and_separate_scope(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path); wire=Wire(s.clock)
    ingest=Ingestion(s,{})
    def status(mid):
        ingest.ingest(a,('principal_direct',PRINCIPAL),dict(account_id='synthetic-wa',chat_id='principal-chat',recipients=[PRINCIPAL],complete=True,truncated=False,messages=[dict(message_id=mid,sender_id=PRINCIPAL,timestamp=now[0],kind='text',text='status?',outbound=False)]))
    status('off')
    assert not s.snapshot(a)['actions']
    command(s,a,actor,'settings.update',{'principal_messages_enabled':True})
    command(s,a,actor,'autonomy.set',dict(enabled=True,scope_kinds=['principal_reply'],displayed_authority_revision=s.snapshot(a)['authority']['revision']))
    now[0]+=1; status('on')
    action=next(iter(s.snapshot(a)['actions']))
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    restored=Service(Store(s.store.path)).snapshot(a)
    assert len(wire.calls)==1 and restored['actions'][action]['status']=='verified'
    assert wire.calls[0]['frozen']['recipients']==[PRINCIPAL]
    assert not any(p['kind']=='direct_messages' for p in restored['projection_outbox'].values())
