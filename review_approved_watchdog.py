"""Restart only the isolated approved publisher; never call WB or modify approvals."""
import os,json,time,hmac,hashlib,urllib.request
WORKFLOW='review-approved-publication.yml'
def should_dispatch(cfg,pending,runs):
    if not all(cfg.get(k) for k in ('enabled','publication_enabled','destination_verified')):return False
    if not pending:return False
    return not any(r.get('status') in ('queued','in_progress','waiting','pending','requested') for r in runs)
def main():
    import psycopg
    from review_approved_worker import due_intents
    root=os.environ['SUPABASE_SECRET_KEY'].encode()
    pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15,options='-c statement_timeout=30000') as conn:
        from review_telegram_approval import Repository
        repo=Repository(conn,postgres=True)
        conn.execute("SELECT pg_advisory_lock(hashtextextended('review-approved-watchdog-v1',0))")
        row=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()
        cfg=dict(row[0]) if row else {}
        group=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:content-group:v1'").fetchone()
        if group and group[0].get('enabled') and group[0].get('destination_verified'):cfg['content_group_chat_id']=str(group[0]['chat_id'])
        pending=due_intents(repo,cfg) if cfg.get('cutover') is not None else []
        base='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/workflows/'+WORKFLOW
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
        with urllib.request.urlopen(urllib.request.Request(base+'/runs?per_page=100',headers=headers),timeout=30) as response:runs=json.load(response)['workflow_runs']
        dispatch=should_dispatch(cfg,pending,runs)
        if dispatch:
            # A single dispatch under the controller lock. If HTTP is uncertain,
            # the next event checks active runs before it can dispatch again.
            req=urllib.request.Request(base+'/dispatches',data=json.dumps({'ref':'main'}).encode(),headers=dict(headers,**{'Content-Type':'application/json'}),method='POST')
            with urllib.request.urlopen(req,timeout=30) as response:
                if response.status!=204:raise RuntimeError('Publisher wake not confirmed')
        with repo.transaction():
            repo.put('events','approved-worker:watchdog:v1',dict(checked_at=time.time(),run_id=os.getenv('GITHUB_RUN_ID'),code_commit=os.getenv('GITHUB_SHA'),dispatched=dispatch,pending_cabinets=len(pending),active_runs=sum(r.get('status') in ('queued','in_progress','waiting','pending','requested') for r in runs)))
        print(json.dumps({'dispatched':dispatch,'pending_cabinets':len(pending)}))
if __name__=='__main__':main()
