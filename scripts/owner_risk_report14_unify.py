"""Replace today's existing two report photos; remove the superseded supplement."""
import os,json,copy,base64,hashlib
from datetime import datetime,timezone
from urllib.parse import urlparse
from china_advertising_state import AdvertisingIO
from china_loss_control import PLAN
from china_daily_ad_actions import plan,bind,BIND
from china_report_buttons import prepare,ROOT as BUTTONS
ROOT='china_agent:owner_risk_report:2026-11-14:v1:unified'
DAY='2026-11-14';CHAT=-1004342917488
def main():
 io=AdvertisingIO()
 if(io.get(ROOT)or{}).get('status')=='delivered':return
 assert not io.get(ROOT),'Existing correction journal; do not replay an uncertain edit'
 original=io.get('china_agent:advertising_artifacts:'+DAY+':v2');extra=io.get('china_agent:owner_risk_report:'+DAY+':v1:prepared')
 delivery=io.get('china_agent:advertising_delivery:'+DAY+':v1');assert delivery['status']=='delivered'
 previous=[PLAN+f['plan_id']for f in original['files']]+[PLAN+'daily-2026-11-14-risk-supplement-v1-drr-0']
 for key in previous:
  p=io.get(key);assert p and not io.get('china_agent:daily_ad_execution:v2:'+p['plan_id']),'Prior plan processing; do not replace confirmed actions'
  assert not(io.get('china_agent:daily_action_claim:v1:'+p['plan_id'])or{}).get('domains'),'Prior plan already confirmed'
 import requests
 old=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  allowed=url.startswith(io.url+'/rest/v1/telegram_api_cache')or urlparse(url).hostname=='api.telegram.org'and urlparse(url).path.rsplit('/',1)[-1]in('getMe','editMessageMedia','deleteMessage')
  if not allowed:raise ValueError('Correction prohibits WB/model/other messages')
  return old(session,method,url,**kw)
 requests.sessions.Session.request=guard
 from china_advertising_v2_png import render
 b=copy.deepcopy(original['bundle']);updates={c['id']:c for c in extra['bundle']['campaigns']}
 for c in b['campaigns']:
  u=updates.get(c['id'])
  if not u:continue
  for k in ['status','balance','name','focus','attention','budget_short_note','budget_recommendation']:c[k]=copy.deepcopy(u[k])
  c['financial_action']=copy.deepcopy(next(a for a in extra['actions']if a['campaign_id']==c['id']))
  c['financial_recommendation']=u['direction_recommendations'][0];c['budget_action']=None;c['budget_review_required']=True
 b.update(source_observed_at='14.11.2026 07:31 МСК; три РК дополнительно проверены 09:39–09:42',mandatory_campaign_format=False)
 pages=render(b);assert [f['family']for f in pages]==['drr','budgets']
 assert [len(f['actions'])for f in pages]==[18,5]
 assert len({a['id']for f in pages for a in f['actions']})==23
 # Preserve all existing ready proposals, adding two pauses and one atomic recovery.
 old_ids={a['id']for f in original['files']for a in io.get(PLAN+f['plan_id'])['items']}
 assert old_ids<={a['id']for f in pages for a in f['actions']}
 state=dict(status='prepared',created_at=datetime.now(timezone.utc).isoformat(),parts=[],wb_writes=0,model_calls=0)
 assert io.create(ROOT,state)
 def save():io.put(ROOT,copy.deepcopy(state))
 for key in previous:
  p=io.get(key);p.update(invalidated_at=datetime.now(timezone.utc).isoformat(),invalidation_reason='Owner requested the complete updated two-PNG report');io.put(key,p)
 for index,f in enumerate(pages):
  p=plan(io,DAY,f,index,slot='risk-unified-v1');f.update(plan_id=p['plan_id'],plan_sha256=p['plan_sha256'])
  part=next(x for x in delivery['parts']if x['kind'].split(':')[0]==f['family']);mid=part['message_id']
  cap='Китай · '+('ДРР и рекомендации по РК'if f['family']=='drr'else'бюджеты и суммы пополнения')+' · 14.11.2026. Обновлённый общий отчёт. Новых пунктов: '+str(len(p['items']))+'. Выберите нужное → «Посмотреть выбранное» → «Подтвердить».'
  if f['family']=='budgets':cap+=' По 41325637 подтверждение включает 15 снижений до 0,23 CNY, +100 CNY и возобновление.'
  markup=prepare(io,p,f['family']);assert markup
  record=dict(family=f['family'],message_id=mid,status='editing',plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],sha256=hashlib.sha256(f['bytes']).hexdigest(),actions=len(p['items']))
  state['parts'].append(record);save()
  media=dict(type='photo',media='attach://photo',caption=cap)
  try:
   r=requests.post('https://api.telegram.org/bot'+io.bot+'/editMessageMedia',data=dict(chat_id=CHAT,message_id=mid,media=json.dumps(media,ensure_ascii=False),reply_markup=json.dumps(markup,ensure_ascii=False)),files={'photo':('report.png',f['bytes'],'image/png')},timeout=60)
   result=r.json();assert r.ok and result.get('ok');receipt=result['result'];assert receipt['message_id']==mid and receipt['chat']['id']==CHAT and receipt['reply_markup']==markup
   record.update(status='edited',receipt=receipt);save()
  except Exception:
   record['status']='uncertain';state['status']='uncertain';save();raise
  # Rebind an explicitly edited message only after its exact Telegram receipt.
  io.put(BIND+str(mid),dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],chat_id=CHAT,family=f['family']))
  token=markup['inline_keyboard'][0][0]['callback_data'].split(':')[1]
  io.put(BUTTONS+'message:'+str(mid),dict(status='sent',token=token,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],family=f['family'],chat_id=CHAT,bot_id=8780468043,message_id=mid,receipt=receipt))
  bind(io,f,receipt)
 supplement=io.get('china_agent:owner_risk_report:'+DAY+':v1:delivery');assert supplement['status']=='delivered'
 for part in supplement['parts']:
  assert part['message_id']==1038
  state['supplement_deletion']=dict(status='deleting',message_id=1038);save()
  try:
   assert io.tg('deleteMessage',dict(chat_id=CHAT,message_id=1038))is True
   state['supplement_deletion']['status']='deleted';save()
  except Exception:
   state['supplement_deletion']['status']='uncertain';state['status']='uncertain';save();raise
 state.update(status='delivered',completed_at=datetime.now(timezone.utc).isoformat());save()
 print(json.dumps(dict(status='delivered',message_ids=[p['message_id']for p in state['parts']],actions=[p['actions']for p in state['parts']],supplement_deleted=1038,wb_writes=0,model_calls=0)))
if __name__=='__main__':main()
