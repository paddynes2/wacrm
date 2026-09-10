"""Exa calls go only to the fixed API host; source URLs remain inert inputs."""
import ipaddress
import json
import re
import urllib.parse
from decimal import Decimal
from ..providers import _request
from .contracts import require, text


def public_url(value):
    text(value,2048)
    parsed=urllib.parse.urlsplit(value)
    host=parsed.hostname or ''
    require(parsed.scheme=='https' and host and not parsed.username and not parsed.password and parsed.port in {None,443},'unsafe_source_url')
    require('%' not in host and '\\' not in value and '.' in host and not host.endswith(('.localhost','.local','.internal','.test','.invalid')), 'unsafe_source_url')
    require(host not in {'localhost','metadata.google.internal'} and not re.fullmatch(r'[0-9.]+',host),'unsafe_source_url')
    try: ipaddress.ip_address(host)
    except ValueError: pass
    else: require(False,'unsafe_source_url')
    return value

class Exa:
    def __init__(self, config):
        from functools import partial
        from ..providers import http_request
        self.config={**config, 'http':config.get('http') or partial(http_request,timeout=45)}
        self.maximum=config.get('max_operation_micro_usd',0)
        require(config.get('provider')=='exa' and config.get('api_key'),'research_not_configured',503)
    def call(self, path, body):
        headers,data=_request(self.config,'POST','https://api.exa.ai'+path,{'Content-Type':'application/json','x-api-key':self.config['api_key']},body)
        require(isinstance(data,dict) and isinstance(data.get('results'),list),'provider_schema_changed',503)
        results=[]
        for row in data['results'][:10]:
            require(isinstance(row,dict),'provider_schema_changed',503)
            url=public_url(row.get('url'))
            content=row.get('text','')
            require(isinstance(content,str),'provider_schema_changed',503)
            inaccessible=bool(re.search(r'access denied|verify you are human|sign in to continue|captcha', content[:2000],re.I))
            results.append(dict(url=url,title=str(row.get('title',''))[:500],text=content[:20000],truncated=len(content)>20000,
                                published_at=row.get('publishedDate'),status='inaccessible' if inaccessible else 'success',read=path=='/contents'))
        estimate=data.get('costDollars')
        if isinstance(estimate,dict): estimate=estimate.get('total')
        cost=int(Decimal(str(estimate))*1000000) if estimate is not None else None
        require(cost is None or cost>=0,'provider_cost_invalid',503)
        return dict(results=results,status='success' if results else 'empty',estimated_cost_micro_usd=cost)
    def search(self, query):
        text(query,1000)
        return self.call('/search',dict(query=query,type='auto',numResults=10))
    def read(self,url):
        public_url(url)
        result=self.call('/contents',dict(urls=[url],text=True,maxAgeHours=24))
        for row in result['results']: require(row['url']==url,'redirect_identity_changed',409)
        return result
