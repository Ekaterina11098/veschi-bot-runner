"""Response-only Supabase traffic observation; never changes requests or responses."""
import json,os,atexit,hashlib
from pathlib import Path
from urllib.parse import urlparse
def install(path):
    import requests
    host=urlparse(os.getenv('SUPABASE_URL','')).hostname
    native=requests.sessions.Session.request
    stats=dict(response_body_bytes=0,wire_response_bytes=0,calls=0,by_path={})
    def observed(session,method,url,*args,**kwargs):
        r=native(session,method,url,*args,**kwargs)
        parsed=urlparse(str(url))
        if parsed.hostname==host:
            if kwargs.get('stream'):size=0
            else:size=len(r.content)
            try:wire=int(r.headers.get('Content-Length',size))
            except (ValueError,TypeError):wire=size
            stats['calls']+=1;stats['response_body_bytes']+=size;stats['wire_response_bytes']+=wire
            # Never retain query values, credentials, bodies, or business output.
            stats['by_path'][parsed.path]=stats['by_path'].get(parsed.path,0)+wire
        return r
    requests.sessions.Session.request=observed
    atexit.register(lambda:Path(path).write_text(json.dumps(stats),encoding='utf-8'))
    return stats
def persist(stats,label):
    if not stats.get('calls'):return
    import requests
    from datetime import datetime,timezone,timedelta
    key=os.environ.get('SUPABASE_SECRET_KEY')
    if not key:return
    headers={'apikey':key,'Content-Type':'application/json','Prefer':'resolution=merge-duplicates,return=minimal'}
    if not key.startswith('sb_secret_'):headers['Authorization']='Bearer '+key
    now=datetime.now(timezone.utc)
    ident=hashlib.sha256(label.encode()).hexdigest()[:16]
    record=dict(run_id=os.getenv('GITHUB_RUN_ID'),attempt=os.getenv('GITHUB_RUN_ATTEMPT','1'),task=os.getenv('TASK','unknown'),label=label[:150],observed_at=now.isoformat(),measurement='HTTP response bytes, not billing total',**stats)
    requests.post(os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/telegram_api_cache?on_conflict=cache_key',
        headers=headers,json=dict(cache_key='analytics:egress:worker:'+str(record['run_id'])+':'+record['attempt']+':'+record['task']+':'+ident,payload=record,updated_at=now.isoformat(),expires_at=(now+timedelta(days=90)).isoformat()),timeout=(10,30)).raise_for_status()
