"""Seed an explicit local test account in the isolated Supabase project, never production."""
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlparse
import requests

ROOT = Path(__file__).resolve().parents[1]
EMAIL = 'patrick@concierge.test'
PASSWORD = 'Concierge-Test-2026!'

def main():
    result = subprocess.run([shutil.which('npx.cmd') or 'npx', 'supabase', 'status', '-o', 'json'], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8', check=True)
    config = json.loads(result.stdout)
    base = config['API_URL']
    if urlparse(base).hostname not in ('127.0.0.1', 'localhost'):
        raise SystemExit('Refusing to seed a non-local database.')
    session = requests.Session()
    session.headers.update({'apikey': config['SERVICE_ROLE_KEY'], 'Authorization': 'Bearer ' + config['SERVICE_ROLE_KEY']})
    def request(method, path, data=None):
        response = session.request(method, base + path, json=data, timeout=20, headers={'Prefer': 'return=representation'})
        if not response.ok: raise RuntimeError(f'Local seed failed: {path} ({response.status_code}) {response.text[:200]}')
        return response.json() if response.content else None
    users = request('GET', '/auth/v1/admin/users')['users']
    user = next((u for u in users if u['email'] == EMAIL), None)
    if not user: user = request('POST', '/auth/v1/admin/users', {'email': EMAIL, 'password': PASSWORD,
        'email_confirm': True, 'user_metadata': {'full_name': 'Patrick (test workspace)'}})
    profile = request('GET', '/rest/v1/profiles?select=account_id&user_id=eq.' + user['id'])[0]
    account = profile['account_id']
    request('PATCH', '/rest/v1/accounts?id=eq.' + account, {'name': 'AutoSpark Test Workspace'})
    contacts = request('GET', '/rest/v1/contacts?select=id,phone&account_id=eq.' + account)
    for name, phone, email, company in [('Bond Aster (sample)', '+27820000002', 'bond@example.com', 'Value Logic (sample)'),
                                      ('Stuart Willson (sample)', '+27820000003', 'stuart@example.com', 'Pluris (sample)')]:
        if not any(c['phone'] == phone for c in contacts):
            contacts += request('POST', '/rest/v1/contacts', {'account_id': account, 'user_id': user['id'], 'name': name,
                'phone': phone, 'email': email, 'company': company})
    pipelines = request('GET', '/rest/v1/pipelines?select=id&account_id=eq.' + account)
    if not pipelines:
        pipeline = request('POST', '/rest/v1/pipelines', {'account_id': account, 'user_id': user['id'], 'name': 'Introductions'})[0]
        stages = request('POST', '/rest/v1/pipeline_stages', [{'pipeline_id': pipeline['id'], 'name': name, 'position': index,
            'color': color} for index, (name, color) in enumerate([('Researching', '#64748b'), ('In conversation', '#3b82f6'),
                ('Introduced', '#8b5cf6'), ('Meeting booked', '#10b981')])])
        request('POST', '/rest/v1/deals', {'account_id': account, 'user_id': user['id'], 'pipeline_id': pipeline['id'],
            'stage_id': stages[0]['id'], 'contact_id': contacts[0]['id'], 'title': 'Sample referral partnership',
            'value': 0, 'currency': 'ZAR', 'notes': 'Sample opportunity for local workflow testing. No commercial outcome claimed.'})
    print('Local test account ready: ' + EMAIL)
    print('Password on initial creation: ' + PASSWORD)
    print('Sign in at http://127.0.0.1:8316/login. Contacts and pipeline are real local database records with sample content.')

if __name__ == '__main__': main()
