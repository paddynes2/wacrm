"""Loopback-only QA host: real private Chris API plus synthetic Supabase I/O.

Never use with a live DB or credentials. The executable explicitly creates its
own simulation store and its auth provider accepts only the synthetic QA user.
"""
import argparse
import base64
import json
from pathlib import Path
import time
from uuid import uuid4
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from concierge_service.api import create_app
from concierge_service.engine import Engine
from concierge_service.store import Store

TOKEN = 'synthetic-chris-qa-token-not-a-real-credential'
ACCOUNT = 'e89ab10e-a785-4ca3-a591-9d3c1b3c4b5d'
USER = '5db9ee8c-8fca-4c6c-9dda-a73e4ec91931'


def build(path):
    crm_path = Path(path).with_suffix('.crm.json')
    crm = json.loads(crm_path.read_text()) if crm_path.exists() else {t: [] for t in ['contacts', 'contact_notes', 'conversations', 'messages']}
    def selected(table, request):
        return [row for row in crm[table] if all(not value.startswith('eq.') or str(row.get(key)) == value[3:] for key, value in request.query_params.items())]
    def persist():
        crm_path.write_text(json.dumps(crm, indent=2), encoding='utf-8')
    engine = Engine(Store(path), mode='simulation')
    app = create_app(engine=engine, token=TOKEN, worker=False)
    app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:18762'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
    user = dict(id=USER, aud='authenticated', role='authenticated', email='qa@example.test', app_metadata={'provider':'email'}, user_metadata={'full_name':'Alex QA'}, created_at='2026-09-10T00:00:00Z')
    def session():
        encode = lambda v: base64.urlsafe_b64encode(json.dumps(v).encode()).decode().rstrip('=')
        jwt = encode({'alg':'HS256','typ':'JWT'}) + '.' + encode(dict(sub=USER, exp=int(time.time())+86400, role='authenticated', aud='authenticated', iss='synthetic-qa')) + '.synthetic-signature'
        return dict(access_token=jwt, token_type='bearer', expires_in=86400, expires_at=int(time.time())+86400, refresh_token='synthetic-refresh-token', user=user)
    @app.post('/auth/v1/token')
    async def login(request: Request):
        body=await request.json()
        if body.get('email')!='qa@example.test' and body.get('refresh_token')!='synthetic-refresh-token': return JSONResponse({'error':'synthetic_user_required'},status_code=401)
        return session()
    @app.get('/auth/v1/user')
    def who(request: Request):
        if not request.headers.get('authorization','').endswith('.synthetic-signature'): return JSONResponse({'error':'invalid_synthetic_token'},status_code=401)
        return user
    @app.get('/rest/v1/{table}')
    def rows(table: str, request: Request):
        if table=='profiles': value=dict(id=USER,user_id=USER,account_id=ACCOUNT,account_role='owner',role='admin',full_name='Alex QA',email='qa@example.test',beta_features=[])
        elif table=='accounts': value=dict(id=ACCOUNT,name='Chris simulation QA',default_currency='USD')
        elif table in crm:
            result = selected(table, request)
            return JSONResponse((result[0] if result else None) if 'object+json' in request.headers.get('accept','') else result)
        else: return JSONResponse([],headers={'Content-Range':'0-0/0'})
        return value if 'object+json' in request.headers.get('accept','') else [value]
    @app.post('/rest/v1/{table}')
    async def store_fixture(table: str, request: Request):
        # Presence/notifications are irrelevant to Chris acceptance and cannot
        # mutate any external CRM. Unexpected business tables fail loudly.
        if table in crm:
            body = await request.json()
            assert isinstance(body, dict)
            assert body.get('account_id', ACCOUNT) == ACCOUNT
            if table == 'messages':
                assert any(c['id'] == body['conversation_id'] for c in crm['conversations'])
            duplicate = next((r for r in crm[table] if (body.get('id') and r.get('id') == body['id']) or
                (table == 'contacts' and r.get('phone') == body.get('phone')) or
                (table == 'conversations' and r.get('contact_id') == body.get('contact_id')) or
                (table == 'messages' and r.get('conversation_id') == body.get('conversation_id') and r.get('message_id') == body.get('message_id'))), None)
            if duplicate:
                if 'resolution=ignore-duplicates' in request.headers.get('prefer', ''): return JSONResponse(None, status_code=201)
                return JSONResponse({'code':'23505','message':'synthetic unique constraint'},status_code=409)
            body.setdefault('id', str(uuid4()))
            if table == 'contacts': body['phone_normalized'] = body['phone'].lstrip('+')
            crm[table].append(body); persist()
            return JSONResponse(body if 'object+json' in request.headers.get('accept','') else [body], status_code=201)
        if table not in {'user_presence','presence','notifications'}: return JSONResponse({'error':'unexpected_fixture_write'},status_code=409)
        return JSONResponse({},status_code=201)
    @app.patch('/rest/v1/{table}')
    async def update_fixture(table: str, request: Request):
        assert table == 'conversations'
        body = await request.json()
        for row in selected(table, request):
            if not row.get('last_message_at') or row['last_message_at'] <= body['last_message_at']: row.update(body)
        persist()
        return JSONResponse(None)
    @app.post('/rest/v1/rpc/touch_presence')
    def presence():
        return JSONResponse(None)
    with app.state.chris.service.transaction(ACCOUNT) as (_,state):
        state['health']['heartbeat']=time.time()
    return app


if __name__=='__main__':
    import uvicorn
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True);parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args()
    target=Path(args.db).resolve()
    require_root=Path(__file__).resolve().parents[2]/'.local'
    assert target.is_relative_to(require_root) and target.name.startswith('qa-')
    uvicorn.run(build(target),host='127.0.0.1',port=args.port,log_level='warning')
