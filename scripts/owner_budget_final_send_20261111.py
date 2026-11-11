"""Edit existing owner-requested PNGs into one hash-bound shared plan; no WB mutation."""
import copy,base64,json,requests
from datetime import datetime,timezone
from china_advertising_state import AdvertisingIO as IO
from china_daily_ad_actions import plan,bind,BIND
from china_loss_control import PLAN
def run():
 io=IO();root='china_agent:owner_budget_final:2026-11-11:v2';K=root+':delivery'
 if io.get(K):raise SystemExit('Existing edit journal; do not blindly repeat')
 v=io.get(root+':prepared');qa=io.get(root+':visual_qa')
 assert v['status']=='prepared_not_sent'and qa['status']=='approved_for_owner_requested_edit'
 assert len(v['shared_actions'])==21 and len(v['budget_actions'])==6 and v['total_funding_cny']==4300
 old={str(mid):io.get(BIND+str(mid))for mid in[857,858]}
 assert old['857']['plan_id']=='daily-2026-11-11-owner-final-drr-0'
 assert old['858']['plan_id']=='daily-2026-11-11-owner-final-budgets-1'
 for b in old.values():assert io.get('china_agent:daily_ad_execution:v2:'+b['plan_id'])is None
 f=dict(family='drr',actions=copy.deepcopy(v['shared_actions']))
 p=plan(io,'2026-11-11',f,0,slot='owner-unified-final')
 p.update(unified_report=True,related_families=['drr','budgets'],budget_total_cny=4300,advertising_action_count=15,budget_action_count=6)
 e=dict(status='prepared',new_plan_id=p['plan_id'],new_plan_sha256=p['plan_sha256'],old_bindings=old,wb_writes=0,prepared_at=datetime.now(timezone.utc).isoformat())
 assert io.create(K,e)
 for mid,b in old.items():
  previous=io.get(PLAN+b['plan_id']);assert io.create(K+':old_plan:'+mid,previous)
  previous.update(invalidated_at=datetime.now(timezone.utc).isoformat(),invalidation_reason='Owner requires one unified actionable ad and budget plan; replaced21actions4300CNY')
  io.put(PLAN+previous['plan_id'],previous)
 url='https://api.telegram.org/bot'+io.bot+'/'
 me=io.tg('getMe',{});assert me['id']==8780468043
 captions={
 857:'Китай · утренний отчёт11ноября · данные8–10ноября. Общий план с бюджетным PNG858:15рекламных действий +6пополнений на4300CNY, всего21действие. Ответьте «Сделай всё» на ЛЮБОЙ из этих двух PNG — весь общий план выполнится один раз.41756218 — новая РК, отдельно от числовых итогов. Старые планы заменены. Ничего ещё не исполнено.',
 858:'Китай · бюджеты11ноября. Пополнить:40933588 +2500;40964981 +100;41055480 +300;41155909 +100;41270309 +250;41298169 +1050CNY. Итого4300CNY. Остальные решения «не пополнять» — в PNG. ОБЩИЙ план с рекламным PNG857:15рекламных действий +6пополнений. Ответ «Сделай всё» на любой из двух PNG подтверждает21действие один раз. Это не дневные лимиты.'
 }
 budget=next(f for f in v['files']if f['family']=='budgets')
 e['status']='editing';io.put(K,e)
 try:
  r=requests.post(url+'editMessageMedia',data={'chat_id':-1004342917488,'message_id':858,'media':json.dumps(dict(type='photo',media='attach://report',caption=captions[858]),ensure_ascii=False)},files={'report':('budgets.png',base64.b64decode(budget['b64']),'image/png')},timeout=90)
  j=r.json();assert r.ok and j.get('ok');receipt858=j['result'];assert receipt858['message_id']==858 and receipt858['chat']['id']==-1004342917488
  e['budget_edited']=True;io.put(K,e)
  receipt857=io.tg('editMessageCaption',dict(chat_id=-1004342917488,message_id=857,caption=captions[857]))
  assert receipt857['message_id']==857
  p.update(visible_from=datetime.now(timezone.utc).isoformat(),report_message_ids=[857,858]);io.put(PLAN+p['plan_id'],p)
  for mid,receipt in[(857,receipt857),(858,receipt858)]:
   io.put(BIND+str(mid),dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],chat_id=-1004342917488,family='drr'))
   bind(io,dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256']),receipt)
  io.put('china_agent:daily_ad_current_report:v1:budgets',dict(report_generation=p['report_generation'],plan_id=p['plan_id'],published_at=p['visible_from'],unified=True))
  e.update(status='edited_verified',receipts=[dict(message_id=r['message_id'],chat_id=r['chat']['id'],edit_date=r.get('edit_date'))for r in[receipt857,receipt858]],completed_at=datetime.now(timezone.utc).isoformat());io.put(K,e)
 except Exception:
  e['status']='uncertain';io.put(K,e);raise
 assert io.get(BIND+'857')['plan_sha256']==io.get(BIND+'858')['plan_sha256']==p['plan_sha256']
 print('Existing857858edited and bound to one21-action plan; no WB writes')
if __name__=='__main__':run()
