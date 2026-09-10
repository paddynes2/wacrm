"""Private authenticated routes. Actor claims only come from the WACRM server."""
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from . import contracts as c


def install(app, service, auth, projection):
    def fail(exc):
        return JSONResponse({'error': {'code': exc.code, 'message': exc.code.replace('_', ' '), 'retryable': False}}, status_code=exc.status,
                            headers={'Cache-Control': 'private, no-store'})

    @app.get('/workspace/{account}/chris', dependencies=[Depends(auth)])
    def overview(account: str):
        try:
            c.uid(account)
            return JSONResponse(service.overview(account), headers={'Cache-Control': 'private, no-store'})
        except c.ChrisError as exc: return fail(exc)

    @app.post('/workspace/{account}/chris/commands', dependencies=[Depends(auth)])
    async def command(account: str, request: Request):
        try:
            c.uid(account)
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk); c.require(len(raw) <= c.MAX_BODY, 'body_too_large', 413)
            body = c.parse(bytes(raw))
            c.keys(body, ['actor', 'envelope'])
            from starlette.concurrency import run_in_threadpool
            result = await run_in_threadpool(service.command, account, body['envelope'], body['actor'])
            return JSONResponse(result, status_code=202, headers={'Cache-Control': 'private, no-store'})
        except c.ChrisError as exc: return fail(exc)

    @app.get('/workspace/{account}/chris/{collection}', dependencies=[Depends(auth)])
    def listing(account: str, collection: str, cursor: str = '', limit: int = 25):
        try:
            c.uid(account); c.integer(limit, 100, 1)
            c.require(collection in {'people', 'introductions', 'activity', 'export'}, 'not_found', 404)
            state = service.snapshot(account)
            if collection == 'export': return state
            rows = state['events'] if collection == 'activity' else list(state[collection].values())
            rows = sorted(rows, key=lambda x: str(x.get('observed_seq', 0)).zfill(20) + str(x.get('person_id', x.get('intro_id', ''))))
            offset = 0
            if cursor:
                import base64
                try:
                    decoded = c.parse(base64.urlsafe_b64decode(cursor))
                    c.require(decoded['account'] == account and decoded['collection'] == collection, 'invalid_cursor')
                    offset = c.integer(decoded['offset'])
                except (ValueError, KeyError): raise c.ChrisError('invalid_cursor') from None
            page = rows[offset:offset + limit]
            if collection == 'people':
                from .state import pursuit_for
                page = [{**p, 'pursuit': pursuit_for(state, p['person_id'])} for p in page]
            import base64
            next_cursor = base64.urlsafe_b64encode(c.canonical(dict(account=account, collection=collection, offset=offset + limit))).decode() if offset + limit < len(rows) else None
            return dict(schema_version=1, revision=state['revision'], items=page, next_cursor=next_cursor)
        except c.ChrisError as exc: return fail(exc)

    @app.get('/workspace/{account}/chris/{collection}/{identity}', dependencies=[Depends(auth)])
    def detail(account: str, collection: str, identity: str):
        try:
            c.uid(account)
            c.require(collection in {'people', 'introductions', 'commands', 'projections'}, 'not_found', 404)
            state = service.snapshot(account)
            row = service.entity(state, 'projection_outbox' if collection == 'projections' else collection, identity)
            if collection == 'people':
                from .state import pursuit_for
                p = pursuit_for(state, identity)
                row = {**row, 'pursuit': p, 'dossier': service.blobs.get(row['dossier_ref']) if row.get('dossier_ref') else None,
                       'business_sender_identity': (state['connection'] or {}).get('self_provider_id'),
                       'permissions': [v for v in state['permissions'].values() if v.get('subject_provider_id') == row.get('provider_id')],
                       'thread': state['threads'].get(p.get('direct_thread_key')), 'actions': [a for a in state['actions'].values() if a['pursuit_id'] == p['pursuit_id']]}
                source_ids = {sid for fact in (row['dossier'] or {}).get('facts',[]) for sid in fact['source_ids']}
                row['sources'] = {sid:state['sources'][sid] for sid in source_ids if sid in state['sources']}
            if collection == 'introductions':
                row = {**row, 'threads': [t for t in state['threads'].values() if t['owner_entity_id'] == identity],
                       'actions': [a for a in state['actions'].values() if a.get('intro_id') == identity]}
            return dict(schema_version=1, revision=state['revision'], item=row)
        except c.ChrisError as exc: return fail(exc)

    @app.post('/workspace/{account}/chris/projections/{identity}/claim', dependencies=[Depends(auth)])
    async def claim_projection(account: str, identity: str, request: Request):
        try:
            c.uid(account)
            body = c.parse(await request.body())
            c.keys(body, ['digest'])
            with service.transaction(account) as (_, state):
                row = service.entity(state, 'projection_outbox', identity)
                c.require(row['kind'] == 'contact' and row['payload_digest'] == body['digest'], 'projection_digest_mismatch', 409)
                c.require(not state['people'][row['payload']['person_id']].get('crm_tombstone'), 'contact_tombstone', 409)
                c.require(not row.get('contact_creation_claimed'), 'contact_creation_uncertain', 409)
                c.require(not any(other['projection_id'] != identity and other['kind'] == 'contact'
                    and other['payload']['person_id'] == row['payload']['person_id'] and other.get('contact_creation_claimed')
                    for other in state['projection_outbox'].values()), 'contact_creation_uncertain', 409)
                row['contact_creation_claimed'] = True
            return {'claimed': True}
        except c.ChrisError as exc: return fail(exc)

    @app.post('/workspace/{account}/chris/projections/{identity}/ack', dependencies=[Depends(auth)])
    async def acknowledge(account: str, identity: str, request: Request):
        try:
            c.uid(account)
            body = c.parse(await request.body())
            c.keys(body, ['digest', 'result'])
            projection.acknowledge(account, identity, body['digest'], body['result'])
            return {'status': 'acknowledged'}
        except c.ChrisError as exc: return fail(exc)
