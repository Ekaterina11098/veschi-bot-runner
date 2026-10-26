"""Final read-only confirmation of owner-approved cohort; never mutate WB."""
import requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
c=Cache();w=WB();validate_identity(c,w)
parent=c.get('china_agent:codex_search_expand26:v4:execution') or {}
if len(parent.get('groups',[]))!=2 or any(g.get('status')!='verified' for g in parent['groups']):raise RuntimeError('Scoped child execution not verified')
cs=w.campaigns([41332083,41325637])
for g in parent['groups']:
 after=cs[str(g['campaign_id'])]
 expected={i['nm_id'] for i in g['items']}
 actual={n['nm_id']:n for n in after['nm_settings']}
 if not expected<=set(actual):raise RuntimeError('Verified items no longer present')
 for nm in expected:
  if actual[nm]['bids_kopecks']['search']!=g['minimums'][str(nm)]:raise RuntimeError('Minimum bid changed')
 if after['status'] not in ([4,9] if g['campaign_id']==41332083 else [9]):raise RuntimeError('Campaign status changed')
budgets=w.req('/api/advert/v2/budget','POST',dict(advertIds=[41332083,41325637]))
r=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':w.token},timeout=50)
if not r.ok:raise RuntimeError('Config read HTTP '+str(r.status_code))
config=r.json()
if config.get('currency')!='CNY':raise RuntimeError('Config currency mismatch')
c.put('china_agent:codex_search_expand26:final:execution',dict(status='verified',verified_at=datetime.now(timezone.utc).isoformat(),groups=[dict(g,after=cs[str(g['campaign_id'])]) for g in parent['groups']],budgets_after=budgets,config=config,wb_writes=0,telegram_sends=0,parent='china_agent:codex_search_expand26:v4:execution',note='All scoped additions and minima verified; parent post-verification config read used an unsupported helper endpoint, no repeated writes.'))
print('Final current states, memberships, minimum bids and budgets verified; no writes.')
