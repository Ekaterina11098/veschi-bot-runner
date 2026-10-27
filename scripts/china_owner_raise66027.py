"""Exact dated owner raise66028->31; stock/minimum preflight, one PATCH, exact readback."""
import os,json,copy
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity,projection
import requests
ROOT='china_agent:owner_raise660:2026-10-27:v1'
CID=41296359;NM=1473242584;ARTICLE='660-CelineaBag-cream'
def stamp():return datetime.now(timezone.utc).isoformat()
def stock():
 headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN']}
 base='https://api.moysklad.ru/api/remap/1.2'
 r=requests.get(base+'/entity/store',headers=headers,params={'limit':1000},timeout=45)
 if not r.ok:raise ValueError('Stock store unavailable')
 stores=[x for x in r.json().get('rows',[]) if x.get('name')=='МСК' and not x.get('archived')]
 if len(stores)!=1:raise ValueError('MSK store ambiguous')
 rows=[];offset=0
 while True:
  r=requests.get(base+'/report/stock/all',headers=headers,params={'filter':'store='+stores[0]['meta']['href'],'stockMode':'all','limit':1000,'offset':offset},timeout=50)
  if not r.ok:raise ValueError('Stock read failed')
  data=r.json();part=data.get('rows',[])
  rows.extend(x for x in part if (x.get('article') or '').casefold()==ARTICLE.casefold())
  if offset+len(part)>=data.get('meta',{}).get('size',offset+len(part)):break
  if not part or offset>=5000:raise ValueError('Stock pagination incomplete')
  offset+=len(part)
 if len(rows)!=1:raise ValueError('Stock article ambiguous')
 out={k:rows[0].get(k) for k in ['article','stock','reserve','price']}
 if any(not isinstance(out[k],(int,float)) for k in ['stock','reserve']) or out['stock']-out['reserve']<=0:raise ValueError('No confirmed available MSK stock')
 return dict(out,available=out['stock']-out['reserve'],observed_at=stamp())
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 c=Cache();wb=WB();a=c.get(ROOT+':approval') or {}
 if a.get('status')!='approved' or a.get('owner_user_id')!=5122667182 or a.get('source_channel')!='codex' or any(a.get(k)!=v for k,v in dict(campaign_id=CID,nm_id=NM,article=ARTICLE,placement='recommendations',old_minor=28,target_minor=31).items()) or datetime.now(timezone.utc)>datetime.fromisoformat(a['expires_at']):raise ValueError('Exact owner approval missing')
 prior=c.get(ROOT+':execution')
 if prior:
  print(json.dumps(dict(status=prior['status'],existing=True)));return
 validate_identity(c,wb)
 e=dict(status='preflight',created_at=stamp(),approval_key=ROOT+':approval',steps={},wb_writes=0,telegram_calls=0,article=ARTICLE,campaign_id=CID,nm_id=NM)
 if not c.create(ROOT+':execution',e):raise ValueError('Execution already claimed')
 def save():c.put(ROOT+':execution',copy.deepcopy(e))
 try:
  before=wb.campaigns([CID])[str(CID)];e['before']=before
  if before['status']!=9 or before['currency']!='CNY' or before['bid_type']!='manual' or before['settings']['payment_type']!='cpc' or before['settings']['placements']!=dict(search=False,recommendations=True):raise ValueError('Campaign settings changed')
  matches=[n for n in before['nm_settings'] if n['nm_id']==NM]
  if len(matches)!=1 or matches[0]['bids_kopecks']['recommendations'] not in [28,31]:raise ValueError('Current bid differs from exact approval')
  e['stock']=stock();e['minimum_minor']=wb.minimums(CID,[NM],'recommendations')[NM];save()
  config_response=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':wb.token},timeout=45)
  if not config_response.ok:raise ValueError('WB bid config unavailable')
  cfg=config_response.json();e['config']={k:cfg.get(k) for k in ['currency','cpcStep','cpcMaxBid']}
  if cfg.get('currency')!='CNY' or type(cfg.get('cpcStep'))is not int or cfg['cpcStep']<=0 or 31%cfg['cpcStep'] or not isinstance(cfg.get('cpcMaxBid'),int) or 31>cfg['cpcMaxBid'] or e['minimum_minor']>31:raise ValueError('Approved31 outside WB bid constraints')
  save()
  if matches[0]['bids_kopecks']['recommendations']==28:
   body=dict(bids=[dict(advert_id=CID,nm_bids=[dict(nm_id=NM,bid_kopecks=31,placement='recommendations')])])
   e['steps']['bid']=dict(status='submitting',body=body,submitted_at=stamp());save()
   try:
    result=wb.req('/api/advert/v1/bids','PATCH',body,write=True)
   except Exception:
    e['steps']['bid']['status']='uncertain';save();raise
   e['wb_writes']=1;e['steps']['bid'].update(status='accepted',response=result);save()
  after=wb.campaigns([CID])[str(CID)];e['after']=after
  expected=copy.deepcopy(before)
  next(n for n in expected['nm_settings'] if n['nm_id']==NM)['bids_kopecks']['recommendations']=31
  if projection(after)!=projection(expected):raise ValueError('Exact WB after readback mismatch')
  e.update(status='verified',verified_at=stamp(),completed_at=stamp(),old_minor=matches[0]['bids_kopecks']['recommendations'],target_minor=31)
  if 'bid' in e['steps']:e['steps']['bid']['status']='verified'
  save()
  registry=c.get('china_agent:verified_campaign_state:v1') or {}
  registry[str(CID)]=ROOT+':execution';c.put('china_agent:verified_campaign_state:v1',registry)
 except Exception as error:
  e.update(status='uncertain' if e['steps'] else 'blocked',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__,completed_at=stamp());save()
 print(json.dumps({k:e.get(k) for k in ['status','article','old_minor','target_minor','minimum_minor','stock','wb_writes','reason']}))
if __name__=='__main__':run()
