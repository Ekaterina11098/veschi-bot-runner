"""Recover only today's morning collection; no WB or Telegram write access."""
import os,json,time,hmac,hashlib,urllib.request
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
ACTIVE={'queued','in_progress','waiting','pending','requested'}
TARGETS=(('reviews','reviews-morning.yml'),('questions','questions-morning.yml'))
def choose(now,cfg,states,runs,last_attempt=0):
    local=now.astimezone(ZoneInfo('Europe/Moscow'))
    if not 480<=local.hour*60+local.minute<780:return None
    if not all(cfg.get(k) for k in ('enabled','new_notices_enabled','destination_verified')):return None
    if now.timestamp()-last_attempt<300:return None
    if any(r.get('status') in ACTIVE for rs in runs.values() for r in rs):return None
    # Give the other kind its first turn before resuming a long partial collection.
    pending=[kind for kind,_ in TARGETS if not (
        states.get(kind,{}).get('status')=='complete' and
        all(states[kind].get('scopes',{}).get(c,{}).get('status')=='complete'
            for c in ('token_1','token_2','token_3')))]
    return next((k for k in pending if not states.get(k)),pending[0] if pending else None)
def main():
    import psycopg
    from review_telegram_approval import Repository
    root=os.environ['SUPABASE_SECRET_KEY'].encode()
    pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15,options='-c statement_timeout=30000') as conn:
        repo=Repository(conn,postgres=True)
        conn.execute("SELECT pg_advisory_lock(hashtextextended('review-morning-watchdog-v1',0))")
        cfgrow=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()
        cfg=dict(cfgrow[0]) if cfgrow else {}
        group=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:content-group:v1'").fetchone()
        if not group or not group[0].get('enabled') or not group[0].get('destination_verified'):cfg={}
        now=datetime.now(timezone.utc);day=now.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
        states={k:repo.get('events',k+'-morning:'+day) or {} for k,_ in TARGETS}
        base='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/workflows/'
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'}
        runs={}
        for kind,workflow in TARGETS:
            with urllib.request.urlopen(urllib.request.Request(base+workflow,headers=headers),timeout=30) as r:meta=json.load(r)
            if meta.get('state')!='active':raise RuntimeError('Morning workflow disabled: '+kind)
            with urllib.request.urlopen(urllib.request.Request(base+workflow+'/runs?per_page=100',headers=headers),timeout=30) as r:runs[kind]=json.load(r)['workflow_runs']
        event_id='morning-watchdog:'+day
        previous=repo.get('events',event_id) or {}
        selected=choose(now,cfg,states,runs,previous.get('attempt_at',0))
        record=dict(previous,checked_at=now.timestamp(),run_id=os.getenv('GITHUB_RUN_ID'),code_commit=os.getenv('GITHUB_SHA'),selected=selected)
        if selected:
            # Durable BEFORE HTTP: unknown dispatch waits, then checks real active runs.
            record.update(attempt_at=now.timestamp(),dispatch_status='unknown')
            with repo.transaction():repo.put('events',event_id,record)
            workflow=dict(TARGETS)[selected]
            request=urllib.request.Request(base+workflow+'/dispatches',data=b'{"ref":"main"}',headers=dict(headers,**{'Content-Type':'application/json'}),method='POST')
            with urllib.request.urlopen(request,timeout=30) as r:
                if r.status!=204:raise RuntimeError('Morning dispatch unconfirmed')
            record['dispatch_status']='accepted'
        with repo.transaction():repo.put('events',event_id,record)
        print(json.dumps({'selected':selected,'states':{k:v.get('status','missing') for k,v in states.items()}}))
if __name__=='__main__':main()
