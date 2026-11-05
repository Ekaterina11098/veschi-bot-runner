"""Existing daily delivery adapter: ready recommendations only, frozen reply-bound scope."""
import copy,hashlib,json,math
from datetime import datetime,timedelta,timezone
from pathlib import Path
from advertising_daily_png import font,wrap,rub,pct
from PIL import Image,ImageDraw
CHAT=-1004378639510;BOT=8987327588
PREFIX='advertising:ip:daily-png-plan:v1:'
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def action_id(a):return digest({k:a.get(k) for k in ('campaign','nm','kind','placement','stored_bid_minor','target_bid_minor')})
def completed_or_claimed(store,a):return bool(store.cache_get('advertising:ip:action-once:v1:'+action_id(a)))
def ready(a,period):
 if a.get('ready') is not True or a.get('period_to')!=period or not a.get('source') or not a.get('sku') or not a.get('criterion'):return False
 if not isinstance(a.get('baseline'),dict) or a['baseline'].get('id')!=a.get('campaign'):return False
 if a.get('kind') not in ('remove','raise_bid','lower_bid','add'):return False
 if any(type(a.get(k)) is not int or a[k]<=0 for k in ('campaign','nm')):return False
 if a['kind']!='remove':
  if a.get('placement') not in ('search','recommendations') or type(a.get('target_bid_minor')) is not int or a['target_bid_minor']<=0:return False
  if a['kind']!='add' and (type(a.get('stored_bid_minor')) is not int or a['stored_bid_minor']<=0):return False
  if a['kind']=='raise_bid' and not a['stored_bid_minor']<a['target_bid_minor']<=math.floor(a['stored_bid_minor']*1.05):return False
 if a['kind'] in ('raise_bid','add') and not a.get('positive_stock_verified'):return False
 c=a['baseline'];members={n['nm_id']:n for n in c.get('nm_settings',[])}
 if c.get('status')!=9 or c.get('currency')!='RUB' or c.get('bid_type')!='manual':return False
 if a['kind']=='remove' and (a['nm'] not in members or len(members)<=1 or not c.get('restrictions',{}).get('can_change_nms')):return False
 if a['kind'] in ('raise_bid','lower_bid') and (a['nm'] not in members or members[a['nm']].get('bids_kopecks',{}).get(a['placement'])!=a['stored_bid_minor']):return False
 if a['kind']=='lower_bid' and (type(a.get('minimum_bid_minor')) is not int or not a['minimum_bid_minor']<=a['target_bid_minor']<a['stored_bid_minor']):return False
 if a['kind']=='add' and (a['nm'] in members or len(members)>=50 or type(a.get('minimum_bid_minor')) is not int or a['target_bid_minor']<a['minimum_bid_minor']):return False
 if a['kind'] in ('raise_bid','add') and a.get('subject') in (51,57,255,756) and not a.get('positive_fbo_verified'):return False
 return True
def action_text(a):
 if a['kind']=='remove':return 'Исключить только этот SKU до отдельного возврата'
 val=lambda v:f'{v/100:.2f}'.replace('.',',')+' ₽'
 if a['kind']=='add':return 'Добавить только этот SKU · '+a['placement_label']+' '+val(a['target_bid_minor'])
 return a['placement_label']+' '+val(a['stored_bid_minor'])+' → '+val(a['target_bid_minor'])
def adapt_decisions(state,period,configs):
 """Accept typed execution specs only; never infer amounts or scope from prose."""
 out=[]
 for r in (state.get('records') or {}).values():
  if r.get('stage') not in ('proposed','detected'):continue
  p=r.get('latest_proposal') or r.get('proposal') or {};s=p.get('execution_spec');f=p.get('facts') or {}
  if p.get('delivery_ready') is False or p.get('draft_only') or f.get('period_to')!=period:continue
  if p.get('campaign_id')==40428689 and 'orange' in str(p.get('article','')).lower():continue
  if not isinstance(s,dict):
   # Adapt already-ready structured decisions; never parse execution parameters from prose.
   from analytics.ip_daily_recommendations import delivery_action_ready
   if not delivery_action_ready(r):continue
   c=configs.get(p.get('campaign_id'));nm=p.get('nm_id')
   if not c or not any(n['nm_id']==nm for n in c.get('nm_settings',[])):continue
   if p.get('kind') in ('pause','sku_exclusion'):
    s=dict(kind='remove',ready=True,baseline=c,placement_label='',positive_stock_verified=False)
   elif p.get('kind')=='bid_test' and (p.get('correction') or {}).get('kind')=='cpc_bid':
    correction=p['correction'];n=next(n for n in c['nm_settings'] if n['nm_id']==nm)
    old=n['bids_kopecks'].get('search');target=round(correction['target']*100)
    if old!=round(correction['current']*100) or target>=old or not correction.get('minimum'):continue
    s=dict(kind='lower_bid',ready=True,baseline=c,placement='search',placement_label='Ставка поиска',stored_bid_minor=old,target_bid_minor=target,minimum_bid_minor=round(correction['minimum']*100))
   else:continue
  a=dict(s,sku=p.get('article'),nm=p.get('nm_id'),campaign=p.get('campaign_id'),period_to=(p.get('facts') or {}).get('period_to'),source=(p.get('facts') or {}).get('source'),criterion=p.get('criterion'))
  if ready(a,period):out.append(a)
 return out
def build_contract(store,view):
 period=view['period'];cached=store.cache_get('advertising:ip:daily-ready:v1:'+period) or {}
 if cached and cached.get('period_to')!=period:raise ValueError('Ready evidence period mismatch')
 rows=store.db('GET','analytics_snapshots',params={'source':'eq.advertising_active_configuration','cabinet':'eq.token_2','select':'payload,collected_at','order':'id.desc','limit':1}) or []
 cfg=rows[0]['payload'] if rows else {};cfg=cfg[0] if isinstance(cfg,list) and cfg else cfg
 configs={c['id']:c for c in cfg.get('adverts',[])} if isinstance(cfg,dict) else {}
 display=[];authorized=set();protected_additions=set();pending_nms=set();donors=[];pair_changes={};sku_changes={}
 registry=store.cache_get('advertising:ip:execution-registry:v1') or {}
 protected_additions.update(registry.get('protected_addition_nms') or [])
 for record in registry.get('records',[]):
  p=store.cache_get(record['approval_key']) or {};e=store.cache_get(record['execution_key']) or {}
  for name,at in [('before','configuration_observed_at'),('membership_readback','membership_readback_at'),('after','readback_at'),('recovery_readback','recovery_readback_at')]:
   if isinstance(e.get(name),dict) and e.get(at):donors.append((e[at],e[name]))
  scope=p.get('actions') or p.get('scope') or p.get('entries') or []
  verified=str(e.get('status','')).startswith('verified')
  completed=e.get('readback_at') or e.get('recovery_readback_at') or e.get('finished_at')
  completed_day=None
  if completed:
   from zoneinfo import ZoneInfo
   completed_day=datetime.fromisoformat(completed.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
  for a in scope:
   if not a.get('kind') and 'target_bid_minor' in a:a=dict(a,kind='add')
   cid=a.get('campaign');nm=a.get('nm')
   item_verified=verified or any(i.get('campaign')==cid and i.get('nm')==nm and i.get('status')=='verified' for i in e.get('items',[]))
   if a.get('kind')=='remove':protected_additions.add(nm)
   if item_verified and completed_day and cid and nm:
    if a.get('kind') in ('raise_bid','lower_bid'):sku_changes[nm]=max(sku_changes.get(nm,''),completed_day)
    elif a.get('kind') in ('remove','add','add_to_existing'):pair_changes[(cid,nm)]=max(pair_changes.get((cid,nm),''),completed_day)
   if not record.get('show_recent'):continue
   relevant=not item_verified or not completed_day or view['period']<=completed_day
   if not relevant:continue
   if not cid or not nm or a.get('kind') not in ('remove','add','raise_bid','lower_bid'):continue
   authorized.add((cid,nm));pending_nms.add(nm)
   d=copy.deepcopy(a)
   d['display_status']='Выполнено '+str(completed_day)+'. Повторно не применять.' if item_verified else 'Не выполнено: исполнитель остановлен; повтор не запускать.' if e.get('finished_at') and e.get('error') else 'Результат не подтверждён; повтор не выполнять.' if e.get('status')=='attention' else 'Согласовано; в исполнении.' if e else 'Согласовано; ожидает исполнителя.'
   display.append(d)
 config_at=rows[0].get('collected_at','') if rows else ''
 observed_by_cid={cid:config_at for cid in configs}
 for at,adverts in sorted(donors,key=lambda x:x[0]):
  for cid,c in adverts.items():
   if isinstance(c,dict) and c.get('id') and 'nm_settings' in c:
    old_at=observed_by_cid.get(int(cid))
    if not old_at or datetime.fromisoformat(at.replace('Z','+00:00'))>=datetime.fromisoformat(old_at.replace('Z','+00:00')):
     configs[int(cid)]=copy.deepcopy(c);observed_by_cid[int(cid)]=at
 raw=list(cached.get('actions') or [])+adapt_decisions(store.cache_get('advertising:ip_pair_decisions:token_2:v1') or {},period,configs)
 from ip_daily_retained_review import review
 constraints=store.cache_get('advertising:ip:owner_constraints:v1') or {}
 preserve=set(constraints.get('preserve_skus') or [])
 reviewed,review_coverage=review(store,view,configs,authorized,protected_additions,pending_nms|preserve,pair_changes,sku_changes)
 raw+=reviewed
 actions=[];seen=set()
 for a in raw:
  a=copy.deepcopy(a)
  if not a.get('daily') and a.get('kind')!='add':
   a['daily']={}
   for v in (view.get('_recent_views') or [])+[view]:
    c=next((c for c in v['campaigns'] if c['campaign_id']==a.get('campaign')),None)
    row=next((r for r in (c or {}).get('sku_rows') or [] if r.get('nm_id')==a.get('nm')),None)
    if row and all(type(row.get(k)) in (int,float) and row[k]>=0 for k in ('ac_spending_sum','ac_orders','ac_orders_sum')):a['daily'][v['period']]=dict(spend=row['ac_spending_sum'],orders=row['ac_orders'],revenue=row['ac_orders_sum'])
  if a.get('kind')!='add' and period not in (a.get('daily') or {}):continue
  if not ready(a,period) or completed_or_claimed(store,a) or (a['campaign'],a['nm']) in authorized or a['nm'] in preserve:continue
  if (a['campaign'],a['nm']) in seen:continue # A previously frozen ready source has priority over a fresh adapter proposal.
  seen.add((a['campaign'],a['nm']));actions.append(copy.deepcopy(a))
 # The renderer and executor receive precisely the same frozen rows.
 details=copy.deepcopy(cached.get('details') or {})
 if not details.get('days'):
  compatible=sorted(set.intersection(*(set(a['daily']) for a in actions if a['kind']!='add'))) if any(a['kind']!='add' for a in actions) else [period]
  details['days']=compatible[-3:] or [period];details['period_label']='–'.join((details['days'][0],details['days'][-1])) if len(details['days'])>1 else period
 saved_notes=store.cache_get('advertising:ip:daily-notes:v1:'+period) or {}
 campaign_notes={cid:n['notes'] for cid,n in saved_notes.items() if isinstance(n,dict) and n.get('rows_sha256')==digest(next((c.get('sku_rows') for c in view['campaigns'] if str(c['campaign_id'])==cid),None))}
 result=dict(version='ip-daily-png-v1',chat_id=CHAT,bot_id=BOT,period=period,actions=actions,plan_sha256=digest(actions),campaign_notes=campaign_notes,
  details=details,excluded_incomplete=cached.get('excluded_incomplete') or [],display_only=display,
  campaign_labels={str(cid):dict(name=c['settings'].get('name'),payment=c['settings'].get('payment_type')) for cid,c in configs.items()},review_coverage=review_coverage,
  historical_profit_only=True,automatic_execution=False)
 store.cache_set('advertising:ip:daily-review-audit:v1:'+period,dict(period_to=period,coverage=review_coverage,new_actions=[{k:a.get(k) for k in ('sku','nm','campaign','kind','stored_bid_minor','target_bid_minor','source','criterion')} for a in actions],display_only_count=len(display),source_calls=0,wb_writes=0),ttl_days=365)
 return result
def render_recommendations(view,contract,outdir):
 from ip_campaign_table_png import render_ip
 return render_ip(view,contract,outdir)

def _render_superseded_sku_layout(view,contract,outdir):
 W=1300;P=26;BG='#edf4f7';INK='#203e50';MUTED='#71828c';RED='#bc354c'
 actions=contract['actions'];groups={}
 for a in actions:groups.setdefault(a['campaign'],[]).append(a)
 h=650+len(actions)*160+len(groups)*100
 im=Image.new('RGB',(W,max(850,h)),BG);d=ImageDraw.Draw(im)
 def txt(t,x,y,width,size=24,color=INK,bold=False):
  lines=wrap(t,font(size,bold),width)
  for i,l in enumerate(lines):d.text((x,y+i*(size+6)),l,font=font(size,bold),fill=color)
  return len(lines)*(size+6)
 d.rectangle((0,0,W,140),fill='#193c50');d.text((P,23),'ИП · ДРР и рекламные расходы',font=font(39,True),fill='white')
 label=contract['details'].get('period_label') or view['period']
 d.text((P,86),label+' · '+str(sum(c['metrics_complete'] is True for c in view['campaigns']))+'/'+str(len(view['campaigns']))+' РК за день',font=font(26),fill='#d2e0e7')
 y=163;y+=txt('Только готовые новые рекомендации. Усиление и ограничения — в одной таблице.',P,y,W-2*P)
 days=contract['details'].get('days') or [view['period']]
 if len(days)>3:raise ValueError('At most three completed days')
 cols=[425,558,691][:len(days)];periodx=691 if len(days)<3 else 817;actionx=880 if len(days)<3 else 957
 for x,t in [(P,'Артикул')]+[(x,day[8:10]+'.'+day[5:7]) for x,day in zip(cols,days)]+[(periodx,'ДРР периода'),(actionx,'Что делать сейчас')]:txt(t,x,y,(actionx-periodx-8) if x==periodx else 370,22,INK,True)
 y+=54;campaigns={c['campaign_id']:c for c in view['campaigns']}
 for cid,aa in groups.items():
  c=campaigns.get(cid,{})
  d.rounded_rectangle((14,y,W-14,y+110),radius=12,fill='#dfeaf0')
  name=aa[0].get('campaign_name','').removesuffix(' · CPC').removesuffix(' · CPM');payment=aa[0]['baseline']['settings']['payment_type']
  txt('РК '+str(cid)+' · '+name+' · '+('CPC — оплата за клики' if payment=='cpc' else 'CPM — оплата за показы'),P,y+10,W-2*P,24,INK,True)
  z=c.get('no_order_count');zs=c.get('no_order_spend');note='День: '+(rub(c['spend']) if c.get('spend') is not None else 'неизвестно')
  if z is not None and zs is not None:note+=' · без прямых заказов: '+str(z)+' SKU · '+rub(zs)
  txt(note,P,y+47,W-2*P,21,MUTED)
  txt('7 полных дней: '+(rub(c['weekly_spend']) if c.get('weekly_spend') is not None else 'неполное покрытие, сумма неизвестна'),P,y+78,W-2*P,20,MUTED);y+=120
  for a in aa:
   text=action_text(a);rh=max(118,30+len(wrap(text,font(24),W-actionx-P))*30)
   d.rounded_rectangle((14,y,W-14,y+rh-7),radius=12,fill='white');txt(a['sku'],P,y+15,380,25,INK,True)
   metrics=a.get('daily') or {};known=[metrics.get(day) for day in days];complete=all(isinstance(v,dict) for v in known)
   cost=sum(v['spend'] for v in known if v);orders=sum(v['orders'] for v in known if v);amount=sum(v['revenue'] for v in known if v)
   txt((rub(cost)+' · '+str(orders)+' прям. зак.') if complete else 'Новое размещение' if a['kind']=='add' else 'Показатели: см. период данных',P,y+69,380,20,RED if complete and cost>0 and orders==0 else MUTED)
   for x,day in zip(cols,days):
    v=metrics.get(day);ratio=100*v['spend']/v['revenue'] if v and v['revenue'] else None
    value=pct(ratio) if ratio is not None else '—' if v else 'н/п' if a['kind']=='add' else 'н/д'
    txt(value,x,y+25,125,25,RED if ratio is not None and ratio>5 else INK,True)
   ratio=100*cost/amount if complete and amount else None
   txt(pct(ratio) if ratio is not None else '—' if complete else 'н/п' if a['kind']=='add' else 'н/д',periodx,y+25,actionx-periodx-8,25,RED if ratio is not None and ratio>5 else INK,True)
   txt(text,actionx,y+14,W-actionx-P,24);y+=rh
 if not actions:y+=txt('Готовых новых команд нет. Это не означает отсутствия рисков или пробелов данных.',P,y,W-2*P,25)
 y+=15
 for line in ['ДРР периода = расход / сумма прямых заказов; не среднее дневных %. — нет прямых заказов; н/д — нет данных.',
  'Постклик по SKU не распределяется без подтверждения. Ставка и фактическая стоимость перехода различаются.',
  'Изменения не выполнены. Ответ «Сделай всё» на этот PNG подтвердит только перечисленные новые действия.',
  'Ранее согласованные действия исключены из команды. Бюджеты, цены, содержание карточек и расписания не меняются.',
  'Суммы SKU могут немного отличаться от итога РК из-за округления и версий источника.']:
  y+=txt(line,P,y,W-2*P,21,MUTED)+5
 path=Path(outdir)/'recommendations.png';path.parent.mkdir(parents=True,exist_ok=True);im.crop((0,0,W,y+25)).save(path,optimize=True)
 return dict(kind='drr',path=str(path))
def freeze_plan(store,contract,media_sha):
 key=PREFIX+contract['period'];p=dict(contract,media_sha256=media_sha,delivery_status='prepared',expires_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
 old=store.cache_get(key)
 if old:
  if old['plan_sha256']!=p['plan_sha256'] or old['media_sha256']!=media_sha:raise RuntimeError('Frozen daily plan changed; no replacement or resend')
  return key,old
 store.cache_set(key,p,ttl_days=365)
 if store.cache_get(key)!=p:raise RuntimeError('Plan readback mismatch')
 return key,p
def bind_receipt(store,key,p,receipt):
 if receipt.get('status')!='confirmed' or not receipt.get('photo_file_unique_id'):raise RuntimeError('Photo receipt not confirmed')
 if receipt.get('media_sha256')!=p['media_sha256']:raise RuntimeError('Delivered photo differs from frozen plan; no reply binding')
 value=dict(p,delivery_status='sent',message_id=receipt['message_id'],file_unique_id=receipt['photo_file_unique_id'])
 store.cache_set(key,value,ttl_days=365)
 if store.cache_get(key)!=value:raise RuntimeError('Reply plan receipt readback failed')
 binding='advertising:ip:png-message:v1:'+str(p['chat_id'])+':'+str(value['message_id'])
 store.cache_set(binding,dict(plan_key=key,plan_sha256=p['plan_sha256'],file_unique_id=value['file_unique_id']),ttl_days=365)
 if store.cache_get(binding).get('plan_key')!=key:raise RuntimeError('Message binding not saved')
 return value
