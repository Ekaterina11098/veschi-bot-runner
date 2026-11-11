"""Owner-authorized corrected morning report preparation only. No TG or WB mutations."""
import copy,base64,json
from datetime import datetime,timezone
from china_advertising_state import AdvertisingIO as IO
from china_advertising_v2 import build
from china_advertising_v2_png import render
from china_advertising_directions import campaign_table
from china_growth_placements import addition_key
from china_advertising_full_growth import addition_actions
from china_morning_readiness import current_prices,published_stock
from china_moysklad_read import read_stock
from china_advertising_economic_review import model_rows
from china_budget_reserve import apply
K='china_agent:owner_morning_final:2026-11-11:v1:prepared'
def run():
 io=IO()
 if io.get(K):raise SystemExit('Prepared journal exists; inspect without replay')
 old=io.get('china_agent:owner_archive3_report:2026-11-11:v1');assert old['status']=='edited_verified'
 b=copy.deepcopy(old['bundle']);s=copy.deepcopy(io.get('china_agent:advertising_source:2026-11-11:v2'))
 v=copy.deepcopy(io.get('china_agent:owner_report_complete:2026-11-11:v1:growth-repair2')['inputs'])
 live=io.get('china_agent:owner_morning_quotes:2026-11-11:v1:read');q=io.get('china_agent:owner_morning_quotes:2026-11-11:v2:read')
 assert live['status']=='read'and live['states']['http']==live['budgets']['http']==200 and q['status']=='read'
 states={c['id']:c for c in live['states']['data']['adverts']};cash={r['advertId']:r for r in live['budgets']['data']['adverts']}
 for c in b['campaigns']:
  if c['id']in states:
   assert c['status']==states[c['id']]['status']
   c['balance']=cash[c['id']]['total']
  for row in c.get('attention',[]):
   a=row.get('action')or{}
   if a.get('kind')in['ad_set_bid','ad_exclude_sku']:
    n=next(n for n in states[c['id']]['nm_settings']if n['nm_id']==a['nm_id'])
    assert n['bids_kopecks'][a['placement']]==a['old_minor']
  if any((r.get('action')or{}).get('kind')=='archive_campaign'for r in c.get('attention',[])):
   c['planned_archive']=True;c['owner_budget_refused']=True
 # Explicit latest owner exception: new campaign has no returned WB statistics, NOT zero.
 b['approved_statistics_exceptions']={'41756218':dict(owner_id=5122667182,owner_accepted_separate_row=True,reason='new_campaign_no_wb_statistics',source='owner accepted send now with417 separately; WB UI8-10Nov also no data')}
 c=next(c for c in b['campaigns']if c['id']==41756218)
 c.update(period=None,last=None,missing_stats=True)
 c['direction_recommendations']=['Новая РК от10.11. Первый полный день11.11; оценка12.11. Без изменений.']
 ids=[1535337771,1535337772,1535337773,1535337779,1556488181]
 prices=current_prices(io,ids);stock=read_stock([p['article']for p in prices['rows']]);pub=published_stock(io,prices,ids)
 econ=model_rows(dict(products=v['own'],prices=prices,stock=stock,fx=dict(rub_per_cny=v['fx']['rub_per_cny'])),io.get('china_agent:new_ad_economics_policy:v1'),io.get('china_agent:expected_profit_delivery_model:v1'))
 assert not econ['missing']
 now=datetime.now(timezone.utc).isoformat()
 for nm,e in econ['rows'].items():
  e.update(published_stock=pub['amounts'].get(nm),published_stock_observed_at=pub['observed_at'],fx_rub_per_cny=v['fx']['rub_per_cny'],fx_date='2026-11-11')
  assert e['expected_margin_before_ads_cny']>0 and e['stock_free']>0 and e['published_stock']>=3 and not e['buyout_fallback']and not e['commission_policy_fallback']and e['sample_size']>=5
 v['economics']['rows'].update(econ['rows'])
 freshprices={p['nm_id']:p for p in prices['rows']}
 v['prices']['rows']=[freshprices.get(p['nm_id'],p)for p in v['prices']['rows']]
 v['campaigns']=[states.get(c['id'],c)for c in v['campaigns']]
 v['budgets']=live['budgets']['data'];v['observed_at']=now
 # Keep completed-day selection; no today DRR is used.
 v['addition_candidates']=[r for r in v['addition_candidates']if r['nm_id']in ids]
 s['full_growth_inputs']=v;s['addition_bid_quotes']={}
 for r in v['addition_candidates']:
  label='panamas_search'if r['placement']=='search'else'umbrella_recommendations';cp=40945478 if label=='panamas_search'else41325637
  response=q[label];assert response['http']==200
  typ='search'if r['placement']=='search'else'recommendation'
  values=[bid['value']for row in response['data']['bids']if row['nm_id']==r['nm_id']for bid in row['bids']if bid['type']==typ and bid['currency']=='CNY']
  assert len(values)==1
  s['addition_bid_quotes'][addition_key(r)]=dict(campaign_id=r['campaign_id'],placement=r['placement'],target_minor=values[0],bid_verified=True,quote_campaign_id=cp,observed_at=q['observed_at'])
 adds=addition_actions(s,[])
 assert len(adds)==5
 for a in adds:
  c=next(c for c in b['campaigns']if c['id']==a['campaign_id'])
  row=dict(nm=a['nm_id'],article=a['article'],action=a,decision='Тест: добавить; ставка '+str(a['target_minor']/100)+' CNY.',period=None,daily=[],economics=a['growth_evidence'])
  c.setdefault('attention',[]).append(copy.deepcopy(row));c.setdefault('focus',[]).append(row)
  b['recommendation_directions']['add']['rows'].append(dict(article=a['article'],campaign_id=a['campaign_id'],decision=row['decision'],action=a,ready=True,nm_id=a['nm_id'],target_minor=a['target_minor'],bid_verified=True,economics=a['growth_evidence']))
 b['recommendation_directions']['add'].update(count=5,note='5 готовых ограниченных тестов; предварительная экономика, CPA неизвестна.')
 b['budget_observed_at']=now;b['budget_balance_observed_at_iso']=live['observed_at'];b['budget_balance_observed_at']=datetime.fromisoformat(live['observed_at']).astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).strftime('%H:%M МСК')
 b=apply(b,b.get('budget_minimum_topup_cny',100))
 b['owner_correction_note']='Рекомендации ещё не исполнены. Бюджеты учитывают предложенное завершение3РК; история расходов сохранена.'
 # Manual row visibility is checked before any publication.
 table=campaign_table(b)
 c55=next(c for c in table['campaigns']if c['id']==41680341)
 assert any('55-NoelBag-green' in x and 'Исключить'in x for x in c55['direction_recommendations'])
 for cid in[41155824,41270471,41570073]:
  c=next(c for c in table['campaigns']if c['id']==cid)
  assert any('архив'in x for x in c['direction_recommendations'])
 assert sum(len(c['direction_recommendations'])for c in table['campaigns'])>=15
 files=render(b);assert sum(len(f['actions'])for f in files if f['family']=='drr')==15
 prepared=dict(status='prepared_not_sent',bundle=b,files=[dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],actions=f['actions'],b64=base64.b64encode(f['bytes']).decode())for f in files],fresh_addition_inputs=dict(prices=prices,stock=stock,published_stock=pub,economics=econ),source_key='china_agent:advertising_source:2026-11-11:v2',prepared_at=now,wb_writes=0,telegram_calls=0,model_calls=0)
 assert io.create(K,prepared);assert io.get(K)==prepared
 print('Prepared privately:15 ad actions; verified visible55/archive3/add5; no publication')
if __name__=='__main__':run()
