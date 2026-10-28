"""Explicit owner recovery of one uncertain FBS document chain; no other supplies."""
import copy,json,os
from fbs_document_chain import Cache,Transport,Worker,Stop,MS,WB,TYPES,href,now
SUPPLY='WB-GI-300616357'
KEY='fbs_document_chain:china:supply:v1:'+SUPPLY
RECEIPT='fbs_document_chain:china:owner_recovery:'+SUPPLY+':2026-10-28:v1'
ARCHIVE=RECEIPT+':original'
class ScopedTransport(Transport):
 def __init__(self):
  super().__init__();self.allowed_ids=set();self.posted=set();self.prefix='fbs-china'
 def request(self,base,path,method='GET',body=None,params=None):
  if base==WB and method!='GET':raise Stop('Recovery prohibits WB mutations')
  if base==MS and method!='GET':
   if method=='POST' and path.startswith('entity/') and path.split('/')[-1] in TYPES:
    typ=path.split('/')[-1]
    if path!='entity/'+typ or body.get('externalCode')!=self.prefix+':'+SUPPLY+':'+typ:raise Stop('Wrong supply write')
    if typ in self.posted:raise Stop('No repeated POST')
    if typ=='customerorder' and body.get('name')!=SUPPLY:raise Stop('Wrong order name')
    self.posted.add(typ)
   elif method=='PUT' and path in {'entity/customerorder/'+x for x in self.allowed_ids} and set(body)<= {'state','description'}:pass
   else:raise Stop('Recovery write outside selected chain')
  if base not in (MS,WB) and method!='GET':
   if path!='telegram_api_cache' or (body or {}).get('cache_key') not in (KEY,RECEIPT,ARCHIVE):raise Stop('Recovery cannot modify other journals')
  result=super().request(base,path,method,body,params)
  if base==MS and method=='POST' and isinstance(result,dict) and result.get('id'):self.allowed_ids.add(result['id'])
  return result
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise Stop('Public main only')
 t=ScopedTransport();db=Cache(t);prior=db.get(RECEIPT)
 if prior:print(json.dumps({'status':prior.get('status'),'existing_receipt':True}));return
 c=db.get('fbs_document_chain:china:config:v1');state=db.get(KEY)
 if not c or c.get('cabinet')!='token_3' or c.get('scope_confirmed') is not True or c.get('status')!='active' or c.get('writes_enabled') is not True:raise Stop('China configuration not active and verified')
 if not state or state['supply']['id']!=SUPPLY:raise Stop('Wrong supply')
 if len(state.get('positions',[]))!=78 or sum(p['quantity'] for p in state['positions'])!=219:raise Stop('Prepared picking scope changed; review required')
 t.prefix=c.get('document_prefix','fbs-china');w=Worker(t,db,c)
 report=dict(status='preflight',started_at=now(),supply_id=SUPPLY,owner_instruction='Create all documents for this supply only',wb_writes=0,other_supply_writes=0)
 try:
  if db.get(ARCHIVE):raise Stop('Original archive already exists without execution receipt; reconcile')
  db.put(ARCHIVE,copy.deepcopy(state))
  w.validate_source(state)
  found={}
  for typ in TYPES:
   docs=w.ms_rows('entity/'+typ,{'filter':'externalCode='+t.prefix+':'+SUPPLY+':'+typ})
   if len(docs)>1:raise Stop('Duplicate '+typ+' externalCode')
   found[typ]=[x['id'] for x in docs];t.allowed_ids.update(found[typ])
  manual=w.ms_rows('entity/customerorder',{'filter':'name='+SUPPLY})
  if any(x['id'] not in found['customerorder'] for x in manual):raise Stop('Existing manual order requires reconciliation')
  report.update(preflight_at=now(),found=found,manual_order_ids=[x['id'] for x in manual],position_count=78,quantity=219,status='running')
  db.put(RECEIPT,report)
  if state.get('inflight'):
   typ=state['inflight']
   if typ not in TYPES:raise Stop('Unknown inflight type')
   if not found[typ]:
    if typ!='customerorder' or state.get('documents'):raise Stop('Unexpected partial state; review required')
    again=w.ms_rows('entity/customerorder',{'filter':'externalCode='+t.prefix+':'+SUPPLY+':customerorder'})
    if again:raise Stop('Document appeared during reconciliation; adopt on reviewed recovery')
    state.pop('inflight');state['status']='prepared'
    state['owner_recovery']={'receipt':RECEIPT,'absence_verified_at':now(),'archive':ARCHIVE}
    db.put(KEY,state)
  w.process(state)
  final=db.get(KEY)
  if final.get('status')!='complete':raise Stop('Ledger not complete after execution')
  annotation=w.order_annotation(final['supply']);checks=[]
  for typ in TYPES:
   docs=w.ms_rows('entity/'+typ,{'filter':'externalCode='+t.prefix+':'+SUPPLY+':'+typ})
   if len(docs)!=1 or docs[0]['id']!=final['documents'][typ]['id']:raise Stop('Final unique document readback failed')
   payload=dict(c['templates'][typ],positions=final['positions'],description=annotation['description'])
   if typ=='demand':payload['customerOrder']=final['documents']['customerorder']
   if typ=='salesreturn':payload['demand']=final['documents']['demand']
   w.verify(typ,docs[0],payload)
   if typ=='customerorder' and href(docs[0].get('state',{}))!=href(annotation['state']):raise Stop('Final order state mismatch')
   checks.append(dict(type=typ,id=docs[0]['id'],name=docs[0]['name'],applicable=docs[0]['applicable'],sum=docs[0]['sum'],comment=docs[0].get('description'),verified_at=now()))
  report.update(status='verified',completed_at=now(),documents=checks,post_attempted_types=sorted(t.posted))
  db.put(RECEIPT,report);print(json.dumps({'status':'verified','documents':checks,'quantity':219},ensure_ascii=False))
 except Exception as e:
  report.update(status='requires_reconciliation',error=str(e) if isinstance(e,Stop) else type(e).__name__,failed_at=now(),post_attempted_types=sorted(t.posted))
  db.put(RECEIPT,report);raise
if __name__=='__main__':run()
