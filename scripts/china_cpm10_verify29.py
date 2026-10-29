"""Read-only canonical before/after for owner-authorized browser CPM creation."""
import os,json
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
ROOT='china_agent:owner_cpm10_apply29:2026-10-29:v1'
PHASE=os.environ.get('REVIEW_PHASE','before')
def save(c,k,p):c.put(k,json.loads(json.dumps(p,allow_nan=False)))
def main():
 assert os.environ.get('GITHUB_REPOSITORY')=='Ekaterina11098/veschi-bot-runner' and os.environ.get('GITHUB_REF')=='refs/heads/main'
 assert datetime.now(timezone(timedelta(hours=3))).date().isoformat()=='2026-10-29'
 c=Cache();w=WB();validate_identity(c,w)
 approval=c.get(ROOT+':approval');assert approval and approval['status']=='approved'
 key=ROOT+':'+PHASE
 if c.get(key):print('Existing private snapshot; no repeated reads');return
 inv=w.req('/adv/v1/promotion/count')
 ids=sorted({a['advertId'] for g in inv.get('adverts',[]) for a in g.get('advert_list',[])})
 camps=w.campaigns(ids)
 budgets=w.req('/api/advert/v2/budget','POST',dict(advertIds=ids)).get('adverts',[])
 targets={int(x['nm_id']) for x in approval['items']}
 affected={cid:v for cid,v in camps.items() if any(int(n['nm_id']) in targets for n in v.get('nm_settings',[]))}
 base=dict(status='captured',phase=PHASE,observed_at=stamp(),campaigns=camps,budgets=budgets,affected=affected,wb_writes=0)
 if PHASE=='before':
  assert not any(x.get('settings',{}).get('name')==approval['name'] for x in camps.values()),'Named campaign already exists; do not create duplicate'
 save(c,key,base)
 print('Private read-only snapshot captured')
if __name__=='__main__':main()
