"""Hourly cloud cost reduction; private state, narrow WB and funding-only Telegram."""
import argparse,base64,copy,hashlib,json,math,os,time
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import requests
ROOT='china_agent:hourly_cloud:'
POLICY='china_agent:owner_autonomy:advertising_cost_control:2026-10-25:v1'
FIELDS={'spend':'sum','clicks':'clicks','orders':'orders','amount':'sum_price','baskets':'atbs','views':'views'}
def now():return datetime.now(timezone.utc)
def stamp():return now().isoformat()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def zero():return {k:0 for k in FIELDS}
def drr(x):return x['spend']/x['amount']*100 if x['amount']>0 else None
def delta(a,b):return {k:round(a.get(k,0)-b.get(k,0),8) for k in FIELDS}
def authorized(p,t):return p.get('status')=='active' and p.get('cabinet')=='token_3' and t<datetime.fromisoformat(p['expires_at'].replace('Z','+00:00'))
def projection(c):return {k:c[k] for k in ['id','status','currency','bid_type','settings']}|dict(nm_settings=sorted(c['nm_settings'],key=lambda n:n['nm_id']))
def counts(stats):
 campaigns={};skus={}
 for c in stats:
  cid=str(c['advertId']);campaigns[cid]={k:c.get(f,0) for k,f in FIELDS.items()}
  for d in c.get('days',[]):
   for app in d.get('apps',[]):
    for n in app.get('nms',[]):
     r=skus.setdefault(cid+':'+str(n['nmId']),zero())
     for k,f in FIELDS.items():r[k]+=n.get(f,0)
 return campaigns,skus
def risk(x,price,prev):
 if not price or x['spend']<=0 or any(x[k]<0 for k in ['spend','orders','amount','clicks']):return None
 prev=prev or {};rate=drr(x);old=drr(prev) if prev else None
 if x['orders']==0 and x['spend']>=price*.05 and (x['clicks']>=30 or prev.get('orders')==0 and prev.get('spend',0)>=price*.05):return 'no_orders'
 if rate is not None and rate>5 and x['orders']>=1:
  if old is not None and rate<old*.9:return None
  if x['orders']>=5 or old is not None and old>5 and x['spend']>prev.get('spend',0):return 'high_drr'
 return None
def expected_campaign(before,items):
 out=copy.deepcopy(before)
 for x in items:
  if x['kind']=='pause':out['status']=11
  elif x['kind']=='exclude':out['nm_settings']=[n for n in out['nm_settings'] if n['nm_id']!=x['nm']]
  elif x['kind']=='lower':
   n=next(n for n in out['nm_settings'] if n['nm_id']==x['nm']);assert 0<x['target']<n['bids_kopecks'][x['placement']]
   n['bids_kopecks'][x['placement']]=x['target']
  else:raise ValueError('Forbidden action')
 assert out['nm_settings']
 return out

def observed_interval(previous,snap,current):
 start=datetime.fromisoformat(previous['last_observed_at']);end=datetime.fromisoformat(snap['observed_at'])
 hours=(end-start).total_seconds()/3600
 a=start.astimezone(ZoneInfo('Europe/Moscow'));b=end.astimezone(ZoneInfo('Europe/Moscow'))
 phase='mixed_or_other'
 if a.date()==b.date() and 0<=a.hour<6 and b.hour<6:phase='night_00_06'
 if a.date()==b.date() and 12<=a.hour<18 and b.hour<18:phase='day_12_18'
 rows={}
 for cid,total in current.items():
  old=previous.get('previous_campaign_counters',{}).get(cid)
  if old is None:continue
  change=delta(total,old);before=previous.get('campaigns',{}).get(cid);after=snap['campaigns'].get(cid)
  revised=any(change[k]<0 for k in ['spend','orders','amount','clicks'])
  changed=bool(before and after and projection(before)!=projection(after)) or any(str(x.get('cid'))==cid for x in previous.get('last_actions',[]))
  rows[cid]=dict(delta=change,drr_pct=drr(change),attribution_revision=revised,settings_changed=changed,comparable=0<hours<=1.5 and phase!='mixed_or_other' and not revised and not changed)
 return dict(slot=snap['slot'],observed_from=start.isoformat(),observed_to=end.isoformat(),msk_date=a.date().isoformat(),duration_hours=hours,phase=phase,campaigns=rows,orders_time_basis='WB attribution updates observed during interval, not ad-click or order cohort time',preliminary=True,automatic_actions_allowed=False)
def summarize_time(intervals):
 out={}
 for interval in intervals:
  for cid,row in interval['campaigns'].items():
   entry=out.setdefault(cid,dict(night=zero()|dict(hours=0,dates=[]),day=zero()|dict(hours=0,dates=[]),excluded_intervals=0))
   if not row['comparable']:entry['excluded_intervals']+=1;continue
   key='night' if interval['phase']=='night_00_06' else 'day'
   group=entry[key]
   for k in FIELDS:group[k]+=row['delta'][k]
   group['hours']+=interval['duration_hours']
   if interval['msk_date'] not in group['dates']:group['dates'].append(interval['msk_date'])
 for cid,entry in out.items():
  for key in ['night','day']:
   g=entry[key];g['drr_pct']=drr(g);g['spend_per_observed_hour']=g['spend']/g['hours'] if g['hours']>0 else None
  n=entry['night'];d=entry['day'];ready=len(n['dates'])>=2 and len(d['dates'])>=2 and min(n['hours'],d['hours'])>=8
  entry['enough_repeated_observations']=ready
  entry['hypothesis_for_owner_only']=bool(ready and d['orders']>=5 and ((n['orders']==0 and n['clicks']>=60 and n['spend']>0) or (n['drr_pct'] is not None and d['drr_pct'] is not None and n['drr_pct']>5 and n['drr_pct']>d['drr_pct']*1.5)))
  entry['not_a_closed_cohort_or_causal_estimate']=True
 return out
def record_time_observation(c,state,snap,current):
 interval=observed_interval(state,snap,current);key=ROOT+'time_interval:'+snap['slot'];c.create(key,interval)
 rows=c.req('GET',dict(cache_key='like.'+ROOT+'time_interval:*',select='payload',order='updated_at.desc',limit=72))
 summary=summarize_time([r['payload'] for r in rows])
 c.put(ROOT+'time_of_day:v1',dict(observed_at=snap['observed_at'],windows_msk=dict(night='00:00–06:00',day_reference='12:00–18:00'),normalization='per actual observed hour; never compare unequal raw totals',campaigns=summary,automatic_pause_allowed=False,attribution_warning='Order deltas show update time, not proved click-time conversion; late and negative revisions preserved'))
 for cid,r in summary.items():
  if r['hypothesis_for_owner_only']:
   n=r['night'];d=r['day'];nr='неопределена' if n['drr_pct'] is None else str(round(n['drr_pct'],2))+'%'
   c.notice('time-pattern:'+cid+':'+snap['slot'][:10],'РК '+cid+': повторяется гипотеза слабой ночной отдачи. Ночь: '+str(round(n['spend'],2))+' CNY / '+str(n['orders'])+' обновлений рекламных заказов, ДРР '+nr+'; день: '+str(round(d['spend'],2))+' CNY / '+str(d['orders'])+' заказов, ДРР '+str(round(d['drr_pct'],2))+'%. Только предложение обсудить расписание: РК НЕ остановлена, атрибуция предварительная.',r)

class Cache:
 def __init__(self):
  self.url=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/telegram_api_cache'
  key=os.environ['SUPABASE_SECRET_KEY'];self.h={'apikey':key,'Content-Type':'application/json'}
  if not key.startswith('sb_secret_'):self.h['Authorization']='Bearer '+key
 def req(self,method,params=None,body=None,prefer=None):
  r=requests.request(method,self.url,params=params,headers=self.h|({'Prefer':prefer} if prefer else {}),json=body,timeout=35)
  if not r.ok:raise RuntimeError('Private state HTTP '+str(r.status_code))
  return r.json() if r.content else []
 def row(self,key):
  rows=self.req('GET',{'cache_key':'eq.'+key,'select':'payload,updated_at'});return rows[0] if len(rows)==1 else None
 def get(self,key):
  r=self.row(key);return r['payload'] if r else None
 def create(self,key,p):
  return bool(self.req('POST',{'on_conflict':'cache_key'},dict(cache_key=key,payload=p,updated_at=stamp(),expires_at='2036-10-25T00:00:00Z'),'resolution=ignore-duplicates,return=representation'))
 def put(self,key,p):
  self.req('POST',{'on_conflict':'cache_key'},dict(cache_key=key,payload=p,updated_at=stamp(),expires_at='2036-10-25T00:00:00Z'),'resolution=merge-duplicates,return=representation')
  if self.get(key)!=p:raise RuntimeError('State readback mismatch')
 def lease(self,owner):
  key=ROOT+'lease:v1';r=self.row(key);p={'owner':owner,'until':(now()+timedelta(minutes=19)).isoformat()}
  if not r:return self.create(key,p)
  if datetime.fromisoformat(r['payload']['until'])>now():return False
  return len(self.req('PATCH',{'cache_key':'eq.'+key,'updated_at':'eq.'+r['updated_at']},dict(payload=p,updated_at=stamp()),'return=representation'))==1
 def release(self,owner):
  p=self.get(ROOT+'lease:v1')
  if p and p.get('owner')==owner:self.put(ROOT+'lease:v1',dict(owner=owner,until=stamp()))
 def notice(self,event,text,details=None):
  self.create(ROOT+'outbox:'+digest(event),dict(status='pending',channel='codex',event=event,text=text,details=details or {},created_at=stamp()))
class WB:
 def __init__(self):self.token=os.environ['WB_TOKEN_3']
 def req(self,path,method='GET',body=None,write=False):
  reads={'/adv/v1/promotion/count','/api/advert/v2/adverts','/api/advert/v2/budget','/adv/v3/fullstats','/api/advert/v1/bids/min'}
  writes={'/api/advert/v1/bids','/adv/v0/auction/nms','/adv/v0/pause'}
  bare=path.split('?')[0]
  if bare not in (writes if write else reads):raise ValueError('Forbidden endpoint')
  time.sleep(1.3)
  r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':self.token},json=body,timeout=55)
  if not r.ok:raise RuntimeError('WB advertising HTTP '+str(r.status_code))
  return r.json() if r.content else {}
 def campaigns(self,ids):
  cs=self.req('/api/advert/v2/adverts?ids='+','.join(map(str,ids)))['adverts']
  if {c['id'] for c in cs}!=set(ids):raise RuntimeError('Incomplete campaigns')
  return {str(c['id']):c for c in cs}
 def minimums(self,cid,nms,placement):
  kind='recommendation' if placement=='recommendations' else 'search'
  j=self.req('/api/advert/v1/bids/min','POST',dict(advert_id=int(cid),nm_ids=nms,payment_type='cpc',placement_types=[kind]));out={}
  for row in j.get('bids',[]):
   vs=[v for v in row.get('bids',[]) if v.get('currency')=='CNY' and v.get('type')==kind]
   if len(vs)!=1 or type(vs[0].get('value')) is not int or vs[0]['value']<=0:raise RuntimeError('Unverified minimum')
   out[row['nm_id']]=vs[0]['value']
  if set(out)!=set(nms):raise RuntimeError('Incomplete minimums')
  return out
def validate_identity(c,w):
 root=c.url.rsplit('/',1)[0]
 cfg=requests.get(root+'/business_agent_config',params=dict(agent_id='eq.china',select='active,chat_id,bot_id,owner_user_id'),headers=c.h,timeout=30)
 if not cfg.ok or cfg.json()!=[dict(active=True,chat_id=-1004342917488,bot_id=8780468043,owner_user_id=5122667182)]:raise RuntimeError('Registered owner scope changed')
 raw=w.token.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
 if claims.get('t') is not False or claims.get('exp',0)<=time.time() or int(claims.get('s',0))&(1<<30):raise RuntimeError('WB token scope invalid')
 ids=requests.get(root+'/analytics_snapshots',params=dict(cabinet='eq.token_3',source='eq.seller_identity',status='eq.complete',select='payload',limit=100),headers=c.h,timeout=30)
 if not ids.ok or {x['payload'].get('sid') for x in ids.json()}!={claims.get('sid')}:raise RuntimeError('Seller identity changed')
def initial(c):
 shared=c.get('china_agent:all_campaigns_owner_review:2026-10-25:late:v1') or {}
 extra=c.get('china_agent:expanded_tests:2026-10-25:slot22:v1') or {}
 stats=list(shared.get('fullstats_0',{}).get('data',[]))+list(extra.get('fullstats',{}).get('data',[]))
 cs={str(x['id']):x for x in shared.get('campaigns',{}).get('data',{}).get('adverts',[])}
 cs.update({str(x['id']):x for x in extra.get('campaigns',{}).get('data',{}).get('adverts',[])})
 registry=c.get('china_agent:verified_campaign_state:v1') or {}
 for cid,key in registry.items():
  e=c.get(key) or {}
  if e.get('status')=='verified' and str(e.get('after',{}).get('id'))==cid:
   cs[cid]=e['after']
   if e.get('baseline_fullstats'):stats=[s for s in stats if str(s['advertId'])!=cid]+e['baseline_fullstats']
 normalized=[]
 for st in stats:
  days=[d for d in st.get('days',[]) if d['date'][:10]>='2026-10-25']
  n=dict(advertId=st['advertId'],days=days)
  for f in FIELDS.values():n[f]=sum(d.get(f,0) for d in days)
  normalized.append(n)
 cc,ss=counts(normalized)
 return dict(version=1,baselines=ss,previous_delta={},previous_counters=ss,previous_campaign_counters=cc,campaigns=cs,last_observed_at='2026-10-25T20:22:48+00:00',registry=registry,baseline_is_cached=True)
def snapshot(c,w,slot):
 inv=w.req('/adv/v1/promotion/count')
 ids=sorted({x['advertId'] for g in inv.get('adverts',[]) if g['status'] in [4,7,9,11] for x in g.get('advert_list',[])})
 if len(ids)>50:raise RuntimeError('Campaign pagination required')
 campaigns=w.campaigns(ids) if ids else {}
 budgets=w.req('/api/advert/v2/budget','POST',dict(advertIds=ids)).get('adverts',[]) if ids else []
 ids=[int(cid) for cid,x in campaigns.items() if x['status']==9]
 stats=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-25&endDate='+slot[:10]) if ids else []
 if not isinstance(stats,list):raise RuntimeError('Incomplete statistics')
 missing=set(ids)-{s['advertId'] for s in stats}
 for cid in missing:c.notice('missing-stats:'+str(cid)+':'+slot[:10],'РК '+str(cid)+': рекламная статистика отсутствует; это не нулевой расход.')
 return dict(slot=slot,observed_at=stamp(),campaigns=campaigns,budgets={str(x['advertId']):x for x in budgets},stats=stats,complete=True)
def execute(c,w,slot,before,items,snap):
 cid=str(before['id']);key=ROOT+'execution:'+slot+':'+cid+':'+digest(items)[:16]+':execution';old=c.get(key)
 expected=expected_campaign(before,items)
 if old:
  if old['status']=='verified':return old
  raise RuntimeError('Prior write unresolved: no retry')
 p=c.get(POLICY)
 if not authorized(p,now()) or p.get('executor')!='github-cloud-v1':raise RuntimeError('Write authorization expired or changed')
 allowed=p.get('allowed',[])
 for x in items:
  permission=dict(lower='decrease_bid_above_fresh_WB_minimum',exclude='exclude_underperforming_sku',pause='pause_underperforming_campaign_if_item_level_action_insufficient')[x['kind']]
  if permission not in allowed or (x['kind']=='pause' and p.get('pause_authorized') is not True):raise RuntimeError('Action forbidden by current owner policy')
 if projection(w.campaigns([int(cid)])[cid])!=projection(before):raise RuntimeError('Campaign changed before write')
 kinds={x['kind'] for x in items}
 if kinds=={'pause'}:path='/adv/v0/pause?id='+cid;method='GET';body=None
 elif kinds=={'exclude'}:path='/adv/v0/auction/nms';method='PATCH';body={'nms':[dict(advert_id=int(cid),nms=dict(add=[],delete=[x['nm'] for x in items]))]}
 elif kinds=={'lower'}:path='/api/advert/v1/bids';method='PATCH';body={'bids':[dict(advert_id=int(cid),nm_bids=[dict(nm_id=x['nm'],bid_kopecks=x['target'],placement=x['placement']) for x in items])]}
 else:raise ValueError('Stage must have one action kind')
 e=dict(status='submitting',before=before,expected=expected,items=items,policy_key=POLICY,source_snapshot=ROOT+'snapshot:'+slot,baseline_observed_at=snap['observed_at'],baseline_fullstats=[s for s in snap['stats'] if str(s['advertId'])==cid],submitted_at=stamp(),funding_writes=0,telegram_sends=0)
 if not c.create(key,e):raise RuntimeError('Duplicate execution')
 c.put(ROOT+'inflight:v1',{'key':key})
 try:w.req(path,method,body,write=True);e['status']='accepted';c.put(key,e)
 except Exception:e['status']='uncertain';c.put(key,e);raise RuntimeError('WB write result uncertain; never repeat')
 for attempt in range(4):
  got=w.campaigns([int(cid)])[cid]
  if projection(got)==projection(expected):
   e.update(status='verified',after=got,verified_at=stamp());c.put(key,e)
   reg=c.get('china_agent:verified_campaign_state:v1') or {};reg[cid]=key;c.put('china_agent:verified_campaign_state:v1',reg)
   c.put(ROOT+'inflight:v1',{'key':None})
   alias_items=[dict(id=cid+':'+str(x['nm']),campaign_id=int(cid),nm_id=x['nm'],article=x['article'],kind=dict(lower='ad_set_bid',exclude='ad_exclude_sku',pause='ad_pause_campaign')[x['kind']],target_minor=x.get('target'),status='verified',before=before,after=got,verified_at=e['verified_at'],source_execution_key=key) for x in items]
   c.put('china_agent:ad_rule_execution:cloud-hourly-'+digest(key)[:20]+':v1',dict(status='done',alias_of_verified_batch=True,canonical_source_execution_key=key,wb_writes=0,actual_batch_writes=1,items=alias_items))
   text='Автоизменение РК '+cid+': '+('; '.join(x['article']+' — '+dict(lower='снижение ставки',exclude='исключение',pause='пауза РК')[x['kind']]+((' '+str(x['old']/100)+' → '+str(x['target']/100)+' CNY') if x['kind']=='lower' else '') for x in items))+'. WB подтвердил.'
   c.notice(key,text,e);return e
  if attempt<3:time.sleep(12)
 e['status']='readback_pending';c.put(key,e);raise RuntimeError('WB readback pending; no retry')
def telegram_funding(c,p,cid,summary,remaining,need,slot,ec):
 if not p.get('telegram_budget_requests',{}).get('enabled') or ec.get('all_costs_confirmed') is not True or ec.get('expected_total_profit_cny',-1)<=0:return False
 key=ROOT+'funding:'+cid+':'+slot[:10]
 if c.get(key):return False
 rate=drr(summary)
 if rate is None or rate>5:return False
 text=f"Пополнение РК {cid}\nДРР: {rate:.2f}% (с 25.10 по текущий срез)\nОстаток: {remaining:.2f} CNY\nПредлагаю {need:.0f} CNY примерно на 3 дня текущего темпа.\nСрез: {slot} МСК. Пополнение требует вашего подтверждения."
 if not c.create(key,dict(status='sending',text=text,chat_id=-1004342917488,created_at=stamp())):return False
 try:
  bot=os.environ['CHINA_TELEGRAM_BOT_TOKEN'];me=requests.get('https://api.telegram.org/bot'+bot+'/getMe',timeout=25).json()
  if not me.get('ok') or me['result']['id']!=8780468043:raise RuntimeError('Bot identity changed')
  j=requests.post('https://api.telegram.org/bot'+bot+'/sendMessage',json=dict(chat_id=-1004342917488,text=text),timeout=35).json()
  if not j.get('ok') or j['result']['chat']['id']!=-1004342917488:raise RuntimeError('Unconfirmed funding delivery')
  c.put(key,dict(status='sent',text=text,chat_id=-1004342917488,message_id=j['result']['message_id'],sent_at=stamp()));return True
 except Exception:
  c.put(key,dict(status='uncertain',text=text,chat_id=-1004342917488));c.notice(key,'Запрос пополнения РК '+cid+': результат Telegram не подтверждён, повтор заблокирован.');return False

def shared_payload(snap):
 return dict(observed_at=snap['observed_at'],source_key=ROOT+'snapshot:'+snap['slot'],campaigns=list(snap['campaigns'].values()),ad_batches=[dict(ids=[x['advertId'] for x in snap['stats']],data=snap['stats'])],budgets=list(snap['budgets'].values()),complete=True)
def run(preflight=False,cutover=False):
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise RuntimeError('Public runner only')
 c=Cache();p=c.get(POLICY)
 if not p or p.get('cabinet')!='token_3':raise RuntimeError('Owner policy missing')
 if preflight:
  state=initial(c)
  if len(state['campaigns'])<16:raise RuntimeError('Initial campaign coverage incomplete')
  if not c.get(ROOT+'tracking:v1'):c.create(ROOT+'tracking:v1',state)
  c.put(ROOT+'deployment:v1',dict(status='preflight_verified',observed_at=stamp(),campaign_count=len(state['campaigns']),wb_requests=0,wb_writes=0,telegram_sends=0,workflow_run=os.environ.get('GITHUB_RUN_ID')))
  print('Cloud preflight verified; no WB requests, writes or Telegram sends');return
 if os.environ.get('GITHUB_REF')!='refs/heads/main' or (os.environ.get('GITHUB_EVENT_NAME') not in ['schedule','workflow_dispatch'] and not (cutover and os.environ.get('GITHUB_EVENT_NAME')=='push')):raise RuntimeError('Live main schedule only')
 if cutover and c.get(ROOT+'cutover_probe:v1'):print('Cutover probe already completed');return
 if p.get('executor')!='github-cloud-v1':print('Cloud executor not active');return
 local=now().astimezone(ZoneInfo('Europe/Moscow'))
 slot=(local.replace(minute=10,second=0,microsecond=0) if local.minute>=10 else (local-timedelta(hours=1)).replace(minute=10,second=0,microsecond=0)).isoformat()
 owner=os.environ.get('GITHUB_RUN_ID','unknown')
 if not c.lease(owner):print('Writer lease held');return
 try:
  if c.get(ROOT+'slot:'+slot):print('Slot already claimed');return
  state=c.get(ROOT+'tracking:v1') or initial(c);w=WB();validate_identity(c,w)
  inflight=c.get(ROOT+'inflight:v1') or {}
  if inflight.get('key'):
   e=c.get(inflight['key']);got=w.campaigns([e['before']['id']])[str(e['before']['id'])]
   if projection(got)!=projection(e['expected']):raise RuntimeError('Uncertain prior write blocks new writes')
   e.update(status='verified',after=got,verified_at=stamp());c.put(inflight['key'],e);c.put(ROOT+'inflight:v1',{'key':None})
   reg=c.get('china_agent:verified_campaign_state:v1') or {};reg[str(got['id'])]=inflight['key'];c.put('china_agent:verified_campaign_state:v1',reg)
   c.notice(inflight['key'],'Отложенная проверка WB подтвердила изменение РК '+str(got['id'])+'.',e)
  if not c.create(ROOT+'slot:'+slot,dict(status='running',run_id=owner,started_at=stamp())):return
  snap=snapshot(c,w,slot);c.put(ROOT+'snapshot:'+slot,snap)
  cc,ss=counts(snap['stats']);record_time_observation(c,state,snap,cc);price_cache=c.get('china_agent:prices:v1') or {};prices={str(x['nmID']):x for x in price_cache.get('rows',[])}
  historical=c.get('china_agent:new_ad_source:v1:2026-10-25') or {};products={str(x['nm_id']):x for x in historical.get('products',[])}
  baselines=state.setdefault('baselines',{});previous=state.get('previous_delta',{});current_delta={};actions=[];rows=[]
  registry=c.get('china_agent:verified_campaign_state:v1') or {}
  for cid,key in registry.items():
   if state.get('registry',{}).get(cid)==key:continue
   e=c.get(key) or {}
   if e.get('status')!='verified':raise RuntimeError('Registry receipt not verified')
   normalized=[]
   for st in e.get('baseline_fullstats',[]):
    days=[d for d in st.get('days',[]) if d['date'][:10]>='2026-10-25'];n=dict(advertId=st['advertId'],days=days)
    for f in FIELDS.values():n[f]=sum(d.get(f,0) for d in days)
    normalized.append(n)
   _,newbases=counts(normalized)
   for item in e.get('items',[]):
    nm=item.get('nm_id',item.get('nm'));k=cid+':'+str(nm)
    if k in newbases:baselines[k]=newbases[k];previous.pop(k,None)
  for cid,camp in snap['campaigns'].items():
   if camp['status']!=9:continue
   if cid not in cc:continue
   if camp['currency']!='CNY' or camp['settings']['payment_type']!='cpc' or camp['bid_type']!='manual':
    c.notice('unsupported:'+cid,'РК '+cid+': настройки не поддержаны для безопасного автоснижения.');continue
   placements=camp['settings']['placements'];placement='search' if placements==dict(search=True,recommendations=False) else 'recommendations' if placements==dict(search=False,recommendations=True) else None
   if not placement:continue
   candidates=[]
   for member in camp['nm_settings']:
    nm=str(member['nm_id']);k=cid+':'+nm;counter=ss.get(k,zero())
    if k not in baselines:baselines[k]=counter.copy()
    change=delta(counter,baselines[k]);current_delta[k]=change
    pr=prices.get(nm,{});sizes=pr.get('sizes',[]);price=sizes[0].get('discountedPrice') if sizes and pr.get('currencyIsoCode4217')=='CNY' else None
    article=pr.get('vendorCode',nm);own=products.get(nm,{})
    r=dict(cid=cid,nm=int(nm),article=article,price=price,delta=change,counters=counter,bid=member['bids_kopecks'][placement],placement=placement,buyout=dict(paid=own.get('is_payed'),finished=own.get('finished_orders'),period_to=historical.get('period_to')),price_observed_at=price_cache.get('observed_at'),profit=None,profit_unknown_reason='Complete cohort costs not verified; unknown is not zero')
    rows.append(r);reason=risk(change,price,previous.get(k))
    if reason and authorized(p,now()) and not cutover:r['reason']=reason;candidates.append(r)
   if candidates:
    mins=w.minimums(cid,[r['nm'] for r in candidates],placement);lowers=[];excludes=[]
    for r in candidates:
     item=dict(nm=r['nm'],article=r['article'],placement=placement,old=r['bid'],reason=r['reason'],counters=r['delta']);minimum=mins[r['nm']]
     if 0<minimum<r['bid']:lowers.append(item|dict(kind='lower',target=minimum))
     elif minimum==r['bid']:excludes.append(item|dict(kind='exclude'))
    if len(excludes)==len(camp['nm_settings']):
     if p.get('pause_authorized') is True and 'pause_underperforming_campaign_if_item_level_action_insufficient' in p.get('allowed',[]):excludes=[dict(kind='pause',article='вся РК',nm=0,reason='all_active_skus_ineffective')]
     else:
      c.notice('pause-proposal:'+cid+':'+slot[:10],'РК '+cid+': все активные SKU достигли сигнала неэффективного расхода. Автопауза владельцем запрещена; РК оставлена активной, требуется отдельное решение.',dict(candidates=excludes));excludes=[]
    for items in [lowers,excludes]:
     if not items:continue
     e=execute(c,w,slot,camp,items,snap);actions.append(dict(cid=cid,items=items,verified_at=e['verified_at']));camp=e['after'];snap['campaigns'][cid]=camp
     for x in items:
      if x['nm']:baselines[cid+':'+str(x['nm'])]=ss.get(cid+':'+str(x['nm']),zero()).copy();current_delta[cid+':'+str(x['nm'])]=zero()
   old_summary=state.get('previous_campaign_counters',{}).get(cid);summary=cc.get(cid,zero());budget=snap['budgets'].get(cid,{}).get('total')
   if old_summary and budget is not None:
    elapsed=max((datetime.fromisoformat(snap['observed_at'])-datetime.fromisoformat(state['last_observed_at'])).total_seconds()/3600,.01)
    speed=(summary['spend']-old_summary['spend'])/elapsed
    if speed>0 and budget<speed*1.25 and camp['status']==9 and not cutover:
     rate=drr(summary);ec=(c.get('china_agent:hourly_economics:v1') or {}).get(cid,{})
     if rate is not None and rate<=5 and ec.get('all_costs_confirmed') is True and ec.get('expected_total_profit_cny',-1)>0:
      telegram_funding(c,p,cid,summary,budget,math.ceil(max(speed*72-budget,1)/50)*50,slot,ec)
     else:c.notice('budget-risk:'+cid+':'+slot[:10],'РК '+cid+': остатка '+str(budget)+' CNY может не хватить до следующей проверки; пополнение не запрошено — эффективность или полная экономика не подтверждены.',dict(summary=summary,hourly_speed_cny=speed))
  for cid,old_c in state.get('campaigns',{}).items():
   new=snap['campaigns'].get(cid)
   if old_c.get('status')==9 and (not new or new.get('status')!=9) and not any(a['cid']==cid for a in actions):c.notice('unexpected-stop:'+cid+':'+slot[:10],'РК '+cid+' больше не активна; автоматическое возобновление запрещено.')
  if not authorized(p,now()):c.notice('autonomy-expired','Пробные двое суток автоснижения завершены. Почасовой контроль продолжается без WB-изменений; нужен пересмотр режима.')
  state.update(previous_delta=current_delta,previous_counters=ss,previous_campaign_counters=cc,last_observed_at=snap['observed_at'],campaigns=snap['campaigns'],last_slot=slot,last_rows=rows,last_actions=actions,registry=c.get('china_agent:verified_campaign_state:v1') or {})
  c.put(ROOT+'tracking:v1',state);c.put(ROOT+'analysis:'+slot,dict(status='completed',observed_at=snap['observed_at'],rows=rows,actions=actions,campaigns=cc,autonomy_active=authorized(p,now()),attribution_preliminary=True))
  c.put('china_agent:advertising_intraday:'+slot[:10]+':v1',shared_payload(snap))
  c.put(ROOT+'slot:'+slot,dict(status='completed',run_id=owner,completed_at=stamp(),actions=len(actions)))
  c.put(ROOT+'health:v1',dict(status='healthy',last_slot=slot,observed_at=stamp(),run_id=owner))
  if cutover:c.put(ROOT+'cutover_probe:v1',dict(status='verified',slot=slot,observed_at=stamp(),campaign_count=len(snap['campaigns']),wb_writes=0,telegram_sends=0,run_id=owner))
  print('Hourly cloud check completed; operational data saved privately')
 except Exception as ex:
  c.notice('blocker:'+type(ex).__name__+':'+str(ex),'Облачный рекламный контроль: '+str(ex)+'. Записи с неопределённым результатом не повторяются.')
  c.put(ROOT+'health:v1',dict(status='blocked',last_slot=slot,observed_at=stamp(),error_type=type(ex).__name__))
  raise RuntimeError('Hourly cloud check needs attention') from None
 finally:c.release(owner)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--preflight',action='store_true');parser.add_argument('--cutover',action='store_true');args=parser.parse_args();run(args.preflight,args.cutover)
