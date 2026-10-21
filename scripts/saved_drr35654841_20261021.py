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
rows=decode_rows(s.db('GET','analytics_snapshots',params={'id':'in.(18736,18738,18740,18742,18744,18746,18748,18750,18752,18754)','source':'eq.mpstats_campaign_report','cabinet':'eq.token_2','period_from':'eq.2026-10-20','period_to':'eq.2026-10-20','select':'id,payload,collected_at','limit':10}) or [])
assert len(rows)==10
seal('saved-noorders',dict(report=rows,source_calls=0,telegram_calls=0,wb_changes=0))
print(json.dumps(dict(complete=True,snapshots=len(rows),source_calls=0,telegram_calls=0)))
