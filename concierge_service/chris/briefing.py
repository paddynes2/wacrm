"""Propose an editable brief; only the reviewed activation command adopts it."""
from .agent import validate
from .contracts import keys, text, require, brief
from .scheduler import reserve, bounded_job
from .state import event


class Briefing:
    def __init__(self, service, models): self.service,self.models=service,models

    @bounded_job
    def run(self, account, payload):
        initial=self.service.snapshot(account)
        proposal=self.service.entity(initial,'proposals',payload['proposal_id'])
        require(account in self.models,'model_not_configured',503)
        run,fresh=reserve(self.service,account,'brief_interpretation',dict(proposal_id=payload['proposal_id']),getattr(self.models[account],'maximum',100000))
        require(fresh,'paid_result_unknown',409)
        result=validate(self.models[account].turn(dict(task='propose_structured_brief',
            instruction='Return finish with arguments brief. Brief fields: objective, principal_display_name, principal_public_context, timezone, candidate_archetypes, geography_include, geography_exclude, explicit_exclusions, confidentiality_rules. Use only facts from the supplied user text and previously approved brief. Unknown required strings are empty; unspecified geography/archetypes are empty arrays, never a default region or industry. Do not invent a principal name or offer. Keep private objectives out of public context. This proposal will be reviewed in the console and cannot activate itself.',
            user_text=proposal['text'],previous_brief=initial['brief_versions'].get(str(initial['active_brief_revision'])))))
        require(result['step']=='finish','model_contract_error');keys(result['arguments'],['brief'])
        proposed=result['arguments']['brief']
        keys(proposed,['objective','principal_display_name','principal_public_context','timezone'],
            ['candidate_archetypes','geography_include','geography_exclude','explicit_exclusions','confidentiality_rules'])
        for key in ['objective','principal_display_name','principal_public_context','timezone']: text(proposed[key],4000,0)
        # Validate optional fields without manufacturing values in the saved draft.
        brief({**proposed,'objective':proposed['objective'] or 'Review required','principal_display_name':proposed['principal_display_name'] or 'Review required','timezone':proposed['timezone'] or 'UTC'})
        ref=self.service.blobs.put(result)
        with self.service.transaction(account) as (_,state):
            state['tool_runs'][run['run_id']].update(status='completed',output_ref=ref)
            current=state['proposals'][payload['proposal_id']]
            if current.get('reviewed') or state['research_revision']!=initial['research_revision']: return
            current.update(suggested_brief=proposed,interpretation_ref=ref)
            event(state,'brief_interpreted',self.service.clock(),payload['proposal_id'])
