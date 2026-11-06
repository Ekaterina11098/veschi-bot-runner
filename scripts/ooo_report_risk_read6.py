"""One cache-first missing-day OOO read; no model, delivery, marketplace mutations or retries."""
import os,json,time,hashlib,base64,datetime,xml.etree.ElementTree as ET,requests
from china_codex_cloud import DB,stamp
ROOT='ooo_agent:report_risk_review:2026-11-06:0930'
def run():
 db=DB();policy=db.get(ROOT+':request')or{}
 if policy.get('approved_read_only')is not True or policy.get('cabinet')!='token_1':raise PermissionError('Read scope missing')
 if db.get(ROOT+':read'):print('Existing read retained; no duplicate');return
 token=os.environ['WB_TOKEN_1'];claims=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='));ids=db.api('GET','analytics_snapshots',{'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})
 if claims.get('exp',0)<time.time()or not claims.get('sid')or{r['payload'].get('sid')for r in ids}!={claims['sid']}:raise PermissionError('OOO seller mismatch')
 out={'status':'reading','run_id':os.environ['GITHUB_RUN_ID'],'started_at':stamp(),'sources':{},'wb_writes':0,'model_calls':0,'telegram_calls':0};db.once(ROOT+':read',out)
 def save():db.update(ROOT+':read',out)
 def wb(name,method,path,params=None,body=None):
  if (method,path)not in{('GET','/adv/v3/fullstats'),('POST','/api/advert/v2/budget')}:raise PermissionError('No writes/read boundary')
  pk='wb-pause:'+hashlib.sha256((token+'advert-api.wildberries.ru'+path).encode()).hexdigest();pause=db.get(pk)or{}
  if float(pause.get('until',0))>time.time():out['sources'][name]={'status':'waiting_shared_quota','resume_epoch':pause['until']};save();return None
  r=requests.request(method,'https://advert-api.wildberries.ru'+path,params=params,json=body,headers={'Authorization':token},timeout=(10,90),allow_redirects=False)
  raw=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
  try:delay=float(raw or 0)
  except ValueError:delay=0
  if delay>time.time()-86400:delay=max(0,delay-time.time())
  if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and delay>0):
   until=max(float(pause.get('until',0)),time.time()+max(delay,60)+3);db.update(pk,{'until':until,'basis':'provider_header'})if pause else db.once(pk,{'until':until,'basis':'provider_header'})
  if r.status_code!=200:out['sources'][name]={'status':'waiting_provider'if r.status_code==429 else'error','http_status':r.status_code,'observed_at':stamp()};save();return None
  return r.json()
 campaign_ids=policy['campaign_ids'];raw=wb('advertising_today','GET','/adv/v3/fullstats',{'ids':','.join(map(str,campaign_ids)),'beginDate':policy['day'],'endDate':policy['day']})
 if raw is not None:
  if not isinstance(raw,list)or{r['advertId']for r in raw}!=set(campaign_ids)or any(c.get('currency')!='KGS'for c in raw):raise ValueError('Incomplete day/currency coverage')
  out['sources']['advertising_today']={'status':'complete','observed_at':stamp(),'day':policy['day'],'data':raw};save()
 raw=wb('budgets','POST','/api/advert/v2/budget',body={'advertIds':campaign_ids})
 if raw is not None:out['sources']['budgets']={'status':'complete','observed_at':stamp(),'data':raw};save()
 try:
  r=requests.get('https://www.nbkr.kg/XML_daily.asp',params={'date':'06.11.2026'},timeout=(10,30));r.raise_for_status();root=ET.fromstring(r.content)
  rate=next(n for n in root if n.attrib.get('ISOCode')=='RUB');rub=float(rate.findtext('Value').replace(',','.'))/float(rate.findtext('Nominal').replace(',','.'))
  if root.attrib.get('Date')!='06.11.2026'or not rub>0:raise ValueError('Dated FX unavailable')
  out['sources']['fx']={'status':'complete','observed_at':stamp(),'source':'https://www.nbkr.kg/XML_daily.asp?date=06.11.2026','date':'2026-11-06','kgs_per_rub':rub}
 except Exception as e:out['sources']['fx']={'status':'unavailable','error_type':type(e).__name__}
 out.update(status='finished',finished_at=stamp());save();print('Missing day and budget read stored privately; no repeats or WB mutations')
if __name__=='__main__':
 try:run()
 except Exception as e:print('Read stopped:',type(e).__name__);raise SystemExit(1)

