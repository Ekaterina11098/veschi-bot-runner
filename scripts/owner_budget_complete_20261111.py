"""Read-only completion of the two exact missing budget facts; no marketplace mutation or TG."""
import copy,json,requests
from datetime import datetime,timezone
from china_advertising_state import AdvertisingIO as IO
from china_held_evidence import merge_held
from china_morning_readiness import current_prices,published_stock
from china_moysklad_read import read_stock
from china_advertising_economic_review import model_rows
from china_budget_ready_model import attach
from china_advertising_v2 import history
def run():
 io=IO();K='china_agent:owner_budget_complete:2026-11-11:v1:read'
 if io.get(K):raise SystemExit('Existing exact budget read')
 s=copy.deepcopy(io.get('china_agent:advertising_source:2026-11-11:v2'));v=merge_held(s['full_growth_inputs'])
 prices=current_prices(io,[1473245494,1473244000]);stock=read_stock([p['article']for p in prices['rows']]);pub=published_stock(io,prices,[1473245494,1473244000])
 econ=model_rows(dict(products=v['own'],prices=prices,stock=stock,fx=dict(rub_per_cny=v['fx']['rub_per_cny'])),io.get('china_agent:new_ad_economics_policy:v1'),io.get('china_agent:expected_profit_delivery_model:v1'))
 assert not econ['missing']
 for nm,e in econ['rows'].items():e.update(published_stock=pub['amounts'][nm],published_stock_observed_at=pub['observed_at'],fx_rub_per_cny=v['fx']['rub_per_cny'],fx_date='2026-11-11')
 v['economics']['rows'].update(econ['rows']);v['published_stock']['amounts'].update(pub['amounts'])
 for family,new,key in [('prices',prices,'nm_id'),('stock',stock,'article')]:
  rows={str(r[key]).casefold():r for r in v[family]['rows']};rows.update({str(r[key]).casefold():r for r in new['rows']});v[family]['rows']=list(rows.values())
 s['economics']=v['economics'];s['full_growth_inputs']=v;s['observed_at']=datetime.now(timezone.utc).isoformat()
 ids=[c['id']for c in v['campaigns']if c['status']==9]
 r=requests.post('https://advert-api.wildberries.ru/api/advert/v2/budget',headers={'Authorization':io.token},json={'advertIds':ids},timeout=40);r.raise_for_status();balances=r.json();cash={c['advertId']:c for c in balances['adverts']}
 b=copy.deepcopy(io.get('china_agent:owner_morning_final:2026-11-11:v1:prepared')['bundle'])
 for c in b['campaigns']:
  if c['id']in cash:c['balance']=cash[c['id']]['total']
 b['budget_observed_at']=s['observed_at'];b['budget_balance_observed_at_iso']=s['observed_at']
 b=attach(b,s,history(s['executions']))
 out=dict(status='read',source=s,bundle=b,prices=prices,stock=stock,published_stock=pub,economics=econ,balances=balances,observed_at=s['observed_at'],wb_writes=0,telegram_calls=0)
 assert io.create(K,out);assert io.get(K)==out
 print('Exact budget evidence completed privately; no writes/sends')
if __name__=='__main__':run()
