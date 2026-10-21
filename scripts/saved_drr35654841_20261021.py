"""Read retained exact-day report18734 only. No source calls or Telegram."""
import os,sys,json
from pathlib import Path
from urllib.parse import urlparse
import requests
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,'private-source')
from stock_deploy_support import seal
from advertising_agent import agent_store as s
from analytics.payload_storage import decode_rows
from business_agents.data import Data
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(session,method,url,*a,**kw):
 u=urlparse(url)
 if u.hostname!=host or not u.path.startswith('/rest/v1/') or method.upper()!='GET':raise PermissionError('Saved GET only')
 return native(session,method,url,*a,**kw)
requests.sessions.Session.request=guard
rows=decode_rows(s.db('GET','analytics_snapshots',params={'id':'eq.18734','source':'eq.mpstats_campaign_report','cabinet':'eq.token_2','period_from':'eq.2026-10-20','period_to':'eq.2026-10-20','select':'id,payload,collected_at','limit':1}) or [])
assert len(rows)==1
p=rows[0]['payload'][0]
cards=Data('operations',lambda t,q:s.db('GET',t,params=q)).snapshot('cards','token_2')
names={int(r['nmID']):r['vendorCode'] for r in cards.get('rows',[]) if r.get('nmID') and r.get('vendorCode')}
for r in p.get('rows') or []:r['article']=names.get(r.get('nm_id'))
seal('saved-drr35654841',dict(report=rows,source_calls=0,telegram_calls=0,wb_changes=0))
print(json.dumps(dict(complete=True,rows=len(p.get('rows') or []),source_calls=0,telegram_calls=0)))
