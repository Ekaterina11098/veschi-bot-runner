"""Owner diagnostic of534 search traffic; read-only promotion endpoints."""
import os,time,requests,json
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:534_search_cause:2026-10-29:v1'
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 assert datetime.now(timezone(timedelta(hours=3))).date().isoformat()=='2026-10-29'
 c=Cache();w=WB();validate_identity(c,w)
 if c.get(ROOT):print('Existing diagnostic; no duplicate read');return
 config=w.campaigns([40933588,41298169])
 save=lambda k,p:c.put(k,json.loads(json.dumps(p,allow_nan=False)))
 save(ROOT+':campaigns',dict(observed_at=stamp(),rows=config))
 members={x['nm_id'] for x in config['41298169']['nm_settings']}
 nms=[1473243903,1473243896,1473243910,1473244984]
 if not set(nms)<=members or config['41298169'].get('currency')!='CNY':raise ValueError('Verified scope changed')
 out=dict(status='collecting',started_at=stamp(),errors=[],wb_writes=0,stock_reads=0,telegram_sends=0)
 if not c.create(ROOT,out):raise ValueError('Concurrent read')
 pairs=[dict(advertId=41298169,nmId=nm) for nm in nms]
 for label,path,body in [('query_daily','/adv/v1/normquery/stats',dict(from_='2026-10-25',to='2026-10-29',items=pairs)),('query_list','/adv/v0/normquery/list',dict(items=pairs))]:
  if 'from_' in body:body['from']=body.pop('from_')
  try:
   r=requests.post('https://advert-api.wildberries.ru'+path,headers={'Authorization':w.token},json=body,timeout=65)
   if not r.ok:raise RuntimeError('Read HTTP '+str(r.status_code))
   data=r.json();save(ROOT+':'+label,dict(observed_at=stamp(),request=body,data=data))
   out[label]=dict(status='received',top_keys=list(data) if isinstance(data,dict) else None)
  except Exception as ex:out['errors'].append(dict(stage=label,error=str(ex) if isinstance(ex,RuntimeError) else type(ex).__name__))
  time.sleep(7)
 try:
  stats=w.req('/adv/v3/fullstats?ids=40933588,41298169&beginDate=2026-10-22&endDate=2026-10-29')
  selected=[]
  for st in stats:
   item=dict(id=st['advertId'],position=[r for r in st.get('boosterStats',[]) if r.get('nm') in nms],days=[])
   for d in st.get('days',[]):
    apps=[]
    for a in d.get('apps',[]):
     rows=[x for x in a.get('nms',[]) if x.get('nmId') in nms]
     if rows:apps.append(dict(appType=a.get('appType'),nms=rows))
    item['days'].append(dict(date=d.get('date'),apps=apps))
   selected.append(item)
  save(ROOT+':fullstats',dict(observed_at=stamp(),rows=selected))
 except Exception as ex:out['errors'].append(dict(stage='fullstats',error=type(ex).__name__))
 out.update(status='complete' if not out['errors'] else 'partial',completed_at=stamp());save(ROOT,out)
 print(json.dumps(dict(status=out['status'],errors=out['errors'])))
if __name__=='__main__':main()
