"""Explicit deployment composition; no credentials, grants or enabled defaults.

The host supplies actual human-approval functions. An OS integration must use its
canonical HR12 gate, not an always-true callback. Tests use fake provider IO only.
"""
from .api import create_app
from .live_execution import execute_decision


def create_authorized_app(engine, token, *, whatsapp_gate=None,
                          calendar_authorizer=None, principal_provider_ids=None,
                          worker=False, sync_interval=0):
    if engine.mode != 'live':
        raise ValueError('Authorized host composition requires an explicit live engine')
    for value in (whatsapp_gate, calendar_authorizer):
        if value is not None and not callable(value):
            raise ValueError('Host authorizers must be callable or absent')
    principals = dict(principal_provider_ids or {})

    def execute(runtime, account, decision_id):
        report = runtime.report(account)
        decision = next((d for d in report['decisions'] if d['id'] == decision_id), None)
        if not decision or decision['status'] != 'pending':
            raise ValueError('Pending reviewed decision not found')
        if decision['purpose'] == 'booking':
            if calendar_authorizer is None:
                raise ValueError('Calendar authorization is not installed')
            return runtime.execute_calendar(account,decision_id,authorize=calendar_authorizer)
        if whatsapp_gate is None:
            raise ValueError('WhatsApp authorization is not installed')
        return execute_decision(runtime,account,decision_id,whatsapp_gate,
                                principal_provider_id=principals.get(account))

    def amend(runtime,account,prospect_id,digest):
        return runtime.execute_calendar_amendment(account,prospect_id,digest,
                                                   authorize=calendar_authorizer)

    return create_app(engine,token,worker=worker,sync_interval=sync_interval,
        live_executor=execute if whatsapp_gate is not None or calendar_authorizer is not None else None,
        live_amendment_executor=amend if calendar_authorizer is not None else None)
