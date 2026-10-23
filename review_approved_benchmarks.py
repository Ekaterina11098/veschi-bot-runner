"""Copy only immutable owner-approved revisions to the existing example library."""
import json,time,os,hmac,hashlib,urllib.request
from review_telegram_approval import sha
PREFIX='approved-benchmark:'
STATES=('awaiting_preflight','verify','confirmed')
def candidates(cards,events,intents,owner):
    result={}
    edits=[(k,e) for k,e in events.items() if k.startswith('edit:') and str(e.get('actor'))==str(owner) and e.get('decision')=='revision_requested']
    for intent_id,i in sorted(intents.items(),key=lambda kv:kv[1].get('created_at',0)):
        if i.get('status') not in STATES or str(i.get('owner_id'))!=str(owner) or i.get('authorization_channel')=='automatic_policy':continue
        c=cards.get(i.get('card_token'),{})
        answer=i.get('answer','')
        if not answer or sha(answer)!=i.get('answer_sha256') or sha(c.get('source'))!=i.get('source_sha256'):continue
        if any(i.get(k)!=c.get(k) for k in ('ref','cabinet','kind','item_id','version')):continue
        if i.get('answer_sha256') not in c.get('hashes',[]):continue
        matches=[]
        for event_id,e in edits:
            old=cards.get(e.get('token'),{})
            if old.get('ref')!=i['ref'] or e.get('version')!=old.get('version'):continue
            if str(e.get('instruction','')).strip()!=answer:continue
            # Exact revision lineage, never a similar or unconfirmed free-text draft.
            if i['version']!=old['version']+'-edit-'+sha(event_id)[:8]:continue
            originals=old.get('texts') or []
            if not originals or answer in originals:continue
            matches.append((event_id,originals[0]))
        if len(matches)!=1:continue
        src=c['source'];event_id,original=matches[0]
        key=i['item_id'] if i['cabinet']=='token_1' and i['kind']=='feedbacks' else 'veschi-review:'+i['cabinet']+':'+i['kind']+':'+i['item_id']
        row=dict(feedback_id=key,product_name='',supplier_article=src.get('article') or '',
            rating=src.get('rating') or 0,review_text=src.get('text') or '',pros=src.get('pros') or '',cons=src.get('cons') or '',
            original_draft=original,edited_answer=answer)
        result[key]=dict(intent_id=intent_id,revision_event_id=event_id,cabinet=i['cabinet'],kind=i['kind'],answer_sha256=i['answer_sha256'],row=row)
    return list(result.values())
def sync(repo,owner,write,read,clock=time.time):
    def table(name):return {k:json.loads(v) for k,v in repo.execute('SELECT id,payload FROM {p}'+name).fetchall()}
    cards,events,intents=table('cards'),table('events'),table('intents')
    report=dict(saved=0,existing=0,errors=0,cabinets={})
    for entry in candidates(cards,events,intents,owner):
        key=PREFIX+entry['intent_id'];old=events.get(key) or {}
        if old.get('status')=='confirmed' and old.get('answer_sha256')==entry['answer_sha256']:
            report['existing']+=1;continue
        if old.get('retry_at',0)>clock():continue
        receipt={k:entry[k] for k in ('intent_id','revision_event_id','cabinet','kind','answer_sha256')}
        try:
            write(entry['row'])
            actual=read(entry['row']['feedback_id'])
            if not actual or any(actual.get(k)!=v for k,v in entry['row'].items()):raise RuntimeError('Benchmark readback mismatch')
            receipt.update(status='confirmed',checked_at=clock())
            report['saved']+=1;report['cabinets'][entry['cabinet']]=report['cabinets'].get(entry['cabinet'],0)+1
        except Exception as exc:
            receipt.update(status='retry',error_type=type(exc).__name__,retry_at=clock()+60,checked_at=clock());report['errors']+=1
        with repo.transaction():repo.put('events',key,receipt)
    return report
def sync_live(repo,owner):
    from urllib.parse import urlencode
    base=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/review_benchmarks'
    secret=os.environ['SUPABASE_SECRET_KEY']
    headers={'apikey':secret,'Authorization':'Bearer '+secret,'Content-Type':'application/json'}
    def request(method,params,payload=None):
        body=None if payload is None else json.dumps(payload,ensure_ascii=False).encode()
        req=urllib.request.Request(base+'?'+urlencode(params),data=body,headers=dict(headers,Prefer='resolution=merge-duplicates,return=representation'),method=method)
        with urllib.request.urlopen(req,timeout=15) as response:
            text=response.read().decode();return json.loads(text) if text.strip() else []
    def write(row):request('POST',{'on_conflict':'feedback_id'},dict(row,updated_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()))
    def read(key):
        rows=request('GET',{'feedback_id':'eq.'+key,'select':'*','limit':'1'})
        return rows[0] if rows else None
    # One saver at a time prevents an older approved version overwriting a newer one.
    locked=repo.execute("SELECT pg_try_advisory_lock(hashtextextended(?,0))",('review-benchmark-sync-v1',)).fetchone()[0]
    if not locked:return dict(busy=True)
    try:return sync(repo,owner,write,read)
    finally:repo.execute("SELECT pg_advisory_unlock(hashtextextended(?,0))",('review-benchmark-sync-v1',))
def main():
    import psycopg
    from review_telegram_approval import Repository
    root=os.environ['SUPABASE_SECRET_KEY'].encode()
    pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15) as conn:
        repo=Repository(conn,postgres=True)
        cfg=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()[0]
        result=sync_live(repo,str(cfg['owner_id']))
        with repo.transaction():repo.put('events','approved-benchmark:backfill:20261023:v1',dict(result=result,checked_at=time.time(),run_id=os.getenv('GITHUB_RUN_ID'),code_commit=os.getenv('GITHUB_SHA')))
        print(json.dumps(result))
        if result.get('errors'):raise RuntimeError('Some approved examples require retry')
if __name__=='__main__':main()
