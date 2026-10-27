"""15:00 MSK current-day-only report; read-only collection, explicit page approvals."""
import os,json,base64,io as bio
from datetime import datetime,timezone,timedelta,date
from PIL import Image,ImageDraw
from china_advertising_v2 import collect,build,http,price_map,history,daily_metrics,sums,ratio,MSK
from china_advertising_v2_png import font,money,pct,color
ZERO=dict(spend=0,amount=0,orders=0,views=0,clicks=0)

def post_change_pending(changes,cid,nm,day,campaign=None):
 # SKU changes apply across placements; explicit campaign launch protects every member.
 cutoff=date.fromisoformat(day)
 def pending(at):
  changed=datetime.fromisoformat(at.replace('Z','+00:00'))
  if changed.tzinfo is None:raise ValueError('Change timestamp has no timezone')
  return cutoff<=changed.astimezone(MSK).date()+timedelta(days=1)
 started=(campaign or {}).get('timestamps',{}).get('started')
 if started and pending(started):return True
 return any(x.get('nm')==nm and x.get('kind') in ['bid','added','price','returned','relaunch']
            and pending(x['at']) for x in changes)

def revise_midday_bundle(bundle,source,records):
 # Owner correction of a frozen report: filter only; never collect or invent new actions.
 import copy
 out=copy.deepcopy(bundle);changes=history(records)
 campaigns={c['id']:c for batch in source['batches'].values()
            for c in batch['campaigns'].get('adverts',[])}
 removed=[]
 for row in out['campaigns']:
  campaign=campaigns.get(row['id'])
  if campaign is None:raise ValueError('Frozen campaign is missing')
  kept=[]
  for item in row['attention']:
   action=item['action']
   if post_change_pending(changes,row['id'],action['nm_id'],out['day'],campaign):
    removed.append(action);continue
   kept.append(item)
  row['attention']=kept
  if removed and any(x['campaign_id']==row['id'] for x in removed):
   row['post_change_note']='Тест после запуска или изменения: ждём завершения полного следующего дня МСК. Исключение и снижение пока не предлагаем.'
 out['correction']=dict(rule='full_following_msk_day_v2',removed_actions=removed)
 return out

def current_report_context(io,source,day):
 # Read the canonical journal even when a resumable source froze its older history.
 records=list(source.get('executions',[]));seen={r.get('cache_key') for r in records}
 registry=io.get('china_agent:verified_campaign_state:v1') or {}
 if not isinstance(registry,dict):raise ValueError('Campaign registry malformed')
 pointers={}
 for cid,key in registry.items():
  if not isinstance(key,str):continue
  receipt=io.get(key) or {};after=receipt.get('after')
  if receipt.get('status')!='verified' or not isinstance(after,dict) or str(after.get('id'))!=str(cid):raise ValueError('Canonical campaign receipt not verified: '+str(cid))
  pointers[str(cid)]=key
  if key not in seen:records.append(dict(cache_key=key,payload=receipt));seen.add(key)
 from china_budget_context import read_context
 manual=read_context(io.get,datetime.now(timezone.utc))
 return records,dict(verified_registry=pointers,manual_funding=manual,wb_writes=0)

def prepare_midday(io,day):
 source=collect(io,day,current=True)
 records,context=current_report_context(io,source,day)
 labels=price_map(source['catalogue']);changes=history(records);out=[]
 for batch in source['batches'].values():
  raw={r['advertId']:r for r in batch['stats']}
  for c in batch['campaigns'].get('adverts',[]):
   draft=c['status']==4 and c.get('timestamps',{}).get('started') is None
   rec=raw.get(c['id']);d=next((x for x in (rec or {}).get('days',[]) if x['date'][:10]==day),None)
   metric=daily_metrics(d) if d else dict(ZERO) if rec else None
   skus={}
   for app in (d or {}).get('apps',[]):
    for n in app.get('nms',[]):
     v=skus.setdefault(n['nmId'],dict(ZERO))
     for k,x in daily_metrics(n).items():v[k]+=x
   attention=[];protected=False;placement='search' if c['settings']['placements'].get('search') else 'recommendations'
   # Only direct current SKU evidence; no 3-day actions carried into an intraday PNG.
   for n in c.get('nm_settings',[]):
    nm=n['nm_id'];p=skus.get(nm);label=labels.get(nm,{});price=label.get('price');old=n.get('bids_kopecks',{}).get(placement)
    if c['status']!=9 or not p or not isinstance(price,(int,float)) or price<=0 or type(old)is not int:continue
    # A bid change/addition today invalidates whole-day spend as a post-change exposure.
    if post_change_pending(changes,c['id'],nm,day,c):
     protected=True;continue
    if p['orders']!=0 or p['spend']<price*.05 or p['clicks']<30:continue
    article=label.get('article','')
    if not article or article.startswith('WB '):continue
    typ='search' if placement=='search' else 'recommendation'
    j=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=c['id'],nm_ids=[nm],payment_type='cpc',placement_types=[typ]))
    bids=[v['value'] for row in j.get('bids',[]) if row['nm_id']==nm for v in row.get('bids',[]) if v.get('type')==typ and v.get('currency')=='CNY']
    if len(bids)!=1:raise ValueError('Fresh WB minimum incomplete')
    action=None
    if old>bids[0]:
     target=max(bids[0],int(old*.8))
     action=dict(kind='ad_set_bid',campaign_id=c['id'],nm_id=nm,placement=placement,old_minor=old,target_minor=target)
     decision='Снизить '+money(old/100)+' → '+money(target/100)+' ¥.'
    elif len(c['nm_settings'])>1 and c.get('restrictions',{}).get('can_change_nms'):
     action=dict(kind='ad_exclude_sku',campaign_id=c['id'],nm_id=nm,placement=placement,old_minor=old)
     decision='Исключить из этой РК.'
    if action:
     action.update(id=str(c['id'])+':'+str(nm),article=article)
     attention.append(dict(article=article,decision=decision,action=action,spend=p['spend'],clicks=p['clicks']))
   # Do not propose to empty a campaign via individual approvals.
   if len(attention)==len(c.get('nm_settings',[])):attention=[]
   out.append(dict(id=c['id'],name=c['settings']['name'],draft=draft,today=metric,attention=attention,post_change_note=('Тест после запуска или изменения: полный следующий день МСК ещё не завершён; ставки и состав сохраняем.' if protected else None)))
 if not out:raise ValueError('Empty midday catalogue')
 return dict(day=day,observed_at=source.get('completed_at',source['observed_at']),campaigns=out,presentation='midday_green_current_day_v1',review_context=context)
def recommendations(c):
 p=c['today']
 if c['draft']:return ['Черновик: не запускалась.']
 if p is None:return ['Статистика отсутствует; вывод не подтверждён.']
 if c.get('post_change_note') and not c['attention']:return [c['post_change_note']]
 if c['attention']:return ([r['article']+': за сегодня '+money(r['spend'])+' ¥, '+str(int(r['clicks']))+' кликов, 0 рекламных заказов. '+r['decision'] for r in c['attention']]+([c['post_change_note']] if c.get('post_change_note') else []))
 if not p['spend']:return ['Расхода нет. Изменений не требуется.']
 if p['amount']==0:return ['За сегодня потрачено '+money(p['spend'])+' ¥; рекламных заказов нет. Подтверждённых новых действий по SKU нет.']
 if ratio(p)>5:return ['ДРР выше цели. День не завершён; оснований для нового точечного действия по проверенным SKU нет.']
 return ['ДРР в пределах цели. Изменений не требуется.']
def render_midday(b):
 W=2400;H=6500;xs=[44,480,780,1050,1650,2356];files=[];green='#196b44'
 def wrap(d,s,w,n=27):
  out=[]
  for par in str(s).split('\n'):
   line=''
   for word in par.split():
    t=(line+' '+word).strip()
    if line and d.textlength(t,font=font(n))>w:out.append(line);line=word
    else:line=t
   out.append(line)
  return out
 def canvas():
  im=Image.new('RGB',(W,H),'#edf7f0');d=ImageDraw.Draw(im);d.rectangle((0,0,W,205),fill=green)
  d.text((44,28),'Китай · промежуточный отчёт · 15:00',font=font(48,True),fill='white')
  d.text((44,100),'Текущий день: '+b['day']+' · с 00:00 МСК · цель ДРР 5%',font=font(29,True),fill='white')
  obs=datetime.fromisoformat(b['observed_at'].replace('Z','+00:00')).astimezone(MSK).strftime('%d.%m.%Y %H:%M МСК')
  d.text((44,150),'Фактический срез: '+obs,font=font(24),fill='white')
  for i,label in enumerate(['Кампания WB','Расход, CNY','ДРР сегодня','Результат сегодня','Рекомендации']):
   for j,line in enumerate(wrap(d,label,xs[i+1]-xs[i]-30,29)):d.text((xs[i],235+j*35),line,font=font(29,True),fill=green)
  return im,d
 def finish(im,y,acts):
  f=bio.BytesIO();im.crop((0,0,W,min(H,y+30))).save(f,format='PNG');files.append(dict(family='drr',bytes=f.getvalue(),actions=acts))
 im,d=canvas();y=330;acts=[]
 for c in b['campaigns']:
  p=c['today'];draft=c['draft']
  result='Не запускалась' if draft else 'Нет данных' if p is None else 'Рекламные заказы: '+str(int(p['orders']))+'\nСумма: '+money(p['amount'])+' ¥\nКлики: '+str(int(p['clicks']))
  cells=[str(c['id'])+'\n'+c['name'],'Не запускалась' if draft else money(p['spend'] if p else None)+' ¥','Не применима' if draft else pct(p),result,'\n'.join(recommendations(c))]
  ls=[wrap(d,s,xs[i+1]-xs[i]-36) for i,s in enumerate(cells)];h=max(145,max(map(len,ls))*35+36)
  if h>4800:raise ValueError('Midday row too long')
  if y+h>5500:finish(im,y,acts);im,d=canvas();y=330;acts=[]
  d.rounded_rectangle((24,y,W-24,y+h),18,fill='white')
  for i,lines in enumerate(ls):
   for j,line in enumerate(lines):d.text((xs[i],y+18+j*35),line,font=font(27),fill=color(p) if i==2 else '#111111')
  acts.extend(r['action'] for r in c['attention']);y+=h+12
 known=[c['today'] for c in b['campaigns'] if c['today'] is not None]
 total=None if any(c['today'] is None and not c['draft'] for c in b['campaigns']) else sums(known)
 d.rounded_rectangle((24,y+10,W-24,y+160),18,fill=green)
 d.text((44,y+30),'ИТОГО · Китай · только текущий день',font=font(29,True),fill='white')
 d.text((44,y+85),'Расход: '+money(total['spend'] if total else None)+' ¥   |   ДРР: '+pct(total)+'   |   Рекламных заказов: '+str(int(total['orders']) if total else 'нет данных'),font=font(29,True),fill='white')
 foot='День не завершён; возможна поздняя атрибуция. ДРР = сумма расходов / сумму рекламных заказов до скидок WB. Нет заказов — ДРР не вычисляется. Атрибуция не равна выкупам и прибыли. Только новые действия этого PNG исполняются после отдельного ответа «Сделай всё»; автоматических изменений нет.'
 for j,line in enumerate(wrap(d,foot,W-88,24)):d.text((44,y+188+j*31),line,font=font(24),fill='#536b79')
 finish(im,y+220+len(wrap(d,foot,W-88,24))*31,acts)
 for i,f in enumerate(files,1):f.update(kind='drr:'+str(i).zfill(3),page=i,total=len(files))
 return files
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 from china_price_apply import IO
 from china_advertising_delivery import deliver,telegram_sender
 from china_daily_ad_actions import plan,bind
 io=IO();day=datetime.now(MSK).date().isoformat();key='china_agent:advertising_midday_delivery:'+day+':v1'
 if (io.get(key) or {}).get('status')=='delivered':print('already_delivered');return
 art='china_agent:advertising_midday_artifacts:'+day+':v1';saved=io.get(art)
 if not saved:
  b=prepare_midday(io,day);files=[]
  for i,f in enumerate(render_midday(b)):
   p=plan(io,day,f,i,slot='midday')
   files.append(dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],action_count=len(p['items']),b64=base64.b64encode(f['bytes']).decode()))
  saved=dict(day=day,status='frozen',bundle=b,files=files)
  if not io.create(art,saved):saved=io.get(art)
 if saved.get('day')!=day or saved.get('status')!='frozen':raise ValueError('Midday artifact scope mismatch')
 files=[]
 for f in saved['files']:
  cap='Китай · промежуточный отчёт · '+day+' · '+str(f['page'])+'/'+str(f['total'])+'. '
  cap+=('Ответьте «Сделай всё» для '+str(f['action_count'])+' новых действий только этого PNG.' if f['action_count'] else 'Новых действий для исполнения нет.')
  files.append(dict(f,bytes=base64.b64decode(f['b64'],validate=True),caption=cap))
 r=deliver(io,day,files,telegram_sender(io),binder=lambda f,r:bind(io,f,r),delivery_key=key,expected_families={'drr'})
 print(json.dumps(dict(status=r['status'],day=day,wb_writes=0)))
if __name__=='__main__':run()
