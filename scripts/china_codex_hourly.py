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
 ctx=Worker(db).context(dict(job_id=0,sender_id=5122667182,request_text='Почасовое наблюдение продаж и рекламы: диагностика, бюджет и новые возможности по завершённым дням. Никаких действий и отправок.'))
 def validate(v):
  if v.get('kind')!='hourly_review'or type(v.get('material'))is not bool or not isinstance(v.get('summary'),str)or len(v['summary'])>6000:raise ValueError('Invalid hourly cloud review')
  if not isinstance(v.get('directions'),dict)or set(v['directions'])!={'raise','add','reduce','exclude'}:raise ValueError('Hourly four-direction coverage missing')
  return v
 result,receipt=Core(db).ask('hourly:'+source['slot_msk'],'hourly_observation',ctx,
  dict(kind='hourly_review',material=False,summary='Только новые существенные факты; обе базы продаж, окна/суммы/статусы совместимы. Нет сопоставимых данных явно. Не повторять уже сообщённое/verified/отозванное.',directions={k:'checked|unavailable с кратким обоснованием; готовое действие только при всех текущих проверках'for k in ['raise','add','reduce','exclude']},new_candidates=[]),validate)
 value=dict(status='complete',source_key=key,slot_msk=source['slot_msk'],observed_at=source['observed_at'],completed_at=datetime.now(timezone.utc).isoformat(),analysis=result,receipt=receipt,source_channel='codex_cloud',wb_writes=0,telegram_calls=0,grants_action_permission=False)
 if db.get(result_key):db.update(result_key,value)
 else:db.once(result_key,value)
 latest=ROOT+'latest'
 if db.get(latest):db.update(latest,value)
 else:db.once(latest,value)
 print('Hourly cloud analysis saved privately; no marketplace/Telegram actions')
if __name__=='__main__':main()
