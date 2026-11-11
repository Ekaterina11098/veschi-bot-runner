"""Prepare final concrete budgets and one shared exact approval plan. No TG or WB mutation."""
import copy,base64,math
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from china_advertising_state import AdvertisingIO as IO
from china_budget_ready_model import attach
from china_budget_reserve import apply
from china_advertising_v2 import history
from china_advertising_v2_png import render
from china_owner_budget_final import apply_review
from china_held_evidence import merge_held
def run():
 io=IO();K='china_agent:owner_budget_final:2026-11-11:v2:prepared'
 if io.get(K):raise SystemExit('Already prepared')
 read=io.get('china_agent:owner_budget_complete:2026-11-11:v1:read');assert read['status']=='read'
 b=copy.deepcopy(read['bundle']);s=copy.deepcopy(io.get('china_agent:advertising_source:2026-11-11:v2'));v=merge_held(s['full_growth_inputs'])
 v['economics']['rows'].update(read['economics']['rows']);v['published_stock']['amounts'].update(read['published_stock']['amounts'])
 for family,key in [('prices','nm_id'),('stock','article')]:
  rows={str(r[key]).casefold():r for r in v[family]['rows']};rows.update({str(r[key]).casefold():r for r in read[family]['rows']});v[family]['rows']=list(rows.values())
 s['economics']=v['economics'];s['observed_at']=read['observed_at'];s['full_growth_inputs']=v
 s['owner_launch_day_funding_refs']={'41296363':['2026-11-10']}
 b=attach(b,s,history(s['executions']))
 b=apply(b,b.get('budget_minimum_topup_cny',100))
 decisions={}
 for cid in[41332083,41680341,41680449]:
  c=next(c for c in b['campaigns']if c['id']==cid);ref=c['budget_period']['spend'];assert c['balance']>=ref
  decisions[str(cid)]=dict(decision='no_fund',reference_cny=ref,reference_label='Расход 8–10 ноября (справка): ',text='Не пополнять: остаток '+str(c['balance'])+' CNY выше расходов 8–10 ноября '+format(ref,'.2f').replace('.',',')+' CNY.')
 decisions['41756218']=dict(decision='no_fund',text='Не пополнять: новая РК от 10.11, остаток 300 CNY. Первый полный день — 11.11; оценка 12.11.')
 decisions['40892162']=dict(decision='no_fund',hide=True,text='Не пополнять: РК не запускалась.')
 c=next(c for c in b['campaigns']if c['id']==41296363);e=copy.deepcopy(c['campaign_budget_economics'])
 if e['status']=='positive'and e.get('ready')and e['stress_after_ads_cny']>0:
  state=next(cp for batch in s['batches'].values()for cp in batch['campaigns']['adverts']if cp['id']==41296363)
  launched=datetime.fromisoformat(state['timestamps']['started']).astimezone(ZoneInfo('Europe/Moscow'));end=launched.replace(hour=0,minute=0,second=0,microsecond=0)+__import__('datetime').timedelta(days=1)
  hours=(end-launched).total_seconds()/3600;assert 0<hours<24
  forecast=e['metrics']['spend']/hours*72
  amount=max(100,math.ceil(max(0,forecast-c['balance'])/50)*50)
  if forecast>c['balance']:
   e.update(reference_hours=hours,reference_spend_cny=e['metrics']['spend'],forecast_three_day_cny=forecast,forecast_not_spend_cap=True)
   action=dict(id='topup:41296363',kind='topup_campaign',campaign_id=41296363,amount_cny=amount,balance_before=c['balance'],target_balance=c['balance']+amount,status_before=9,nm_ids=sorted(map(int,e['expected_bids'])),basis='owner_reviewed_limited_launch_day_continuation',completed_days=['2026-11-10'],budget_evidence=e)
   decisions['41296363']=dict(decision='limited_test_topup',reference_cny=round(forecast,2),action=action,evidence=e,text='Тест: пополнить на '+str(amount)+'CNY. По фактическому темпу10.11, не по3полным дням; оценка12.11.')
 else:decisions['41296363']=dict(decision='no_fund',reference_cny=c['budget_period']['spend'],reference_label='Расход8–10ноября (справка): ',text='Не пополнять: предварительная стресс-модель не подтверждает дополнительный расход нового теста.')
 b['owner_final_budget_review']=dict(owner_id=5122667182,source='Owner asked fully actionable budgets and one reply Сделай всё',campaigns=decisions)
 b=apply_review(b)
 # The shared batch applies advertised SKU changes first; funding binds that exact resulting composition.
 ad_actions=[r['action']for c in b['campaigns']for r in c.get('attention',[])if r.get('action')]
 for c in b['campaigns']:
  a=c.get('budget_action')
  if not a:continue
  evidence=a['budget_evidence'];expected=evidence['expected_bids']
  for change in ad_actions:
   if change['campaign_id']!=c['id']:continue
   if change['kind']=='ad_exclude_sku':expected.pop(str(change['nm_id']),None);evidence['member_inputs'].pop(str(change['nm_id']),None)
   if change['kind']=='ad_set_bid':expected[str(change['nm_id'])][change['placement']]=change['target_minor']
  a['nm_ids']=sorted(map(int,expected));a['depends_on_ad_actions']=[x['id']for x in ad_actions if x['campaign_id']==c['id']]
  c['campaign_budget_economics']=evidence
 b['budget_balance_observed_at']=datetime.fromisoformat(read['observed_at']).astimezone(ZoneInfo('Europe/Moscow')).strftime('%H:%M МСК')
 b['owner_unified_approval']=True
 files=render(b)
 budgets=[f for f in files if f['family']=='budgets'];assert len(budgets)==1
 acts=budgets[0]['actions'];assert len(acts)>=6
 # Renderer reapplies reserve checks: carry exact reviewed post-change evidence back onto bound actions.
 correct={c['id']:c['budget_action']for c in b['campaigns']if c.get('budget_action')}
 for i,a in enumerate(acts):acts[i]=copy.deepcopy(correct[a['campaign_id']])
 b['budget_balance_observed_at']=datetime.fromisoformat(read['observed_at']).astimezone(ZoneInfo('Europe/Moscow')).strftime('%H:%M МСК')
 out=dict(status='prepared_not_sent',bundle=b,files=[dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],actions=f['actions'],b64=base64.b64encode(f['bytes']).decode())for f in files],shared_actions=ad_actions+acts,budget_actions=acts,total_funding_cny=sum(a['amount_cny']for a in acts),prepared_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_calls=0)
 assert io.create(K,out);assert io.get(K)==out
 print('Final reviewed budgets and unified approval prepared; no WB/TG mutations')
if __name__=='__main__':run()
