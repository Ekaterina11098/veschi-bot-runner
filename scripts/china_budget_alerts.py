"""Read-only budget alerts at report slots. No WB write path."""
import os,math,json
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,counts,drr,stamp
ROOT='china_agent:budget_watch:v1:'
def assess(balance,today,period,hour,horizon):
 rate=today['spend']/max(hour,1)
 needed=rate*horizon
 return dict(risk=rate>0 and balance<needed,rate_per_hour=rate,until_next=needed,proposed=max(0,math.ceil((needed-balance)/50)*50),drr_today=drr(today),drr_3days=drr(period))
def continuation_ok(today,previous):
 a=drr(today);b=drr(previous) if previous else None
 return a is not None and (a<=5 or a<=5.5 and b is not None and a<=b*.8 and today['orders']>=3)
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise RuntimeError('Public main only')
 c=Cache();w=WB();validate_identity(c,w)
 t=datetime.now(ZoneInfo('Europe/Moscow'));day=t.date().isoformat();slot=day+(':morning' if t.hour<12 else ':afternoon') if os.environ.get('GITHUB_EVENT_NAME')=='schedule' else day+':manual:'+os.environ.get('GITHUB_RUN_ID',stamp())
 key=ROOT+'run:'+slot
 if not c.create(key,dict(status='running',created_at=stamp())):return
 inv=w.req('/adv/v1/promotion/count');ids=sorted({x['advertId'] for g in inv.get('adverts',[]) if g['status']==9 for x in g.get('advert_list',[])})
 cs=w.campaigns(ids);bud=w.req('/api/advert/v2/budget','POST',dict(advertIds=ids))['adverts']
 stats=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate='+(t.date()-timedelta(days=3)).isoformat()+'&endDate='+day)
 def subset(begin,end):
  out=[]
  for x in stats:
   ds=[d for d in x.get('days',[]) if begin<=d['date'][:10]<=end]
   if not ds:continue
   z=dict(advertId=x['advertId'],days=ds)
   for f in ['sum','sum_price','orders','views','clicks','atbs']:z[f]=sum(d.get(f,0) for d in ds)
   out.append(z)
  return counts(out)
 today,sku=subset(day,day);period,_=subset((t.date()-timedelta(days=3)).isoformat(),(t.date()-timedelta(days=1)).isoformat())
 balances={str(x['advertId']):x['total'] for x in bud};hour=t.hour+t.minute/60
 nextcheck=t.replace(hour=15,minute=0,second=0,microsecond=0) if hour<15 else (t+timedelta(days=1)).replace(hour=7,minute=30,second=0,microsecond=0)
 horizon=max(.5,(nextcheck-t).total_seconds()/3600);rows=[]
 for cid,camp in cs.items():
  if cid not in today or cid not in balances:rows.append(dict(campaign_id=cid,status='missing_stats'));continue
  a=assess(balances[cid],today[cid],period.get(cid,dict(spend=0,amount=0)),hour,horizon)
  active={str(n['nm_id']) for n in camp['nm_settings']}
  members=[dict(nm_id=int(n),**sku.get(cid+':'+n,dict(spend=0,amount=0,orders=0,clicks=0))) for n in active]
  row=dict(campaign_id=cid,balance=balances[cid],today=today[cid],previous_3days=period.get(cid),members=members,**a);rows.append(row)
  if not a['risk']:continue
  # One notice per day/campaign; uncertain delivery is never retried blindly.
  nk=ROOT+'notice:'+day+':'+cid
  if c.get(nk):continue
  dr='не определена' if a['drr_today'] is None else f"{a['drr_today']:.2f}%"
  ec=(c.get('china_agent:hourly_economics:v1') or {}).get(cid,{})
  viable=ec.get('all_costs_confirmed') is True and ec.get('expected_total_profit_cny',-1)>0 and continuation_ok(today[cid],period.get(cid))
  decision=f"Предлагаемая сумма: {a['proposed']:.0f} CNY до следующего среза." if viable else "Пополнение пока не рекомендовано: "+("ДРР выше цели либо заказов нет." if not continuation_ok(today[cid],period.get(cid)) else "полная экономика оставшихся товаров не подтверждена.")
  text=f"Бюджет РК {cid}\nОстаток: {balances[cid]:.2f} CNY\nРасход сегодня: {today[cid]['spend']:.2f} CNY\nДРР сегодня: {dr}\nПри текущем темпе остатка может не хватить до {nextcheck.strftime('%d.%m %H:%M')} МСК.\n{decision}\nСрез {t.strftime('%d.%m %H:%M')} МСК. Прогноз предварительный; автопополнения нет."
  if not c.create(nk,dict(status='preparing',text=text)):continue
  bot=os.environ['CHINA_TELEGRAM_BOT_TOKEN'];me=requests.get('https://api.telegram.org/bot'+bot+'/getMe',timeout=20).json()
  if not me.get('ok') or me['result']['id']!=8780468043:raise RuntimeError('Bot identity mismatch')
  c.put(nk,dict(status='sending',text=text))
  try:
   z=requests.post('https://api.telegram.org/bot'+bot+'/sendMessage',json=dict(chat_id=-1004342917488,text=text),timeout=35).json()
   if not z.get('ok') or z['result']['chat']['id']!=-1004342917488:raise RuntimeError('Delivery unconfirmed')
   c.put(nk,dict(status='sent',text=text,message_id=z['result']['message_id'],sent_at=stamp()))
  except Exception:c.put(nk,dict(status='uncertain',text=text));raise RuntimeError('Telegram result uncertain; no retry')
 c.put(ROOT+'latest',dict(observed_at=stamp(),rows=rows,wb_writes=0,next_check=nextcheck.isoformat()))
 c.put(key,dict(status='complete',observed_at=stamp(),campaign_count=len(rows),wb_writes=0))
 print('Private budget snapshot saved; no marketplace writes')
if __name__=='__main__':run()
