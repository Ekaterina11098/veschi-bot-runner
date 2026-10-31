"""Only remaining three approved deposits; never repeat the two separately funded campaigns."""
import copy,json,os,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:owner_reserve_rest31:v1'
def run():
 c=Cache();w=WB();a=c.get(ROOT+':approval')or{}
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or a.get('status')!='approved' or a.get('owner_user_id')!=5122667182 or datetime.now(timezone.utc)>datetime.fromisoformat(a['expires_at']):raise ValueError('Approvalscope')
 if [(i['cid'],i['amount'])for i in a['items']]!=[(41055480,100),(41296359,100),(41332083,250)]:raise ValueError('Exactscope')
 old=c.get(ROOT+':execution')
 if old:print(json.dumps({'status':old['status'],'existing':True}));return
 validate_identity(c,w);e={'status':'running','items':[],'wb_budget_writes':0,'bid_writes':0,'telegram_calls':0}
 if not c.create(ROOT+':execution',e):raise ValueError('Race')
 def save():c.put(ROOT+':execution',copy.deepcopy(e))
 def api(path,method='GET',body=None):
  if method=='POST'and(path not in ['/adv/v1/budget/deposit?id='+str(i['cid'])for i in a['items']]or body.get('sum')!=next(i['amount']for i in a['items']if path.endswith('='+str(i['cid'])))):raise ValueError('Depositscope')
  r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':w.token},json=body,timeout=45)
  if not r.ok:raise RuntimeError('WB HTTP'+str(r.status_code))
  return r.json()if r.content else{}
 def cash(cid):
  rows=w.req('/api/advert/v2/budget','POST',{'advertIds':[cid]})['adverts']
  if len(rows)!=1 or rows[0]['advertId']!=cid or rows[0]['currency']!='CNY':raise ValueError('Cashidentity')
  return rows[0]['total']
 cfg=api('/api/advert/v1/config')
 for i in a['items']:
  st={'cid':i['cid'],'amount_cny':i['amount'],'status':'preflight'};e['items'].append(st);save()
  try:
   cp=w.campaigns([i['cid']])[str(i['cid'])]
   if cp['status']!=9 or cp['currency']!='CNY':raise ValueError('Campaigninactive')
   st['before']=cp;b=cash(i['cid']);st['before_budget']=b;save()
   if b>i['balance']+2:raise ValueError('Already funded after analysis; no duplicate')
   if cfg['currency']!='CNY'or cfg['minTopUp']>i['amount']*100:raise ValueError('Minimumchanged')
   bal=api('/adv/v1/balance')
   if bal.get('currency')!='CNY':raise ValueError('Currency')
   source=0 if bal.get('balance',0)>=i['amount']else 1 if bal.get('net',0)>=i['amount']else None
   if source is None:raise ValueError('Insufficient CNY')
   body={'sum':i['amount'],'type':source};path='/adv/v1/budget/deposit?id='+str(i['cid'])
   st.update(status='submitting',submitted_at=stamp(),steps={'deposit':dict(status='submitting',path=path,body=body,submitted_at=stamp())});save()
   try:response=api(path,'POST',body)
   except Exception:st['status']='uncertain';save();raise
   st.update(status='accepted',response=response);e['wb_budget_writes']+=1;save()
   after=cash(i['cid']);st['after_budget']=after
   if after<b+i['amount']-2:raise ValueError('Readbackmismatch;no retry')
   st.update(status='verified',verified_at=stamp(),after=w.campaigns([i['cid']])[str(i['cid'])]);st['steps']['deposit']['status']='verified';save()
   c.create(ROOT+':'+str(i['cid'])+':execution',dict(st,parent=ROOT+':execution',kind='budget_topup'))
  except Exception as ex:
   st.update(status='uncertain'if st['status']in['submitting','accepted','uncertain']else'blocked',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__);save()
 e.update(status='verified'if len(e['items'])==3 and all(i['status']=='verified'for i in e['items'])else'partial',completed_at=stamp());save()
 print(json.dumps({'status':e['status'],'budget_writes':e['wb_budget_writes']}))
if __name__=='__main__':run()
