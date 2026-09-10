from copy import deepcopy
import pytest
from concierge_service.chris.provider import Provider
from concierge_service.chris.contracts import ChrisError
from concierge_service.tests.chris_support import SELF,PROSPECT


class Client:
    account_id='synthetic-wa'
    def __init__(self):
        self.account=dict(id=self.account_id,type='WHATSAPP',sources=[{'status':'OK'}])
        self.attendees=[dict(id='self-attendee',account_id=self.account_id,provider_id=SELF,is_self=True),dict(id='prospect-attendee',account_id=self.account_id,provider_id=PROSPECT,is_self=False,phone_number='+15550001003')]
        self.messages=[dict(id='m1',chat_id='direct',sender_id='prospect-attendee',timestamp='2026-09-10T12:00:00+02:00',text='Yes',is_sender=False)]
    def _get(self,path):
        if path.startswith('/accounts/'): return deepcopy(self.account)
        assert path=='/chats/direct';return dict(id='direct',account_id=self.account_id)
    def _pages(self,path):
        if path.endswith('/messages'): return deepcopy(self.messages)
        return deepcopy(self.attendees)


def test_v1_attendee_resolution_original_timestamp_and_identity():
    client=Client();provider=Provider(client);assert provider.connection()['connected']
    batch=provider.read_chat('direct');message=batch['messages'][0]
    assert message['sender_id']==PROSPECT and message['original_timestamp']=='2026-09-10T12:00:00+02:00'
    assert batch['complete'] and 'historical retention unverified' in batch['coverage'].lower()
    assert provider.resolve_identity('+15550001003')['provider_id']==PROSPECT


@pytest.mark.parametrize('field,value',[('type','LINKEDIN'),('id','foreign'),('sources',[])])
def test_unproven_account_contract_disables_capability(field,value):
    client=Client();client.account[field]=value;provider=Provider(client)
    if field=='sources': assert not provider.connection()['connected']
    else:
        with pytest.raises(ChrisError): provider.connection()


@pytest.mark.parametrize('fault',['unknown-sender','foreign-account','naive-time','unproven-self'])
def test_unowned_or_unresolved_message_schema_fails_closed(fault):
    client=Client();provider=Provider(client);provider.connection()
    if fault=='unknown-sender': client.messages[0]['sender_id']='unresolved'
    elif fault=='foreign-account': client.messages[0]['account_id']='foreign'
    elif fault=='naive-time': client.messages[0]['timestamp']='2026-09-10T12:00:00'
    else: client.attendees[0].pop('is_self')
    with pytest.raises((ChrisError,ValueError)): provider.read_chat('direct')


def test_shared_phone_is_ambiguous_not_a_verified_mobile():
    client=Client();provider=Provider(client)
    client.attendees.append(dict(id='other',account_id=client.account_id,provider_id='other',is_self=False,phone_number='+15550001003'))
    with pytest.raises(ChrisError,match='recipient_identity_unresolved'): provider.resolve_identity('+15550001003')
