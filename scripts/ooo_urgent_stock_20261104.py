"""Exact read-only stock and COGS checks for urgent OOO recommendations."""
import os
import ooo_owner_apply_all_20261102 as w
from china_moysklad_read import read_stock
w.KEY='ooo_agent:sales_decline:2026-11-04:1606:stock_final'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{}}
if not w.claim(w.state):raise SystemExit('Existing stock check preserved')
try:
 w.state['data']=read_stock(['143-ReginaBag-black','594-NoelBag-green','59-NoelBag-grey','685-CelineaBag-black','663-CelineaBag-beige'])
 w.state.update(status='finished',finished_at=w.stamp());w.save()
except Exception as e:
 w.state.update(status='unavailable',error=type(e).__name__);w.save()
print('Read-only MSK evidence stored privately')
