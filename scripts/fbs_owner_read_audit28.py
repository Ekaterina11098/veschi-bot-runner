"""Owner requested full read-only check of ledger-owned FBS document chains."""
import concurrent.futures,copy,json,os,threading,time
from fbs_document_chain import Cache,Transport,Worker,Stop,MS,WB,TYPES,href,now
REPORT='fbs_document_chain:owner_read_audit:2026-10-28:v1'
class ReadOnly(Transport):
 def __init__(self):super().__init__();self.gate=threading.Lock();self.start=0;self.reads=0
 def request(self,base,path,method='GET',body=None,params=None):
  if base in (MS,WB) and method!='GET':raise Stop('Diagnostic prohibits operational writes')
  if base not in (MS,WB) and method!='GET' and (path!='telegram_api_cache' or (body or {}).get('cache_key')!=REPORT):raise Stop('Only diagnostic journal may be saved')
  if base==MS:
   with self.gate:
    time.sleep(max(0,1-(time.monotonic()-self.start)));self.start=time.monotonic();self.reads+=1
  return super().request(base,path,method,body,params)
def audit(t,db,cab,state,config,states):
 supply=state['supply']['id'];out=dict(cabinet=cab,supply_id=supply,ledger_status=state.get('status'),checks=[],errors=[])
 c=copy.deepcopy(config);c.pop('order_annotation',None);w=Worker(t,db,c)
 expected=(state.get('order_annotation') or {}).get('description');prefix=config.get('document_prefix','fbs-china')
 for typ in TYPES:
  check=dict(type=typ)
  try:
   ext=prefix+':'+supply+':'+typ;found=w.ms_rows('entity/'+typ,{'filter':'externalCode='+ext});check['external_code_matches']=len(found)
   if len(found)>1:out['errors'].append(typ+': duplicate externalCode')
   registered=(state.get('documents') or {}).get(typ)
   if not registered:
    check['found_ids']=[x['id'] for x in found];check['status']='not_registered'
    if typ=='customerorder':check['same_name_ids']=[x['id'] for x in w.ms_rows('entity/customerorder',{'filter':'name='+supply})]
    out['checks'].append(check);continue
   doc=next((x for x in found if x['id']==registered['id']),None)
   if doc is None:doc=t.request(MS,'entity/'+typ+'/'+registered['id'])
   check.update(id=doc['id'],name=doc.get('name'),applicable=doc.get('applicable'),sum=doc.get('sum'))
   payload=dict(config['templates'][typ],positions=state['positions'],description=expected)
   if typ=='demand':payload['customerOrder']=state['documents']['customerorder']
   if typ=='salesreturn':payload['demand']=state['documents']['demand']
   w.verify(typ,doc,payload);check['structure']='verified'
   check['comment_matches']=doc.get('description')==expected if expected else None
   if expected and not check['comment_matches']:out['errors'].append(typ+': comment mismatch');check.update(expected_comment=expected,actual_comment=doc.get('description'))
   if doc.get('externalCode')!=ext:out['errors'].append(typ+': externalCode mismatch')
   if typ=='customerorder':
    duplicates=w.ms_rows('entity/customerorder',{'filter':'name='+supply});check['same_name_ids']=[x['id'] for x in duplicates]
    if len(duplicates)!=1 or duplicates[0]['id']!=doc['id']:out['errors'].append('customerorder: ambiguous supply name')
    want=(config.get('order_annotation') or {}).get('state_name')
    if want:
     matching=[s for s in states if s.get('name')==want]
     if len(matching)!=1 or href(doc.get('state',{}))!=href(matching[0]):out['errors'].append('customerorder: completion status mismatch')
   check['status']='checked'
  except Exception as ex:
   message=str(ex) if isinstance(ex,Stop) else type(ex).__name__;check.update(status='failed',error=message);out['errors'].append(typ+': '+message)
  out['checks'].append(check)
 if state.get('status')!='complete':out['errors'].append('Ledger incomplete: '+str(state.get('error') or state.get('status')))
 out['status']='attention' if out['errors'] else 'verified';return out

def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise Stop('Public main only')
 t=ReadOnly();db=Cache(t);prior=db.get(REPORT)
 if prior and prior.get('status') in ['verified','attention']:print('Existing completed diagnostic; no repeat');return
 report=dict(status='running',started_at=now(),operational_writes=0,telegram_sends=0,results=[],configuration=[],ms_reads=0)
 jobs=[]
 for cab in ['china','ip','ooo','ozon']:
  config=db.get('fbs_document_chain:'+cab+':config:v1')
  if not config:report['configuration'].append(dict(cabinet=cab,error='config missing'));continue
  report['configuration'].append(dict(cabinet=cab,status=config.get('status'),writes_enabled=config.get('writes_enabled'),scope_confirmed=config.get('scope_confirmed'),document_prefix=config.get('document_prefix')))
  rows=t.request(db.base,'telegram_api_cache',params={'cache_key':'like.fbs_document_chain:'+cab+':supply:v1:*','select':'payload','limit':1000})
  if len(rows)>=1000:raise Stop('Ledger pagination incomplete')
  states=t.request(MS,'entity/customerorder/metadata').get('states',[])
  jobs.extend((cab,x['payload'],config,states) for x in rows)
 report['total_chains']=len(jobs);db.put(REPORT,report)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  futures=[pool.submit(audit,t,db,*j) for j in jobs]
  for future in concurrent.futures.as_completed(futures):
   report['results'].append(future.result());report.update(completed_chains=len(report['results']),ms_reads=t.reads,updated_at=now());db.put(REPORT,report)
 report.update(status='attention' if any(x['errors'] for x in report['results']) else 'verified',completed_at=now(),ms_reads=t.reads)
 report['attention']=[dict(cabinet=x['cabinet'],supply_id=x['supply_id'],errors=x['errors']) for x in report['results'] if x['errors']]
 db.put(REPORT,report);print(json.dumps(dict(status=report['status'],chains=len(jobs),attention=len(report['attention']),operational_writes=0)))
if __name__=='__main__':main()

