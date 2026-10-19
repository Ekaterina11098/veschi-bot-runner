"""Offline regression check and bounded GET-only inventory of today's retained advertising inputs."""
import os,sys,json,hashlib,socket,subprocess,requests
from urllib.parse import urlparse
from datetime import datetime,timezone
sys.path.insert(0,'private-source')
from stock_deploy_support import seal,error
proof=dict(source_calls=0,telegram_calls=0,wb_writes=0,configuration_writes=0,complete=False)
try:
 code="""import socket,unittest,sys
from unittest.mock import patch
suite=unittest.TestSuite()
for pattern in ('test_ip_unknown_identity_controls.py','test_ip_price_event_analysis.py','test_ip_full_offline_pipeline.py','test_ip_campaign_audit.py','test_ip_complete_cache_catalog.py','test_ip_missing_catalog_coverage.py','test_payload_storage.py'):
 suite.addTests(unittest.defaultTestLoader.discover('tests',pattern=pattern))
with patch.object(socket.socket,'connect',side_effect=AssertionError('External test network forbidden')):
 result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"""
 env={k:v for k,v in os.environ.items() if not any(k.startswith(p) for p in ('SUPABASE_','WB_','MPSTATS_','TELEGRAM_','ADVERTISING_','OPENAI_'))}
 tested=subprocess.run([sys.executable,'-c',code],cwd='private-source',env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 proof['tests']=dict(exit=tested.returncode,log=tested.stdout)
 if tested.returncode:raise RuntimeError('Offline regressions failed')
 host=urlparse(os.environ['SUPABASE_URL']).hostname
 native=requests.sessions.Session.request;traffic=dict(calls=0,bytes=0)
 def guard(self,method,url,*args,**kwargs):
  if method!='GET' or urlparse(url).hostname!=host or not urlparse(url).path.startswith('/rest/v1/'):raise RuntimeError('Only retained database GET allowed')
  if traffic['bytes']>=20000000:raise RuntimeError('20MB retained inspection cap')
  r=native(self,method,url,*args,**kwargs);traffic['calls']+=1;traffic['bytes']+=len(r.content);return r
 requests.sessions.Session.request=guard
 from advertising_agent import agent_store as store
 from analytics.payload_storage import decode_rows
 db=store.db
 def get(key):
  rows=db('GET','telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload,updated_at','limit':1}) or []
  return rows[0] if rows else None
 state=get('advertising:ip:daily_run:v1:2026-10-19')
 proof['day_claim']=state
 if not state or state['payload'].get('run_id')!='39202750461:1' or state['payload'].get('status')!='failed':raise RuntimeError('Exact failed daily claim changed')
 configs=decode_rows(db('GET','analytics_snapshots',params={'source':'eq.advertising_active_configuration','cabinet':'eq.token_2','select':'id,source,cabinet,payload,collected_at,period_from,period_to,status','order':'id.desc','limit':1}) or [])
 if len(configs)!=1:raise RuntimeError('Retained campaign configuration missing')
 proof['configuration']=configs[0]
 ids=sorted(x['id'] for x in configs[0]['payload'].get('adverts',[]) if x.get('status')==9)
 # Collector may already retain only the active subset without status.
 if not ids:ids=sorted(x['id'] for x in configs[0]['payload'].get('adverts',[]))
 proof['active_campaign_ids']=ids
 proof['budget_snapshots']=decode_rows(db('GET','analytics_snapshots',params={'source':'eq.advertising_campaign_budgets','cabinet':'eq.token_2','select':'id,payload,collected_at','order':'id.desc','limit':3}) or [])
 manifest=[]
 source_ids=sorted({u['id'] for stage in state['payload'].get('stages',[]) for u in (stage.get('result') or {}).get('completed_units',[]) if type(u.get('id')) is int})
 if source_ids:
  meta=db('GET','analytics_snapshots',params={'id':'in.('+','.join(map(str,source_ids))+')','cabinet':'eq.token_2','select':'id,source,cabinet,collected_at,period_from,period_to,status','order':'id.asc','limit':200}) or []
  if len(meta)!=len(source_ids):raise RuntimeError('Saved completed source manifest missing rows')
  manifest=meta
 proof['source_manifest']=manifest
 # Metadata first: no full historical scan or download of unrelated payloads.
 meta=db('GET','analytics_snapshots',params={'source':'eq.mpstats_campaign_report','cabinet':'eq.token_2','period_from':'gte.2026-10-12','period_to':'lte.2026-10-18','select':'id,period_from,period_to,collected_at,cid:payload->0->campaign_id,kind:payload->0->report,nm:payload->0->scope_nm_id','order':'id.desc','limit':200}) or []
 proof['report_metadata']=meta
 chosen={}
 for m in meta:
  if str(m.get('cid')) not in {str(x) for x in ids} or m.get('nm') is not None or m.get('kind') not in ('products','days'):continue
  key=(str(m['cid']),m['kind'],m['period_from'],m['period_to'])
  if key not in chosen:chosen[key]=m['id']
 values=[]
 if chosen:
  values=decode_rows(db('GET','analytics_snapshots',params={'id':'in.('+','.join(map(str,chosen.values()))+')','cabinet':'eq.token_2','select':'id,source,cabinet,payload,collected_at,period_from,period_to,status','order':'id.desc','limit':100}) or [])
 proof['retained_campaign_reports']=values
 proof['index']=get('mpstats:agent_reports:token_2:v1')
 proof['high_watermark']=(db('GET','analytics_snapshots',params={'select':'id','order':'id.desc','limit':1}) or [{}])[0].get('id')
 proof['registration']=store.registration()
 proof['traffic']=traffic
 proof['complete']=True
except Exception as exc:proof['error']=error(exc)
finally:
 seal('advertising-retained-inventory',proof)
 print(json.dumps(dict(complete=proof['complete'],tests_exit=(proof.get('tests') or {}).get('exit'),source_calls=0,telegram_calls=0,wb_writes=0,configuration_writes=0,error_type=(proof.get('error') or {}).get('type'))))
 if not proof['complete']:raise SystemExit(1)
