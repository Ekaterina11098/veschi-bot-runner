"""Finish explicitly requested economics and all-direction analysis; no WB mutations/sends."""
import copy,json,os
from datetime import datetime,timezone
ROOT='china_agent:owner_moscow_fur:2026-11-11:v1'
def overlay(value,calculation,observed):
 v=copy.deepcopy(value);economics=v.setdefault('economics',dict(rows={},missing={}))
 # Actual ad spend is assessed separately; reserve3% must also be present before ads.
 for e in economics.get('rows',{}).values():
  if all(type(e.get(k))in(int,float)for k in ('buyout','seller_price_cny','expected_margin_before_ads_cny'))and not e.get('payment_reserve_pct'):
   e['expected_margin_before_ads_cny']-=e['buyout']*e['seller_price_cny']*.03
   e['payment_reserve_pct']=3
 for r in calculation:
  nm=str(r['nm_id']);pr=next((p for p in v['prices']['rows']if p['nm_id']==r['nm_id']),None)
  if not pr or pr['seller_price']!=r['price_cny']:continue
  e=dict(observed_at=observed,price_observed_at=r['source_price_stock_observed_at'],stock_observed_at=r['source_price_stock_observed_at'],seller_price_cny=r['price_cny'],own_cogs_rub=r['cogs_rub'],stock_free=r['MSK_available'],buyout=r['buyout_scenario'],sample_size=0,sample_reliable=False,buyout_fallback=True,commission_pct=20,commission_policy_fallback=False,tax_pct=5,payment_reserve_pct=3,handling_rub=0,logistics_cny=r['logistics_cny_per_dispatch'],logistics_historical=False,logistics_source=ROOT+':calculation',expected_margin_before_ads_cny=r['expected_margin_before_ads_cny'],preliminary=True,unknown_reverse_and_shared_costs=True,owner_strategy_review=True,fx_rub_per_cny=r['fx_rub_per_cny'],fx_date=r['fx_date'],published_stock=r.get('published_stock'),published_stock_observed_at=observed,period_from='2026-10-12',period_to='2026-11-10',source_ids=[ROOT+':inputs',ROOT+':calculation'],scenario_note='Owner5Nov fixed planning buyout30% fur/40% bags, not own observed rate. Manual preliminary economics only; automatic sample gates preserved.')
  economics['rows'][nm]=e;economics.setdefault('missing',{}).pop(nm,None)
 return v
def main():
 import requests
 from conversion_watches import runtime
 from china_menu_analytics import candidate,CANDIDATES
 import china_loss_execute
 w=runtime();inputs=w.get(ROOT+':inputs');calc=w.get('china_agent:owner_moscow_fur:2026-11-11:v2:calculation');at=datetime.now(timezone.utc).isoformat()
 if not inputs or calc.get('status')!='calculated':raise ValueError('Exact tariff/card calculation absent')
 if (datetime.now(timezone.utc)-datetime.fromisoformat(inputs['observed_at'])).total_seconds()>7200:raise ValueError('Exact card inputs stale')
 cards=inputs['cards'];headers={'Authorization':os.environ['WB_TOKEN_3']};chrt=[s['chrtID']for c in cards for s in c['sizes']]
 stocks={};raw={}
 previous=w.get(ROOT+':warehouse_stock:2026-11-11T18:59:02.028590+00:00')or{}
 for warehouse in (2126188,2308581):
  old=previous.get(str(warehouse))or{}
  if old.get('status')==200 and (datetime.now(timezone.utc)-datetime.fromisoformat(old['observed_at'])).total_seconds()<1800:
   raw[str(warehouse)]=old;stocks[warehouse]=old['data']['stocks'];continue
  response=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/'+str(warehouse),headers=headers,json={'chrtIds':chrt},timeout=75,allow_redirects=False)
  raw[str(warehouse)]=dict(status=response.status_code,observed_at=at)
  if response.status_code!=200:raise ValueError('Exact warehouse stock HTTP '+str(response.status_code))
  raw[str(warehouse)]['data']=response.json();stocks[warehouse]=response.json()['stocks']
 w.save(ROOT+':warehouse_stock:'+at,raw)
 models=[]
 for row in calc['rows']+calc.get('conditional_other_route',[]):
  r=copy.deepcopy(row);card=next(c for c in cards if c['nmID']==r['nm_id']);sizes={s['chrtID']for s in card['sizes']}
  def amount(warehouse):
   found=[s for s in stocks[warehouse]if s.get('chrtId',s.get('chrtID'))in sizes]
   if len(found)!=len(sizes):return None
   return sum(s['amount']for s in found)
  r['warehouse_MSK_published']=amount(2126188);r['warehouse_Guangzhou_published']=amount(2308581)
  if r['warehouse_MSK_published']is None:raise ValueError('Exact MSK stock coverage incomplete')
  r['other_warehouse_missing_is_not_zero']=r['warehouse_Guangzhou_published']is None
  if (r['warehouse_Guangzhou_published']or 0)>0 and r['subject_id']!=4377:continue
  r['published_stock']=r['warehouse_MSK_published'];r['route']='Moscow_FBS';models.append(r)
 calc.update(rows=[r for r in models if r['subject_id']==4377],resolved_models=models,warehouse_observed_at=at)
 w.save(ROOT+':calculation_resolved',calc)
 original=china_loss_execute.IO
 class ReviewedIO(original):
  def get(self,key):
   value=super().get(key)
   if key=='china_agent:advertising_full_growth:2026-11-11:v1:inputs'and value:
    return overlay(value,models,at)
   return value
 china_loss_execute.IO=ReviewedIO
 job=dict(id='owner-moscow-economics-20261111',chat_id=-1004342917488,sender_id=5122667182,request_text='Завершить подбор после расчета шуб из Москвы')
 try:
  answer=candidate(w,job,CANDIDATES+'Все четыре направления: добавление, повышение, снижение, исключение.')
  review=w.get('china_agent:menu_analytics:v1:'+str(job['id']))or{}
  plan=w.get('china_agent:codex_ad_review:v1:'+str(job['id']))or{}
  w.save(ROOT+':selection',dict(status='reviewed',answer=answer,job_id=job['id'],menu_review=review,prepared_plan=plan,observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_sends=0,automatic_gate_changes=False))
  print(json.dumps(dict(status='reviewed',answer=answer,stock_coverage=len(models),wb_writes=0,telegram_sends=0),ensure_ascii=False))
 except Exception as exc:
  w.save(ROOT+':selection',dict(status='blocked',error_type=type(exc).__name__,error=str(exc)[:350],observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_sends=0))
  raise
 finally:china_loss_execute.IO=original
if __name__=='__main__':main()

