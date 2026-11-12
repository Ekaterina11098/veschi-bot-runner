"""One explicit same-root owner recovery; ordinary cloud executor does all writes."""
import os,json,time,psycopg
import tg_agent_new as g
import stock_regular_service as service
from stock_deploy_support import runtime_db,password,HOST,ROLE,PROJECT,seal
from stock_execution_fence import cloud_writer
from stock_operation_store import Store
from stock_shared_requests import SharedRequests
from stock_regular_job import send
from stock_owner_recover_20261112 import prepare,verify_preserved,ROOT
os.environ['STOCK_DATABASE_URL']=psycopg.conninfo.make_conninfo(host=HOST,port=5432,dbname='postgres',user=ROLE+'.'+PROJECT,password=password(),sslmode='require')
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   store=Store(db,postgres=True);shared=SharedRequests(store)
   g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
   g._CACHE_GET=shared.get;g._CACHE_SET=shared.put;g.RUN_DEADLINE=time.monotonic()+2400
   data=prepare(store,g);seal('morning-owner-recovery-prepared',data['owner_recovery'])
result=service.run(runtime_db,send,'2026-11-12:0700')
with runtime_db() as db:
 data=verify_preserved(Store(db,postgres=True));db.commit()
 seal('morning-owner-recovery-result',dict(result=result,owner_recovery=data['owner_recovery'],progress=data.get('progress'),held_articles=data.get('held_articles'),delivery=data.get('delivery'),execution_complete=data.get('execution_complete'),delivery_done=data.get('delivery_done')))
print(json.dumps(result))

