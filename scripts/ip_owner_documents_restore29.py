"""Owner-approved IP missing-document restoration. Private before/after only."""
import copy,os,re,time,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,stamp,digest
ROOT='ip_agent:documents_restore:2026-10-29:v1:execution'
APPROVAL='ip_agent:documents_restore:2026-10-29:v1:approval'
DOC_FIELDS=('id','type','number','productNumber','tradeName','applicant','startDate','endDate','isEndless')
def norm(s):return re.sub(r'\s+',' ',str(s or '')).strip().upper()
def natural(card):
 if card.get('subjectName')!='Сумки':return False
 vals=[str(v).lower() for x in card.get('characteristics',[]) if x.get('name')=='Состав' for v in (x.get('value') if isinstance(x.get('value'),list) else [x.get('value')])]
 return any(re.search(r'натурал\w*(?:\s+\w+){0,2}\s+кож|кож\w*\s+натурал',x) for x in vals) and not any('экокож' in x or 'искусствен' in x for x in vals)
def build(card,doc):
 if not natural(card):raise ValueError('Outside leather bag scope')
 old=card.get('documents')
 if not isinstance(old,dict):raise ValueError('Document state unknown')
 if old.get('items'):return None
 if old.get('overallVerdict',{}).get('reason')!='documents_missing':raise ValueError('Missing permit not established')
 body={k:copy.deepcopy(card[k]) for k in ('nmID','vendorCode','kizMarked','brand','title','gtin','description') if k in card}
 if card.get('needKiz') and 'kizMarked' not in body:raise ValueError('Marking assertion unknown')
 for k in ('nmID','vendorCode'):
  if not body.get(k):raise ValueError('Card identity missing')
 body['dimensions']={k:copy.deepcopy(card['dimensions'][k]) for k in ('length','width','height','weightBrutto') if k in card.get('dimensions',{})}
 body['characteristics']=[{'id':x['id'],'value':copy.deepcopy(x['value'])} for x in card['characteristics']]
 body['sizes']=[]
 for s in card.get('sizes',[]):
  if not s.get('chrtID') or not s.get('skus'):raise ValueError('Existing size identity missing')
  body['sizes'].append({k:copy.deepcopy(s[k]) for k in ('chrtID','techSize','wbSize','skus') if k in s})
 if not body['sizes']:raise ValueError('Sizes missing')
 body['documents']={'items':[copy.deepcopy(doc)],'excludeDocuments':False}
 return body
def projection(card):
 p={k:copy.deepcopy(card.get(k)) for k in ('nmID','vendorCode','brand','title','description','kizMarked','gtin')}
 p['dimensions']={k:card.get('dimensions',{}).get(k) for k in ('length','width','height','weightBrutto')}
 p['characteristics']=sorted([{'id':x['id'],'value':x['value']} for x in card.get('characteristics',[])],key=lambda x:x['id'])
 p['sizes']=sorted([{k:s.get(k) for k in ('chrtID','techSize','wbSize','skus')} for s in card.get('sizes',[])],key=lambda s:s['chrtID'])
 return p
def req(method,path,host='content-api.wildberries.ru',**kw):
 r=requests.request(method,'https://'+host+path,headers={'Authorization':os.environ['WB_TOKEN_2'].strip()},timeout=(15,60),allow_redirects=False,**kw)
 if not r.ok:raise RuntimeError('WB HTTP '+str(r.status_code))
 return r.json()
def read_all():
 cursor={'limit':100};out={};n=0
 while True:
  j=req('POST','/content/v2/get/cards/list',params={'locale':'ru'},json={'settings':{'sort':{'ascending':True},'cursor':cursor,'filter':{'withPhoto':-1}}})
  if not isinstance(j.get('cards'),list) or not isinstance(j.get('cursor'),dict):raise RuntimeError('Incomplete card read')
  for x in j['cards']:
   if x['nmID'] in out:raise RuntimeError('Pagination conflict')
   out[x['nmID']]=x
  n+=1
  if int(j['cursor'].get('total',-1))<100:return out
  if n>=40:raise RuntimeError('Pagination bound')
  cursor={k:j['cursor'][k] for k in ('updatedAt','nmID')};cursor['limit']=100;time.sleep(.7)
def main():
 c=Cache()
 if c.get(ROOT):return
 plan=c.get(APPROVAL)
 if not plan or plan.get('status')!='approved' or plan.get('cabinet')!='token_2':raise RuntimeError('No exact owner approval')
 if datetime.now(timezone.utc)>=datetime.fromisoformat(plan['expires_at']):raise RuntimeError('Expired approval')
 state=dict(status='preflight',observed_at=stamp(),approval_ref=APPROVAL,plan_hash=digest(plan),wb_write_requests=0,telegram_sends=0)
 if not c.create(ROOT,state):return
 attempted=False
 try:
  seller=req('GET','/api/v1/seller-info',host='common-api.wildberries.ru')
  if seller.get('sid')!=plan['seller_sid']:raise RuntimeError('Seller identity mismatch')
  chars=req('GET','/content/v2/object/charcs/50',params={'locale':'ru'})
  c.put(ROOT+':subject',dict(observed_at=stamp(),data=chars))
  if not any(x.get('charcID') in (15001135,15001137,15001138) for x in chars.get('data',[])):raise RuntimeError('Declaration type unsupported for subject')
  before=read_all();targets={int(x) for x in plan['nm_ids']};bodies=[];skip=[]
  for nm in sorted(targets):
   if nm not in before:raise RuntimeError('Approved card missing')
   body=build(before[nm],plan['document'])
   if body is None:skip.append(nm)
   else:bodies.append(body)
  c.put(ROOT+':before',dict(observed_at=stamp(),cards=[before[n] for n in sorted(targets)],cabinet='token_2'))
  if not bodies:
   state.update(status='no_change',skipped=skip);c.put(ROOT,state);return
  import json
  if len(bodies)>3000 or len(json.dumps(bodies,ensure_ascii=False).encode())>9_000_000:raise RuntimeError('Request bound')
  c.put(ROOT+':request',dict(cards=bodies,observed_at=stamp(),plan_hash=digest(plan)))
  state.update(status='applying',target_nm_ids=[b['nmID'] for b in bodies],skipped=skip);c.put(ROOT,state)
  attempted=True
  result=req('POST','/content/v2/cards/update',json=bodies)
  c.put(ROOT+':api_response',dict(observed_at=stamp(),response=result))
  if result.get('error') is not False:raise RuntimeError('WB rejected update')
  state.update(status='submitted',submitted_at=stamp(),wb_write_requests=1);c.put(ROOT,state)
  after={};verified=[]
  for attempt in range(6):
   if attempt:time.sleep(10)
   all_after=read_all();after={n:all_after[n] for n in targets if n in all_after}
   verified=[b['nmID'] for b in bodies if any(int(d.get('type',-1))==2 and norm(d.get('number'))==norm(plan['document']['number']) and d.get('startDate')==plan['document']['startDate'] and d.get('endDate')==plan['document']['endDate'] for d in after.get(b['nmID'],{}).get('documents',{}).get('items',[]))]
   c.put(ROOT+':after',dict(observed_at=stamp(),cards=list(after.values()),cabinet='token_2',attempt=attempt))
   if len(verified)==len(bodies):break
  unchanged=[n for n in verified if projection(before[n])==projection(after[n])]
  state.update(status='verified' if len(verified)==len(bodies) and len(unchanged)==len(verified) else 'readback_pending_or_mismatch',verified_nm_ids=verified,unchanged_non_document_nm_ids=unchanged,updated_count=len(verified),expected_count=len(bodies),completed_at=stamp(),document_validation_status='pending_or_separate_from_storage_verification')
  c.put(ROOT,state)
 except Exception as ex:
  state.update(status='uncertain' if attempted else 'blocked',error=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__,wb_write_requests=1 if attempted else 0,completed_at=stamp())
  c.put(ROOT,state)
  raise RuntimeError('Inspect protected IP execution receipt; never repeat uncertain write') from None
if __name__=='__main__':
 try:main();print('Owner document operation completed; inspect private receipt.')
 except Exception:print('Owner operation requires private receipt review; no automatic repeat.');raise SystemExit(1)
