"""Read-only verification of legacy per-order chains for unmatched historical supplies."""
import json,os
from fbs_document_chain import Cache,Transport,Worker,Stop,MS,WB,now
from fbs_ozon_api import ozon
ROOT='fbs_document_chain:owner_coverage:2026-10-28:v1'
REPORT=ROOT+':legacy_order_links'
class ReadOnly(Transport):
 def request(self,base,path,method='GET',body=None,params=None):
  if base in (MS,WB) and method!='GET':raise Stop('Read only')
  if base not in (MS,WB) and method!='GET' and (path!='telegram_api_cache' or body.get('cache_key')!=REPORT):raise Stop('Diagnostic only')
  return super().request(base,path,method,body,params)
def refs(doc,typ):
 out=set()
 for value in doc.values():
  values=value if isinstance(value,list) else [value]
  for x in values:
   if isinstance(x,dict) and x.get('meta',{}).get('type')==typ:out.add(x['meta']['href'].rstrip('/').split('/')[-1])
 return out
def batches(w,typ,field,values):
 rows={}
 values=sorted(set(values))
 for start in range(0,len(values),20):
  for d in w.ms_rows('entity/'+typ,{'filter':';'.join(field+'='+str(x) for x in values[start:start+20])}):rows[d['id']]=d
 return rows
def slim(d):
 return dict(id=d['id'],name=d.get('name'),posted=d.get('applicable'),sum=d.get('sum'))
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise Stop('Public main only')
 t=ReadOnly();db=Cache(t);root=db.get(ROOT)
 if db.get(REPORT):print('Existing legacy check');return
 c=db.get('fbs_document_chain:china:config:v1');w=Worker(t,db,c)
 report=dict(status='running',started_at=now(),operational_writes=0,results=[])
 tokens={cab:os.environ['WB_TOKEN_'+n] for cab,n in [('ip','2'),('ooo','1')]}
 scopes=[]
 for row in root['results']:
  if row['status']!='not_matched':continue
  if row['cabinet']=='ozon':
   postings=ozon('/v2/posting/fbs/act/get-postings',{'id':int(row['supply_id'].split('-')[-1])}).get('result')
   if not isinstance(postings,list):raise Stop('Posting list incomplete')
   ids=[p['posting_number'] for p in postings]
  else:
   os.environ['WB_TOKEN_3']=tokens[row['cabinet']]
   ids=t.request(WB,'api/marketplace/v3/supplies/'+row['supply_id']+'/order-ids').get('orderIds')
   if not isinstance(ids,list):raise Stop('Order list incomplete')
  scopes.append(dict(cabinet=row['cabinet'],supply_id=row['supply_id'],order_names=[str(x) for x in ids]))
 report.update(stage='source_orders',scopes=scopes);db.put(REPORT,report)
 orders=batches(w,'customerorder','name',[x for row in scopes for x in row['order_names']])
 demand_ids=set()
 for d in orders.values():demand_ids.update(refs(d,'demand'))
 demands=batches(w,'demand','id',demand_ids)
 return_ids=set()
 for d in demands.values():return_ids.update(refs(d,'salesreturn'))
 returns=batches(w,'salesreturn','id',return_ids)
 report.update(stage='linked_documents',orders_found=len(orders),demands_found=len(demands),returns_found=len(returns));db.put(REPORT,report)
 byname={}
 for d in orders.values():byname.setdefault(d['name'],[]).append(d)
 for scope in scopes:
  checks=[]
  for name in scope['order_names']:
   found=byname.get(name,[]);check=dict(order_name=name,orders=[slim(d) for d in found],demands=[],returns=[],issues=[])
   if len(found)!=1:check['issues'].append('No unique order match')
   else:
    ds=[demands[x] for x in refs(found[0],'demand') if x in demands]
    rs=[returns[x] for d in ds for x in refs(d,'salesreturn') if x in returns]
    check['demands']=[slim(d) for d in ds];check['returns']=[slim(d) for d in rs]
    if not ds:check['issues'].append('No linked demand')
    if not rs:check['issues'].append('No linked return')
    if any(d.get('applicable') is not True for d in found+ds+rs):check['issues'].append('Unposted document')
   check['status']='complete' if not check['issues'] else 'needs_review';checks.append(check)
  report['results'].append(dict(cabinet=scope['cabinet'],supply_id=scope['supply_id'],orders_expected=len(checks),orders_matched=sum(bool(x['orders']) for x in checks),complete_order_chains=sum(x['status']=='complete' for x in checks),checks=checks,status='complete' if checks and all(x['status']=='complete' for x in checks) else 'needs_review'))
 report.update(status='complete',completed_at=now());db.put(REPORT,report);print(json.dumps(dict(status='complete',checked=len(scopes))))
if __name__=='__main__':main()
