"""Owner read-only combined-source funnel and public API field documentation."""
import os,json,re,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,validate_identity,stamp
from china_hourly_sales_read import ReadOnlyWB
from china_wb_evidence import Reports,FUNNEL,normalize_funnel
ROOT='china_agent:owner_143_funnel:2026-10-31:v1'
class Adapter:
 def __init__(self,c):self.c=c
 def get(self,k):return self.c.get(k)
 def save(self,k,p):return self.c.put(k,p)
 def db(self,method,table,params=None,body=None,prefer=None):
  if table!='telegram_api_cache':raise ValueError('Private cache only')
  return self.c.req(method,params,body,prefer)
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or datetime.now(timezone.utc).date().isoformat()!='2026-10-31':raise ValueError('Dated public owner read only')
 c=Cache();w=ReadOnlyWB()
 if c.get(ROOT):print('Existing immutable owner read preserved');return
 validate_identity(c,w)
 e=dict(cabinet='token_3',observed_at=stamp(),wb_writes=0,telegram_calls=0,grants_action_permission=False)
 selected=dict(start='2026-10-31',end='2026-10-31');past=dict(start='2026-10-30',end='2026-10-30')
 body=dict(selectedPeriod=selected,pastPeriod=past,nmIds=[1473245494],brandNames=[],subjectIds=[],tagIds=[],skipDeletedNm=False,orderBy=dict(field='openCard',mode='desc'),limit=10,offset=0)
 try:
  result=Reports(Adapter(c)).request(FUNNEL,body);e['funnel_request']=body
  if not result['available']:e['funnel']=dict(status='unavailable',reason=result.get('status'),retry_at=result.get('retry_at'))
  else:
   raw=result['data'];data=raw.get('data',{});products=data.get('products')
   if not isinstance(products,list) or len(products)!=1 or products[0]['product']['nmId']!=1473245494 or data.get('currency','').upper()!='CNY':raise ValueError('Exact143 funnel identity/coverage unavailable')
   normalized=normalize_funnel(products,selected,past,ROOT)
   e['funnel']=dict(status='complete',observed_at=result['observed_at'],rows=normalized,raw=raw,scope='all_sources',update_delay_hours=2,samehour_yesterday_available=False)
 except Exception as ex:e['funnel']=dict(status='unavailable',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__)
 try:
  url='https://dev.wildberries.ru/api/swagger/yaml/ru/03-orders-fbs.yaml'
  r=requests.get(url,timeout=40);r.raise_for_status();doc=r.text
  e['official_api_fields']=dict(source=url,observed_at=stamp(),excerpts=[doc[max(0,m.start()-100):m.start()+1500]for m in list(re.finditer(r'convertedPrice:',doc))[:4]])
 except Exception as ex:e['documentation_error']=type(ex).__name__
 e.update(status='complete'if e['funnel']['status']=='complete'else'partial',completed_at=stamp())
 if not c.create(ROOT,e)or c.get(ROOT)!=e:raise ValueError('Private owner readback failed')
 print(json.dumps(dict(status=e['status'],funnel_status=e['funnel']['status'],wb_writes=0)))
if __name__=='__main__':run()
