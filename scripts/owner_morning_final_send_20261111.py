"""Publish only visually checked owner-requested replacement; no WB mutations."""
import base64,copy
from china_advertising_state import AdvertisingIO as IO
from china_advertising_delivery import deliver,telegram_sender
from china_daily_ad_actions import plan,bind
def run():
 io=IO();root='china_agent:owner_morning_final:2026-11-11:v1'
 saved=io.get(root+':prepared');qa=io.get(root+':visual_qa')
 assert saved['status']=='prepared_not_sent'and qa['status']=='approved_for_owner_requested_publication'
 assert sum(len(f['actions'])for f in saved['files']if f['family']=='drr')==15
 assert sum(len(f['actions'])for f in saved['files']if f['family']=='budgets')==4
 files=[]
 for index,f in enumerate(saved['files']):
  f=copy.deepcopy(f);p=plan(io,'2026-11-11',f,index,slot='owner-final')
  caption=('Китай · утренний отчёт11ноября · данные8–10ноября. 15новых действий:5добавлений,1повышение,2снижения,4исключения (включая55),3завершения РК.41756218 — новая РК, отдельно; в числовой итог не включена. Ответьте «Сделай всё» на этот PNG для15действий. Ничего ещё не исполнено.' if f['family']=='drr'else'Китай · бюджеты11ноября.4готовых пополнения:100+300+100+250=750CNY; остатки перепроверены. Три РК, предложенные к завершению, не пополняем. Ответьте «Сделай всё» на этот PNG только для4пополнений. Это не суточные лимиты.')
  f.update(bytes=base64.b64decode(f.pop('b64'),validate=True),caption=caption,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'])
  files.append(f)
 result=deliver(io,'2026-11-11',files,telegram_sender(io),binder=lambda f,r:bind(io,f,r),delivery_key=root+':delivery')
 assert result['status']=='delivered'and all(p['status']=='sent'and p['message_id']for p in result['parts'])
 assert io.get(root+':delivery')==result
 print('Owner corrected morning report delivered and read back; WB writes0')
if __name__=='__main__':run()
