"""Opt-in qualitative research evaluation; never composes a send dispatcher."""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4
from .contracts import require

RUBRIC = ['commercial relevance','retained factual support','source independence and currency',
          'useful breadth','explicit uncertainty','public/confidential separation','valid tool contracts']


def report(service, account):
    state=service.snapshot(account)
    return dict(mode=service.mode, rubric=RUBRIC, human_quality_review='not_performed',
        live_acceptance_verified=False, research_revision=state['research_revision'],
        candidates=[dict(person_id=p['person_id'],display_name=p['display_name'],
            dossier=service.blobs.get(p['dossier_ref']) if p.get('dossier_ref') else None) for p in state['people'].values()],
        paid_reservations=[dict(tool_name=r['tool_name'],status=r['status'],reserved_micro_usd=r['cost_reservation_micro_usd'],
            estimated_micro_usd=r.get('estimated_cost_micro_usd'),reported_micro_usd=r.get('reported_cost_micro_usd')) for r in state['tool_runs'].values()],
        external_mutations_started=sum(bool(a.get('started_at')) for a in state['actions'].values()))


def main():
    parser=argparse.ArgumentParser(description='Evaluate configured Chris research with existing host ceilings. Does not send messages.')
    parser.add_argument('--account',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--run-paid-research',action='store_true',help='Explicitly opt into configured model/search operations; requires separately approved host allowance.')
    args=parser.parse_args()
    target=Path(args.output).resolve();require(not target.exists(),'evaluation_output_must_be_new')
    from ..api import configured_engine,mapping
    from .service import Service
    engine=configured_engine();service=Service(engine.store,engine.mode,mapping('CONCIERGE_CHRIS_SETTINGS_JSON'))
    if args.run_paid_research:
        from .runtime import Runtime
        runtime=Runtime(engine,mapping('CONCIERGE_CHRIS_SETTINGS_JSON'),
            projection_base=os.environ.get('CONCIERGE_WACRM_INTERNAL_URL'),token=os.environ.get('WACRM_BRIDGE_TOKEN'))
        try: runtime.research.run(args.account,{'pass_id':str(uuid4())})
        finally: runtime.scheduler.close()
    result=report(service,args.account)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(report=str(target),human_quality_review='not_performed',paid_research_requested=args.run_paid_research)))


if __name__=='__main__': main()
