"""Owner-approved exact two MS product article edits; no documents or stock changes."""
import json,time
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest,Stopped
from stock_execution_fence import cloud_writer
ROOT='technical:owner-furcoat-ms-article-fix:2026-11-10'
TARGETS=[('1- furcoat-whitemelange','1-furcoat-whitemelange','2045867134152'),('2- furcoat-beigemelange','2-furcoat-beigemelange','2045868551415')]
def codes(p):return {str(v) for row in p.get('barcodes',[]) for v in row.values()}
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   store=Store(db,postgres=True);g.check_run_budget=lambda:None
   audit=json.loads(store.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:owner-furcoat-card-match:2026-11-10',)).fetchone()[0])
   prior=store.sql('SELECT snapshot FROM stock_runs WHERE id=?',(ROOT,)).fetchone()
   result=json.loads(prior[0]) if prior else dict(started_at=time.time(),rows={},complete=False,stock_writes=0,document_writes=0)
   def save():
    with store.transaction():store.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',(ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
   verified=[]
   for old,new,barcode in TARGETS:
    found=[p for p in audit['ms_products'] if p['article']==old and barcode in codes(p)]
    if len(found)!=1:raise Stopped('Unique audited MS product identity missing')
    ident=found[0]['id'];url=g.MS_API+'/entity/product/'+ident
    current=g.api('GET',url,g.MS_TOKEN,wb=False,retry_read_network=True)
    if current.get('id')!=ident or barcode not in codes(current) or current.get('article') not in(old,new):raise Stopped('MS product identity or article changed')
    matches=g.ms_rows(g.MS_API+'/entity/product',filter='article='+new)
    if any(p['id']!=ident for p in matches):raise Stopped('Target article already belongs to another MS product')
    verified.append((old,new,barcode,ident,url,current))
   save()
   for old,new,barcode,ident,url,original in verified:
    current=g.api('GET',url,g.MS_TOKEN,wb=False,retry_read_network=True)
    if current.get('id')!=ident or barcode not in codes(current) or current.get('article') not in(old,new):raise Stopped('MS product changed before exact article update')
    row=result['rows'].setdefault(ident,dict(old_article=old,target_article=new,barcode=barcode))
    if current['article']==new:
     row.update(state='confirmed',actual_article=new,verified_at=time.time());save();continue
    if row.get('state') in('sent','uncertain'):raise Stopped('Previous MS edit uncertain; current article remains old, no blind repeat')
    row.update(state='sent',before_article=current['article'],sent_at=time.time());save()
    try:
     g.api('PUT',url,g.MS_TOKEN,wb=False,json={'article':new})
    except Exception:
     row['state']='uncertain';save();raise
    after=g.api('GET',url,g.MS_TOKEN,wb=False,retry_read_network=True)
    if after.get('article')!=new or after.get('id')!=ident or codes(after)!=codes(current) or after.get('name')!=current.get('name'):
     row['state']='uncertain';save();raise Stopped('MS article edit readback mismatch')
    row.update(state='confirmed',actual_article=after['article'],verified_at=time.time());save()
   result.update(complete=all(r.get('state')=='confirmed' for r in result['rows'].values()) and len(result['rows'])==2,finished_at=time.time());save()
   seal('owner-furcoat-ms-article-fix',result)
   print(json.dumps(dict(complete=result['complete'],stock_writes=0,document_writes=0)))
