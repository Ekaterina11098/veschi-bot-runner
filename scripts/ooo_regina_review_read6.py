"""Targeted owner-requested OOO read. No model, Telegram, or marketplace mutations."""
import os,json,time,hashlib,base64,requests
from china_codex_cloud import DB,stamp
ROOT='ooo_agent:regina_review:2026-11-06:1330'
def run():
 db=DB();p=db.get(ROOT+':request')or{}
 if p.get('read_only')is not True or p.get('cabinet')!='token_1':raise PermissionError('Read-only OOO scope required')
 if db.get(ROOT+':read'):print('Existing targeted read preserved');return
 token=os.environ['WB_TOKEN_1'];c=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='));ident=db.api('GET','analytics_snapshots',{'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})
 if c.get('exp',0)<time.time()or{r['payload'].get('sid')for r in ident}!={c.get('sid')}:raise PermissionError('Seller identity mismatch')
 out={'status':'reading','started_at':stamp(),'run_id':os.environ['GITHUB_RUN_ID'],'sources':{},'wb_writes':0,'telegram_calls':0,'model_calls':0};db.once(ROOT+':read',out)
 def read(label,host,path,params):
  if(host,path)not in{('advert-api.wildberries.ru','/adv/v3/fullstats'),('advert-api.wildberries.ru','/api/advert/v2/adverts'),('discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter')}:raise PermissionError('GET boundary')
  key='wb-pause:'+hashlib.sha256((token+host+path).encode()).hexdigest();pause=db.get(key)or{}
  if float(pause.get('until',0))>time.time():out['sources'][label]={'status':'waiting_shared_quota','resume_epoch':pause['until']};db.update(ROOT+':read',out);return
  r=requests.get('https://'+host+path,params=params,headers={'Authorization':token},timeout=(10,90),allow_redirects=False)
  delay=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
  try:d=float(delay or 0)
  except ValueError:d=0
  if d>time.time()-86400:d=max(0,d-time.time())
  if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and d>0):
   v={'until':max(float(pause.get('until',0)),time.time()+max(d,60)+3),'basis':'provider_header'}
   db.update(key,v)if pause else db.once(key,v)
  out['sources'][label]={'status':'complete','data':r.json(),'observed_at':stamp()}if r.status_code==200 else{'status':'waiting_provider'if r.status_code==429 else'error','http_status':r.status_code,'observed_at':stamp()}
  db.update(ROOT+':read',out)
 read('advertising_today','advert-api.wildberries.ru','/adv/v3/fullstats',{'ids':','.join(map(str,p['campaign_ids'])),'beginDate':p['day'],'endDate':p['day']})
 read('configurations','advert-api.wildberries.ru','/api/advert/v2/adverts',{'ids':','.join(map(str,p['campaign_ids']))})
 for nm in p['price_nm_ids']:read('price_'+str(nm),'discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter',{'limit':10,'offset':0,'filterNmID':nm})
 out.update(status='finished',finished_at=stamp());db.update(ROOT+':read',out);print('Targeted read saved privately; no mutations or deliveries')
if __name__=='__main__':run()

