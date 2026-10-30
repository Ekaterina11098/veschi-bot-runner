"""Owner-requested read check after completed advertising scope; no WB or Telegram access."""
import json,os
from china_cloud_cost_control import Cache,stamp
from china_moysklad_read import read_stock,MoySkladReadError
ROOT='china_agent:moysklad_read_check:2026-10-30:v2'
PARENT='china_agent:owner_five_bid_actions:2026-10-30:v2'
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise ValueError('Public runner only')
 c=Cache();parent=c.get(PARENT+':execution') or {}
 if parent.get('status')!='verified':raise ValueError('Advertising scope must be completed first')
 if c.get(ROOT):print('Existing read-check receipt preserved');return
 e={'status':'reading','started_at':stamp(),'wb_calls':0,'moysklad_writes':0,'telegram_calls':0,'source_execution_key':PARENT+':execution'}
 if not c.create(ROOT,e):raise ValueError('Concurrent read check')
 try:
  a=c.get(PARENT+':approval') or {};articles=[i['article'] for i in a['approved_items']]
  if len(articles)!=5 or len(set(articles))!=5:raise ValueError('Exact article scope missing')
  data=read_stock(articles);e['data']=data
  valid=len(data['rows'])==len(articles) and data['coverage_complete'] and all(all(type(r.get(k))in(int,float) for k in ['stock','reserve','price']) and r['price']>0 for r in data['rows'])
  e['status']='verified' if valid else 'partial'
 except Exception as ex:e.update(status='failed',reason=str(ex) if isinstance(ex,(MoySkladReadError,ValueError)) else type(ex).__name__)
 e['completed_at']=stamp();c.put(ROOT,e);print(json.dumps({'status':e['status'],'wb_calls':0,'moysklad_writes':0,'telegram_calls':0}))
if __name__=='__main__':run()
