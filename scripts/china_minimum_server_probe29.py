"""Server-only TinyFish profile access probe. Does not open WB or write marketplace state."""
import os,json,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache
CONFIG='china_agent:minimum_browser:profile:v1'
LATEST='china_agent:minimum_browser_server_probe:latest:v1'
def probe(config,key):
 out=dict(status='configuration_required',wb_writes=0,telegram_sends=0,minimum_writer_enabled=False)
 if not config or not config.get('profile_id'):return dict(out,reason='WB browser profile configuration missing')
 if not key:return dict(out,reason='TINYFISH_API_KEY missing',required_secret='TINYFISH_API_KEY')
 try:r=requests.get('https://agent.tinyfish.ai/v1/profiles',headers={'X-API-Key':key},timeout=30)
 except requests.RequestException:return dict(out,status='blocked',reason='TinyFish profile API transport error')
 if not r.ok:return dict(out,status='blocked',reason='TinyFish profile API HTTP '+str(r.status_code))
 try:rows=r.json()['profiles']
 except (ValueError,TypeError,KeyError):return dict(out,status='blocked',reason='TinyFish profile API response invalid')
 matches=[p for p in rows if p.get('id')==config['profile_id']]
 if len(matches)!=1:return dict(out,status='blocked',reason='Configured profile is not visible to this server key')
 p=matches[0]
 return dict(out,status='profile_access_verified',profile_id=p['id'],saved_domains=p.get('domain_count'),browser_login_verified=False,reason='Server API can access configured profile; separate live WB identity/readback still required')
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Registered public main only')
 c=Cache();out=probe(c.get(CONFIG),os.environ.get('TINYFISH_API_KEY'))
 out.update(observed_at=datetime.now(timezone.utc).isoformat(),run_id=os.environ['GITHUB_RUN_ID'])
 audit='china_agent:minimum_browser_server_probe:v1:'+out['run_id']
 if not c.create(audit,out):raise ValueError('Existing immutable probe result')
 c.put(LATEST,dict(out,audit_key=audit))
 print(json.dumps({k:out[k] for k in ['status','wb_writes','telegram_sends','minimum_writer_enabled']}))
if __name__=='__main__':main()
