"""One read-only WB check started by the server; never edits prices or promotions."""
import os,json,time
from datetime import datetime,timezone
from china_cloud_cost_control import Cache
import requests
ROOT='china_agent:minimum_browser_server_wb_read:2026-10-29:v1'
CONFIG='china_agent:minimum_browser:profile:v1'
def stamp():return datetime.now(timezone.utc).isoformat()
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Registered main only')
 c=Cache();cfg=c.get(CONFIG);e=c.get(ROOT)
 if e and e['status'] in ['verified_read','failed','uncertain_submitting']:print(e['status']);return
 if not cfg or not os.environ.get('TINYFISH_API_KEY'):raise ValueError('Server profile/key unavailable')
 h={'X-API-Key':os.environ['TINYFISH_API_KEY']};base='https://agent.tinyfish.ai'
 if not e:
  source=c.get('china_agent:prices:v1') or {}
  match=[x for x in source.get('rows',[]) if str(x.get('nmID'))=='1473244991']
  if len(match)!=1:raise ValueError('Known China price row unavailable')
  row=match[0]
  target=dict(nm_id=str(row['nmID']),article=row['vendorCode'],seller_name=cfg['seller_name'],seller_ui_id=str(cfg['seller_ui_id']),currency=cfg['currency'])
  goal='READ ONLY. Open WB seller portal with saved session. Select exactly the seller in this JSON: '+json.dumps(target,ensure_ascii=False)+'. Open /discount-and-prices/main-table and search for exactly this WB nm_id. Do not edit any field, price, block or validity; do not upload or download files. Read the visible seller price after seller discount, Minimum Smart Promo price and the raw validity/block label texts for this exact item. Do not infer the meaning of ambiguous labels; return unknown if not explicitly visible. Confirm exact seller, currency and nm_id. Return only the requested JSON fields, using strings. If login is required or identity differs, stop and fill error. No Save, Apply, promotion joining or price actions. Do not reveal credentials, cookies, tokens or phone details.'
  fields=['seller_name','seller_ui_id','currency','article','nm_id','seller_price_with_discount','minimum_price','minimum_validity_text','auto_promo_block_text','page_url','observed_at','error']
  schema=dict(type='object',properties={x:{'type':'string'} for x in fields},required=fields)
  e=dict(status='submitting',created_at=stamp(),target=target,wb_writes=0,minimum_writer_enabled=False)
  if not c.create(ROOT,e):raise ValueError('Read task already claimed')
  try:
   r=requests.post(base+'/v1/automation/run-async',headers=h,json=dict(url='https://seller.wildberries.ru/',goal=goal,use_profile=True,profile_id=cfg['profile_id'],use_vault=False,output_schema=schema),timeout=45)
  except requests.RequestException:
   e.update(status='uncertain_submitting',reason='No response; never submit again');c.put(ROOT,e);raise RuntimeError('Server read submission uncertain') from None
  if not r.ok:e.update(status='failed',http_status=r.status_code);c.put(ROOT,e);raise RuntimeError('Browser service rejected read')
  run=r.json().get('run_id')
  if not run:e.update(status='failed',reason='No run id');c.put(ROOT,e);raise RuntimeError('Missing browser run id')
  e.update(status='running',run_id=run,submitted_at=stamp());c.put(ROOT,e)
 if e['status']=='submitting':raise ValueError('Uncertain prior submission; no duplicate')
 for _ in range(24):
  r=requests.get(base+'/v1/runs/'+e['run_id'],headers=h,timeout=45)
  if not r.ok:raise RuntimeError('Browser status HTTP '+str(r.status_code))
  data=r.json();status=data.get('status');e.update(service_status=status,last_checked_at=stamp())
  if status=='COMPLETED':
   result=data.get('result')
   if isinstance(result,str):
    try:result=json.loads(result)
    except ValueError:result={'error':'Unstructured result'}
   e['result']=result;e['completed_at']=stamp()
   target=e['target']
   valid=isinstance(result,dict) and not result.get('error') and all(str(result.get(k))==str(target[k]) for k in ['seller_name','seller_ui_id','currency','article','nm_id'])
   e['status']='verified_read' if valid else 'failed'
   if not valid:e['reason']='Read result identity or evidence incomplete'
   c.put(ROOT,e);print(json.dumps(dict(status=e['status'],wb_writes=0)));return
  if status in ['FAILED','CANCELLED']:
   e.update(status='failed',reason='Browser run '+status,completed_at=stamp());c.put(ROOT,e);return
  c.put(ROOT,e);time.sleep(30)
 print('Read still running; saved run id, no repeated submission')
if __name__=='__main__':main()
