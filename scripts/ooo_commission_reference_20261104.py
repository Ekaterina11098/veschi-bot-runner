"""Read-only current commission reference for exact OOO campaign subjects."""
import os,time,hashlib,requests
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:full_review:2026-11-04:commissions'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{}}
if not w.claim(w.state):raise SystemExit('Existing tariff receipt')
try:
 base=w.get('ooo_agent:morning:2026-11-04:evidence')
 subjects={n['subject']['id']for c in base['sources']['configurations']['data'].values()for n in c['nm_settings']}
 host='common-api.wildberries.ru';path='/api/v1/tariffs/commission';pk='wb-pause:'+hashlib.sha256((w.TOKEN+host+path).encode()).hexdigest()
 until=float((w.get(pk)or{}).get('until',0))
 if until>time.time():raise RuntimeError('Tariff cooldown')
 r=requests.get('https://'+host+path,headers={'Authorization':w.TOKEN},timeout=(10,60),allow_redirects=False)
 if r.status_code==429:
  delay=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or'60'
  w.put(pk,{'until':time.time()+max(60,float(delay))+3,'basis':'provider_header'})
 r.raise_for_status();v=r.json();rows=v.get('report',v.get('data',[]))
 if not isinstance(rows,list):raise ValueError('Commission schema')
 found=[x for x in rows if x.get('subjectID')in subjects]
 if not found:raise ValueError('No exact subject commission')
 w.state.update(status='finished',data=found,subjects=sorted(subjects),observed_at=w.stamp());w.save()
except Exception as e:
 w.state.update(status='unavailable',error=type(e).__name__+':'+str(e)[:700]);w.save()
