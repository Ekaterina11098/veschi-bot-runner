"""Read saved hourly evidence, ask cloud Codex once per slot, save privately. No WB/TG calls."""
import json
from datetime import datetime,timezone
from china_codex_cloud import DB,Worker
from china_codex_analysis import Core,active
ROOT='china_agent:hourly_codex_analysis:v1:'
def main():
 db=DB()
 if not active(db):print('Cloud hourly analysis not activated');return
 pointer=db.get('china_agent:hourly_sales_api:v1:latest')or{};key=pointer.get('source_key')
 if not isinstance(key,str)or not key.startswith('china_agent:hourly_sales_api:v1:snapshot:'):raise ValueError('Exact hourly source missing')
 source=db.get(key)
 if not source or source.get('status')!='complete'or source.get('cabinet')!='token_3'or source.get('slot_msk')!=pointer.get('slot_msk'):raise ValueError('Hourly source incomplete or wrong scope')
 at=datetime.fromisoformat(source['observed_at'].replace('Z','+00:00'))
 if not 0<=(datetime.now(timezone.utc)-at).total_seconds()<=4800:raise ValueError('Hourly source stale')
 result_key=ROOT+source['slot_msk']
 if (db.get(result_key)or{}).get('status')=='complete':print('Hourly cloud review already complete');return
 # Collect hourly as before; avoid paid re-analysis of the same completed-day basis.
 day=source['slot_msk'][:10];daily_key=ROOT+'daily:'+day
 comparisons=source.get('sales_comparisons')or{}
 material=any(v.get('count',{}).get('baseline',0)>=30 and any(v.get(k,{}).get('pct') is not None and v[k]['pct']<=-20 for k in ['count','amount_cny']) for v in comparisons.values())
 zero_budgets=sorted(r['advertId'] for r in (source.get('budgets')or{}).get('rows',[]) if r.get('total')==0)
 prior=db.get(ROOT+'latest')or{}
 new_zero=set(zero_budgets)-set(prior.get('zero_budget_campaigns',[]))
 worst=min([float(v[k]['pct']) for v in comparisons.values() for k in ['count','amount_cny'] if v.get('count',{}).get('baseline',0)>=30 and v.get(k,{}).get('pct') is not None]or[0])
 band=int(max(0,-worst)//10) if material else 0
 prior_band=prior.get('sales_signal_band',0)
 signal_changed=(band>=2 and (prior_band<2 or band>prior_band))or(band<2 and prior_band>=2)
 if db.get(daily_key) and not signal_changed and not new_zero:
  print('Hourly data saved; unchanged full-day basis, no paid model call');return
 ctx=Worker(db).context(dict(job_id=0,sender_id=5122667182,request_text='Почасовое наблюдение продаж и рекламы: диагностика, бюджет и новые возможности по завершённым дням. Никаких действий и отправок.'))
 ctx.pop('work_notes',None) # Core loads the authoritative bounded notes once.
 def validate(v):
  if v.get('kind')!='hourly_review'or type(v.get('material'))is not bool or not isinstance(v.get('summary'),str)or len(v['summary'])>6000:raise ValueError('Invalid hourly cloud review')
  if not isinstance(v.get('directions'),dict)or set(v['directions'])!={'raise','add','reduce','exclude'}:raise ValueError('Hourly four-direction coverage missing')
  return v
 result,receipt=Core(db).ask('hourly:'+source['slot_msk'],'hourly_observation',ctx,
  dict(kind='hourly_review',material=False,summary='Только новые существенные факты; обе базы продаж, окна/суммы/статусы совместимы. Нет сопоставимых данных явно. Не повторять уже сообщённое/verified/отозванное.',directions={k:'checked|unavailable с кратким обоснованием; готовое действие только при всех текущих проверках'for k in ['raise','add','reduce','exclude']},new_candidates=[]),validate)
 value=dict(status='complete',source_key=key,slot_msk=source['slot_msk'],observed_at=source['observed_at'],completed_at=datetime.now(timezone.utc).isoformat(),analysis=result,receipt=receipt,source_channel='codex_cloud',zero_budget_campaigns=zero_budgets,sales_signal_band=band,wb_writes=0,telegram_calls=0,grants_action_permission=False)
 if db.get(result_key):db.update(result_key,value)
 else:db.once(result_key,value)
 if not db.get(daily_key):db.once(daily_key,dict(status='complete',source_key=key,receipt=receipt))
 latest=ROOT+'latest'
 if db.get(latest):db.update(latest,value)
 else:db.once(latest,value)
 print('Hourly cloud analysis saved privately; no marketplace/Telegram actions')
if __name__=='__main__':main()
