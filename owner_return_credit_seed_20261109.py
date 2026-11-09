"""Seed owner-approved once-only return claims. MS GET and technical journal only."""
import os,requests,json
from urllib.parse import urlparse
from stock_deploy_support import runtime_db
from stock_operation_store import Store
from stock_execution_fence import cloud_writer
from stock_return_credit import collect,ROOT
class G:
 MS_TOKEN='environment-only'
 norm=staticmethod(lambda s:str(s or '').strip().casefold())
 @staticmethod
 def api(method,url,token,**kw):
  if method!='GET' or urlparse(url).netloc!='api.moysklad.ru':raise RuntimeError('Read-only MS boundary')
  r=requests.get(url,headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN'],'Accept-Encoding':'gzip'},params=kw.get('params'),timeout=(5,40))
  r.raise_for_status();return r.json()
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   proof=collect(Store(db,postgres=True),G(),'technical:stock-daily:2026-11-09')
   print(json.dumps({'documents':len(proof['documents']),'names':[d['name'] for d in proof['documents'].values()],'wb_calls':0,'business_writes':0}))
