"""Concrete DRR rule plans, reply-bound owner approval, isolated verified SKU writes."""
import base64,copy,hashlib,json,re
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from urllib.parse import urlparse,parse_qs
from china_loss_control import CHAT,BOT,OWNER,PLAN,APPROVAL,digest,is_all,marker
_READ=None
@contextmanager
def reads():
 global _READ
 old=_READ;_READ={}
 try:yield _READ
 finally:_READ=old
def allowed_read(method,url,body):
 if _READ is None:return False
 u=urlparse(url)
 if u.scheme!='https' or u.hostname!='advert-api.wildberries.ru':return False
 if method.upper()=='GET' and u.path=='/adv/v1/promotion/count':return not u.query
 if method.upper()=='GET' and u.path=='/api/advert/v2/adverts':
  q=parse_qs(u.query);return set(q)=={'ids'} and len(q['ids'])==1 and bool(re.fullmatch(r'\d+(?:,\d+){0,49}',q['ids'][0]))
 if method.upper()=='POST' and u.path=='/api/advert/v1/bids/min' and isinstance(body,dict):
  return set(body)=={'advert_id','nm_ids','payment_type','placement_types'} and body.get('advert_id') in _READ and body['payment_type']=='cpc' and body['placement_types']==['recommendation'] and isinstance(body['nm_ids'],list) and 0<len(body['nm_ids'])<=100 and set(body['nm_ids'])<=_READ[body['advert_id']]
 return False
def minimums(io,campaign,ids):
 from china_loss_ads import http
 j=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=campaign,nm_ids=sorted(ids),payment_type='cpc',placement_types=['recommendation']))
 out={}
 for row in j.get('bids',[]):
  v=[v for v in row.get('bids',[]) if v.get('type')=='recommendation' and v.get('currency')=='CNY']
  if len(v)!=1 or type(v[0].get('value')) is not int or v[0]['value']<=0:raise ValueError('Минимум ставки WB не подтверждён')
  out[int(row['nm_id'])]=v[0]['value']
 if set(out)!=set(ids):raise ValueError('Неполные минимумы ставок SKU')
 return out
def items_for(rows,current,mins,min_drr=6):
 result=[]
 for r in rows:
  drr=r.get('drr')
  if drr is None or drr<min_drr or (min_drr==5 and drr<=5):continue
  nm=int(r['nm']);present=[(cid,c) for cid,c in current.items() if (r.get('campaign_id') is None or r['campaign_id']==cid) and any(n['nm_id']==nm for n in c.get('nm_settings',[]))]
  for cid,c in present:
   base=dict(id=str(cid)+':'+str(nm),nm_id=nm,campaign_id=cid,article=r['article'],drr=drr,orders=r.get('orders'))
   n=next(n for n in c['nm_settings'] if n['nm_id']==nm)
   if cid==41155909:result.append(dict(base,kind='needs_data',question='119: требуется отдельное согласование кампании'));continue
   if c.get('status')!=9 or c.get('currency')!='CNY' or c.get('settings',{}).get('payment_type')!='cpc' or c.get('bid_type')!='manual' or c.get('settings',{}).get('placements')!={'search':False,'recommendations':True}:
    result.append(dict(base,kind='needs_data',question='Другой тип/площадки РК — нужен отдельный план'));continue
   if drr>10:
    if not c.get('restrictions',{}).get('can_change_nms') or len(c['nm_settings'])<=1:
     result.append(dict(base,kind='needs_data',question='Нельзя исключить SKU без остановки/ограничения РК'));continue
    result.append(dict(base,kind='ad_exclude_sku'))
   else:
    old=n.get('bids_kopecks',{}).get('recommendations');new=mins.get((cid,nm))
    if type(old) is not int or type(new) is not int or new<=0:result.append(dict(base,kind='needs_data',question='Не подтверждён минимум/текущая ставка'));continue
    if old<=new:continue
    result.append(dict(base,kind='ad_set_bid',old_minor=old,target_minor=new,placement='recommendations'))
 # Removing several SKUs must not empty a campaign collectively.
 for cid,c in current.items():
  removes=[i for i in result if i['campaign_id']==cid and i['kind']=='ad_exclude_sku']
  if len(removes)>=len(c.get('nm_settings',[])):
   for i in removes:i.update(kind='needs_data',question='Все товары РК попали под исключение; нужен отдельный план')
 return result
def campaign_rows(sources,labels):
 grouped={}
 for p in sources:
  catalog=next(o for o in p['observations'] if o.get('tool')=='wbbidder_campaigns' and o['arguments'].get('report')=='state')
  ids={c['id']:c['wb_id'] for c in catalog['data']['data']}
  for o in p['observations']:
   if o.get('tool')!='wbbidder_campaign_stats' or o['arguments'].get('report')!='products':continue
   cid=ids[o['arguments']['campaign_id']]
   for row in o['data']['data']:
    nm=str(row['nm_id']);key=(cid,nm);r=grouped.setdefault(key,dict(nm=nm,campaign_id=cid,article=labels.get(nm,'WB '+nm),spend=0,orders_sum=0,orders=0))
    r['spend']+=row['ac_spending_sum'];r['orders_sum']+=row['ac_orders_sum'];r['orders']+=row['ac_orders']
 for r in grouped.values():r['drr']=100*r['spend']/r['orders_sum'] if r['orders_sum'] else None
 return list(grouped.values())
def plan_recommendations(items):
 out={}
 for i in items:
  if i['kind']=='ad_set_bid':text=f"Ставка {i['old_minor']/100:g} → {i['target_minor']/100:g} ¥; РК {i['campaign_id']}"
  elif i['kind']=='ad_exclude_sku':text='Исключить SKU из РК '+str(i['campaign_id'])
  elif i['kind']=='keep_ad_settings':text=f"Оставить {i['old_minor']/100:g} ¥; РК {i['campaign_id']}"
  elif i['kind']=='keep_outside_ads':text='Оставить вне РК'
  else:text=i['question']
  out.setdefault(str(i['nm_id']),[]).append(text)
 return {nm:'\n'.join(texts) for nm,texts in out.items()}
def prepare_trend_plan(w,job,report,sources):
 from china_loss_ads import current
 from china_price_apply import IO
 selected={r['nm']:r for r in report['rows'] if r['rising_all_days']}
 if not selected:return None,{}
 pid='ad-trend-'+str(job['id']);prior=w.get(PLAN+pid)
 if prior:return prior,plan_recommendations(prior['items'])
 labels={r['nm']:r['article'] for r in selected.values()}
 scoped=[r for r in campaign_rows(sources,labels) if r['nm'] in selected]
 with reads() as scope:
  io=IO();before=current(io);scope.update({cid:{n['nm_id'] for n in c.get('nm_settings',[])} for cid,c in before.items()});mins={}
  for cid,c in before.items():
   ids={int(r['nm']) for r in scoped if r['campaign_id']==cid and r['drr'] is not None and 5<r['drr']<=10}&scope[cid]
   if ids and c.get('currency')=='CNY' and c.get('settings',{}).get('payment_type')=='cpc':
    mins.update({(cid,nm):value for nm,value in minimums(io,cid,ids).items()})
  items=items_for(scoped,before,mins,min_drr=5)
  existing={(i['campaign_id'],i['nm_id']) for i in items}
  for nm,r in selected.items():
   present=False
   for cid,c in before.items():
    n=next((n for n in c.get('nm_settings',[]) if str(n['nm_id'])==nm),None)
    if not n:continue
    present=True
    if (cid,int(nm)) in existing:continue
    old=(n.get('bids_kopecks') or {}).get('recommendations')
    if not isinstance(old,int) or c.get('currency')!='CNY':
     items.append(dict(id=str(cid)+':'+nm,kind='needs_data',nm_id=int(nm),campaign_id=cid,article=r['article'],question='Нужно проверить текущую ставку и валюту РК'))
     continue
    items.append(dict(id=str(cid)+':'+nm,kind='keep_ad_settings',nm_id=int(nm),campaign_id=cid,article=r['article'],old_minor=old,drr=r['drr'],orders=r['orders']))
   if not present:items.append(dict(id='outside:'+nm,kind='keep_outside_ads',nm_id=int(nm),campaign_id=0,article=r['article'],drr=r['drr'],orders=r['orders']))
 p=dict(plan_id=pid,chat_id=CHAT,bot_id=BOT,execution_kind='ad_drr_rule',created_at=w.now.isoformat(),expires_at=(w.now+timedelta(hours=6)).isoformat(),items=items,plan_sha256=digest(items),period_from=report['days'][0],period_to=report['days'][-1],days=report['days'],report_message_ids=[],price_changes=False)
 w.save(PLAN+pid,p,insert=True);p=w.get(PLAN+pid)
 if not p or digest(p['items'])!=p['plan_sha256']:raise ValueError('Frozen recommendation plan mismatch')
 return p,plan_recommendations(p['items'])
def render_plan(p,results=None):
 from PIL import Image,ImageDraw,ImageFont
  # Separate confirmation/result table: no false claim of a growth-only selection.
 def f(n,b=False):
  for path in ['/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if b else '')+'.ttf','C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf')]:
   try:return ImageFont.truetype(path,n)
   except OSError:pass
  return ImageFont.load_default(size=n)
 def wrap(d,text,x,y,width):
  line=''
  for word in text.split():
   v=(line+' '+word).strip()
   if d.textlength(v,font=f(21))>width and line:d.text((x,y),line,font=f(21),fill='#24384f');y+=27;line=word
   else:line=v
  d.text((x,y),line,font=f(21),fill='#24384f')
 pages=[];items=p['items']
 for start in range(0,max(1,len(items)),10):
  rows=items[start:start+10];im=Image.new('RGB',(1700,260+max(1,len(rows))*125+100),'#f3f6fa');d=ImageDraw.Draw(im)
  d.rectangle((0,0,1700,140),fill='#20374f');d.text((25,20),'Китай · '+('результат' if results is not None else 'план по ДРР'),font=f(34,True),fill='white')
  d.text((25,75),p['period_from']+' — '+p['period_to']+' · цены не меняем',font=f(24),fill='white')
  for x,label in [(30,'Артикул'),(420,'ДРР'),(560,'Результат' if results is not None else 'Конкретное действие')]:d.text((x,173),label,font=f(25,True),fill='#20374f')
  for idx,item in enumerate(rows):
   y=230+idx*125;d.rectangle((20,y,1680,y+118),fill='white' if idx%2==0 else '#e6edf6')
   wrap(d,item['article'],30,y+20,370);d.text((420,y+20),f"{item['drr']:.1f}%".replace('.',','),font=f(23),fill='#b9252b')
   if results is not None:text=results.get(item['id'],'Результат ещё не подтверждён')
   elif item['kind']=='ad_set_bid':text=f"Ставка {item['old_minor']/100:g} → {item['target_minor']/100:g} ¥; РК {item['campaign_id']}"
   elif item['kind']=='ad_exclude_sku':text='Исключить только SKU из РК '+str(item['campaign_id'])
   else:text=item['question']+'; РК '+str(item['campaign_id'])
   wrap(d,text.replace('.',',') if False else text,560,y+20,1080)
  note='Цены не менялись. Только проверенный результат WB.' if results is not None else 'Для применения ответьте «Сделай всё» на эту таблицу. До подтверждения — без изменений.'
  wrap(d,note,25,im.height-75,1640)
  import io
  b=io.BytesIO();im.save(b,format='PNG');pages.append(b.getvalue())
 return pages
def bind(w,text,message_id):
 from china_ad_cost_png import PREFIX
 if not text.startswith(PREFIX):return
 key,index=text[len(PREFIX):].rsplit(':',1);saved=w.get(key) or {}
 if not saved or saved.get('chat_id')!=CHAT:return
 w.save('china_agent:ad_cost_message:'+str(message_id),dict(key=key,job_id=saved['job_id'],chat_id=CHAT))
 pid=saved.get('plan_id')
 if not pid:return
 p=w.get(PLAN+pid)
 if not p or p.get('plan_sha256')!=digest(p['items']) or saved.get('plan_sha256')!=p['plan_sha256']:raise ValueError('Plan binding mismatch')
 p['report_message_ids']=sorted(set(p.get('report_message_ids',[])+[message_id]));w.save(PLAN+pid,p)
 w.save('china_agent:ad_rule_message:'+str(message_id),dict(plan_id=pid,plan_sha256=p['plan_sha256'],chat_id=CHAT))
def handle(w,job,history=()):
 from china_daily_ad_actions import handle as daily_handle
 daily_result=daily_handle(w,job)
 if daily_result is not None:return daily_result
 text=job.get('request_text','');m=marker(job)
 if is_all(text):
  binding=w.get('china_agent:ad_rule_message:'+str(m.get('reply_message_id')))
  if not binding:
   if w.get('china_agent:ad_cost_message:'+str(m.get('reply_message_id'))):return ('В этой таблице нет изменений для применения.',[])
   return None
  from china_group_permissions import allowed
  if not allowed(w,job) or m.get('bot_id')!=BOT:return ('Применять план могут действующие участники этой группы.',[])
  p=w.get(PLAN+binding['plan_id'])
  if not p or p.get('plan_sha256')!=digest(p['items']) or p['plan_sha256']!=binding['plan_sha256']:raise ValueError('Plan changed')
  if w.now>datetime.fromisoformat(p['expires_at']):return ('План устарел. Нужна новая проверка ставок и подтверждение обновлённой таблицы.',[])
  a=dict(status='approved',plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],job_id=job['id'],update_id=job['update_id'],sender_id=job['sender_id'],chat_id=CHAT,bot_id=BOT,input_message_id=m.get('message_id'),reply_message_id=m.get('reply_message_id'),created_at=job['created_at'],price_changes=False)
  w.save(APPROVAL+str(job['id']),a,insert=True)
  return ('Принято. Выполню пункты таблицы и проверю результат WB. Цены не меняю.',[dict(name='ad_drr_rule_approval',plan_id=p['plan_id'])])
 if not (re.search(r'д[рдж]р|ддр',text,re.I) and '6' in text and '10' in text and re.search(r'став|миним|убер|исключ',text,re.I)):return None
 from china_three_day_ads import requested_days,load,build,MSK
 from china_ad_cost_png import PREFIX
 from china_loss_ads import current
 from china_price_apply import IO
 try:
  count=requested_days(text,history);sources=load(w,count);today=w.now.astimezone(MSK).date()
  report=build(sources,today,dict(w.catalog()),count)
  rows=[r for r in campaign_rows(sources,dict(w.catalog())) if r['drr'] is not None and r['drr']>=6]
  with reads() as scope:
   io=IO();before=current(io);scope.update({cid:{n['nm_id'] for n in c.get('nm_settings',[])} for cid,c in before.items()});mins={}
   for cid,c in before.items():
    ids={int(r['nm']) for r in rows if r['campaign_id']==cid and 6<=r['drr']<=10}&scope[cid]
    if ids and c.get('currency')=='CNY' and c.get('settings',{}).get('payment_type')=='cpc':
     mins.update({(cid,nm):value for nm,value in minimums(io,cid,ids).items()})
  items=items_for(rows,before,mins)
 except (ValueError,RuntimeError,KeyError,TypeError) as e:return ('План не готов: '+str(e)+'. Артикулы заново присылать не нужно; изменения не выполнялись.',[dict(name='ad_drr_rule_blocked',wb_writes=0)])
 if not items:return ('За выбранный период нет новых действий по правилу ДРР6–10%/выше10%: уже выполненные пункты исключены.',[])
 pid='ad-rule-'+str(job['id']);p=dict(plan_id=pid,chat_id=CHAT,bot_id=BOT,execution_kind='ad_drr_rule',created_at=w.now.isoformat(),expires_at=(w.now+timedelta(hours=6)).isoformat(),items=items,plan_sha256=digest(items),period_from=report['days'][0],period_to=report['days'][-1],report_message_ids=[],price_changes=False,days=report['days'])
 key='china_agent:ad_cost_png:question:'+str(job['id'])+':v1';saved=w.get(key)
 if not saved:
  w.save(PLAN+pid,p,insert=True);p=w.get(PLAN+pid)
  if not p or p['plan_sha256']!=digest(p['items']):raise ValueError('Frozen plan mismatch')
  images=render_plan(p)
  saved=dict(status='frozen',job_id=job['id'],chat_id=job['chat_id'],plan_id=pid,plan_sha256=p['plan_sha256'],days=p['days'],files=[dict(data=base64.b64encode(b).decode(),sha256=hashlib.sha256(b).hexdigest()) for b in images]);w.save(key,saved,insert=True)
 return '\n[[ПРЕДЛОЖЕНИЯ]]\n'.join(PREFIX+key+':'+str(i) for i in range(len(saved['files']))),[dict(name='ad_drr_rule_plan',plan_id=pid,wb_writes=0)]
def verified_item(item,before,after):
 if before.get('status')!=after.get('status') or before.get('settings')!=after.get('settings') or before.get('currency')!=after.get('currency'):return False
 expected=copy.deepcopy(before.get('nm_settings',[]))
 if item['kind']=='ad_exclude_sku':expected=[n for n in expected if n['nm_id']!=item['nm_id']]
 else:
  for n in expected:
   if n['nm_id']==item['nm_id']:n['bids_kopecks']['recommendations']=item['target_minor']
 return sorted(expected,key=lambda n:n['nm_id'])==sorted(after.get('nm_settings',[]),key=lambda n:n['nm_id'])
def execute(io,a,p):
 from china_loss_ads import current,http,nmset,stamp
 io.validate_owner(a)
 if p.get('plan_sha256')!=digest(p['items']) or a['plan_sha256']!=p['plan_sha256']:raise ValueError('Plan hash changed')
 key='china_agent:ad_rule_execution:'+p['plan_id']+':v1';e=io.get(key)
 if not e:
  e=dict(status='running',plan_id=p['plan_id'],items=[],wb_writes=0)
  if not io.create(key,e):return io.get(key)
 for item in p['items']:
  state=next((s for s in e['items'] if s['id']==item['id']),None)
  if state:
   if state['status'] in ('submitting','accepted','uncertain'):
    try:
     after=current(io,[item['campaign_id']])[item['campaign_id']]
     state.update(status='verified' if verified_item(item,state['before'],after) else 'uncertain',after=after)
    except Exception:state['status']='uncertain'
    io.put(key,e)
   continue
  state=dict(id=item['id'],article=item['article'],status='preflight');e['items'].append(state);io.put(key,e)
  try:
   if item['kind']=='needs_data':state.update(status='blocked',reason=item['question']);io.put(key,e);continue
   if datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']):raise ValueError('План устарел')
   if item['kind']=='keep_outside_ads':
    if any(item['nm_id'] in nmset(c) for c in current(io).values()):raise ValueError('SKU появился в РК — требуется новый план')
    state.update(status='verified',already_done=True);io.put(key,e);continue
   before=current(io,[item['campaign_id']])[item['campaign_id']]
   if before.get('currency')!='CNY' or before.get('status')!=9 or before.get('bid_type')!='manual' or before.get('settings',{}).get('payment_type')!='cpc':raise ValueError('Настройки РК изменились')
   selected=next((n for n in before.get('nm_settings',[]) if n['nm_id']==item['nm_id']),None)
   if item['kind']=='keep_ad_settings':
    if not selected or selected.get('bids_kopecks',{}).get('recommendations')!=item['old_minor']:raise ValueError('Ставка уже изменилась — без новых изменений')
    state.update(status='verified',already_done=True);io.put(key,e);continue
   if item['kind']=='ad_exclude_sku':
    if not selected:state.update(status='verified',already_done=True);io.put(key,e);continue
    if not before.get('restrictions',{}).get('can_change_nms') or len(nmset(before))<=1:raise ValueError('Исключение опустошит РК или запрещено WB')
    path='/adv/v0/auction/nms';body=dict(nms=[dict(advert_id=item['campaign_id'],nms=dict(add=[],delete=[item['nm_id']]))])
   elif item['kind']=='ad_set_bid':
    if not selected or before.get('settings',{}).get('placements')!={'search':False,'recommendations':True}:raise ValueError('SKU/площадки изменились')
    current_bid=selected['bids_kopecks']['recommendations']
    if current_bid==item['target_minor']:state.update(status='verified',already_done=True);io.put(key,e);continue
    if current_bid!=item['old_minor'] or not 0<item['target_minor']<current_bid:raise ValueError('Текущая ставка отличается от согласованной')
    if minimums(io,item['campaign_id'],{item['nm_id']})[item['nm_id']]>item['target_minor']:raise ValueError('Минимум WB вырос — нужен новый план')
    path='/api/advert/v1/bids';body=dict(bids=[dict(advert_id=item['campaign_id'],nm_bids=[dict(nm_id=item['nm_id'],bid_kopecks=item['target_minor'],placement='recommendations')])])
   else:raise ValueError('Операция не разрешена')
   state.update(status='submitting',before=before,request=dict(path=path,body=body));io.put(key,e)
   response=http(io,path,'PATCH',body);e['wb_writes']+=1;state.update(status='accepted',response=response,submitted_at=stamp());io.put(key,e)
   after=current(io,[item['campaign_id']])[item['campaign_id']]
   state.update(status='verified' if verified_item(item,before,after) else 'accepted',after=after);io.put(key,e)
  except Exception as ex:
   state.update(status='uncertain' if state['status']=='submitting' else ('accepted' if state['status']=='accepted' else 'blocked'),reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__);io.put(key,e)
 e['status']='done' if all(s['status'] in ('verified','blocked') for s in e['items']) else 'attention';io.put(key,e);return e
def process_and_deliver(io,a,p):
 e=execute(io,a,p)
 if any(s['status']=='accepted' for s in e['items']):return e
 key='china_agent:ad_rule_result:'+p['plan_id']+':v1'
 existing=io.get(key)
 if existing and (existing.get('status')=='sent' or any(x.get('status') in ('sending','uncertain') for x in existing.get('parts',[]))):return e
 info=io.tg('getMe',{})
 if info.get('id')!=BOT:raise ValueError('Result bot mismatch')
 labels={}
 for s in e['items']:
  item=next(i for i in p['items'] if i['id']==s['id'])
  if s['status']=='verified':labels[s['id']]=('Уже выполнено; без повторных изменений' if s.get('already_done') else ('Ставка изменена; проверено WB' if item['kind']=='ad_set_bid' else 'SKU исключён; проверено WB'))
  else:labels[s['id']]='Не выполнено: '+s.get('reason','результат не подтверждён')
 images=render_plan(p,labels)
 if not existing:
  io.create(key,dict(status='ready',files=[base64.b64encode(b).decode() for b in images],parts=[dict(status='ready',sha256=hashlib.sha256(b).hexdigest()) for b in images]))
 state=io.get(key)
 images=[base64.b64decode(b,validate=True) for b in state['files']]
 import requests
 for idx,b in enumerate(images):
  if state['parts'][idx]['status']=='sent':continue
  if hashlib.sha256(b).hexdigest()!=state['parts'][idx]['sha256']:raise ValueError('Result PNG changed')
  state['parts'][idx]['status']='sending';io.put(key,state)
  try:
   r=requests.post('https://api.telegram.org/bot'+io.bot+'/sendPhoto',data=dict(chat_id=CHAT,caption='Результат. Цены не менялись.',reply_parameters=json.dumps(dict(message_id=a['input_message_id']))),files={'photo':('china-ad-result.png',b,'image/png')},timeout=40).json()
   if not r.get('ok') or r['result'].get('chat',{}).get('id')!=CHAT:raise ValueError('Telegram receipt missing')
   state['parts'][idx].update(status='sent',message_id=r['result']['message_id']);io.put(key,state)
  except Exception:
   state['parts'][idx]['status']='uncertain';io.put(key,state);return e
 state['status']='sent';io.put(key,state);return e

