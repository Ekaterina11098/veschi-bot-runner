import sys,os,json,requests
from datetime import datetime,timezone
sys.path[:0]=['scripts','source']
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
from china_price_apply import IO
io=IO();out=dict(observed_at=datetime.now(timezone.utc).isoformat(),cabinet='token_3',observations=[],cards={},feedbacks={},wb_writes=0,telegram_calls=0)
def reader(call,checks,known):
 tasks=[]
 for nm,pid in [(1473243912,'149503443'),(1535337772,'149503566')]:
  for name,args in [('lk_wb_card_orders',dict(type='products',value=pid,date_from='2026-09-23',date_to='2026-10-22',start_row=0,end_row=300)),('lk_wb_card_table',dict(type='products',value=pid,period_type='30days',self_redemption=False))]:
   tasks.append(dict(key=str(nm)+':'+name,tool=name,cabinet='token_3',arguments=args))
 return execute_reads(call,checks,known,tasks,{},lambda c,o:out['observations'].append(o),max_requests=4)
r=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader);out['mpstats_status']=r['status']
for nm in [1473243912,1535337772]:
 j=requests.post('https://content-api.wildberries.ru/content/v2/get/cards/list',headers={'Authorization':io.token},json={'settings':{'cursor':{'limit':100},'filter':{'textSearch':str(nm),'withPhoto':-1}}},timeout=40)
 out['cards'][str(nm)]=dict(http=j.status_code,data=j.json() if j.ok else None)
 for answered in ['true','false']:
  q=requests.get('https://feedbacks-api.wildberries.ru/api/v1/feedbacks',headers={'Authorization':io.token},params=dict(isAnswered=answered,take=100,skip=0,nmId=nm),timeout=40)
  out['feedbacks'][str(nm)+':'+answered]=dict(http=q.status_code,data=q.json() if q.ok else None)
io.create('china_agent:two_loss_diagnosis:2026-10-23:v1',out)
print(json.dumps(dict(status=r['status'],observations=[o['status'] for o in out['observations']],cards={k:v['http'] for k,v in out['cards'].items()},feedbacks={k:v['http'] for k,v in out['feedbacks'].items()},wb_writes=0,telegram_calls=0)))
