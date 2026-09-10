"""Structured one-step model transport; untrusted data stays in user context."""
import json
from pathlib import Path
from ..providers import _request, _base
from .contracts import require, parse, keys, text

STEPS = {'search_web', 'read_url', 'register_person', 'get_known_relationship',
         'research_phone', 'write_dossier', 'qualify', 'propose_message',
         'classify_reply', 'defer', 'finish'}


class Model:
    def __init__(self, config):
        from functools import partial
        from ..providers import http_request
        self.config = {**config, 'http': config.get('http') or partial(http_request, timeout=45)}
        self.maximum = config.get('max_operation_micro_usd',0)

    def turn(self, context):
        cfg = self.config
        require(cfg.get('provider') in {'openai', 'anthropic'} and cfg.get('model')
                and cfg.get('api_key'), 'model_not_configured', 503)
        data = json.dumps(context, ensure_ascii=False, allow_nan=False)
        require(len(data) <= 30000, 'model_context_limit')
        system = (Path(__file__).parent / 'prompts' / 'chris.md').read_text(encoding='utf-8')
        system += '\nReturn exactly {schema_version:1,step,arguments,evidence_ids,decision_summary} as JSON. Allowed steps: ' + ','.join(sorted(STEPS))
        if cfg['provider'] == 'openai':
            base = _base(cfg.get('base_url', 'https://api.openai.com/v1'), {'api.openai.com'})
            _, response = _request(cfg, 'POST', base + '/chat/completions',
                {'Authorization': 'Bearer ' + cfg['api_key'], 'Content-Type': 'application/json'},
                dict(model=cfg['model'], messages=[dict(role='system', content=system), dict(role='user', content=data)],
                     response_format={'type': 'json_object'}, max_completion_tokens=4096))
            choice = response['choices'][0]
            require(choice['finish_reason'] == 'stop' and not choice['message'].get('tool_calls'), 'model_contract_error')
            raw = choice['message']['content']
        else:
            _, response = _request(cfg, 'POST', 'https://api.anthropic.com/v1/messages',
                {'x-api-key': cfg['api_key'], 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'},
                dict(model=cfg['model'], system=system, messages=[dict(role='user', content=data)], max_tokens=4096))
            require(response.get('stop_reason') == 'end_turn' and len(response['content']) == 1
                    and response['content'][0]['type'] == 'text', 'model_contract_error')
            raw = response['content'][0]['text']
        return validate(parse(raw))


def validate(value):
    keys(value, ['schema_version', 'step', 'arguments', 'evidence_ids', 'decision_summary'])
    require(value['schema_version'] == 1 and value['step'] in STEPS
            and isinstance(value['arguments'], dict), 'model_contract_error')
    require(isinstance(value['evidence_ids'], list) and len(value['evidence_ids']) <= 20, 'model_contract_error')
    text(value['decision_summary'], 1000, 0)
    return value
