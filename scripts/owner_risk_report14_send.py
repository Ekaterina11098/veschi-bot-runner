"""Owner-requested three-campaign supplement. No WB calls or model transport."""
import os,base64,json
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
from china_advertising_state import AdvertisingIO
from china_advertising_delivery import deliver,telegram_sender
from china_daily_ad_actions import plan,bind
from china_loss_control import PLAN
ROOT='china_agent:owner_risk_report:2026-11-14:v1'
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'and os.environ['GITHUB_REF']=='refs/heads/main'
 io=AdvertisingIO();data=io.get(ROOT+':prepared');assert data['day']=='2026-11-14'and len(data['actions'])==3
 if(io.get(ROOT+':delivery')or{}).get('status')=='delivered':return
 import requests
 original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  parsed=urlparse(url)
  allowed=url.startswith(io.url+'/rest/v1/telegram_api_cache')or parsed.hostname=='api.telegram.org'and parsed.path.rsplit('/',1)[-1]in('getMe','sendPhoto')
  if not allowed:raise ValueError('Report sender prohibits WB/model/unrelated traffic')
  return original(session,method,url,**kw)
 requests.sessions.Session.request=guard
 from china_advertising_v2_png import _render_legacy
 frozen=io.get(ROOT+':artifacts')
 if not frozen:
  pages=[p for p in _render_legacy(data['bundle'])if p['family']=='drr'];assert len(pages)==1
  page=pages[0];assert page['actions']==data['actions']
  p=plan(io,data['day'],page,0,slot='risk-supplement-v1')
  # An additive supplement must not invalidate the other morning proposals.
  current=io.get('china_agent:daily_ad_current_report:v1:drr')or{};assert current.get('report_generation')
  p.update(report_generation=current['report_generation'],expires_at=(datetime.now(timezone.utc)+timedelta(hours=20)).isoformat())
  io.put(PLAN+p['plan_id'],p)
  frozen=dict(status='frozen',files=[dict(kind='drr:001',family='drr',page=1,total=1,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],action_count=3,b64=base64.b64encode(page['bytes']).decode())])
  assert io.create(ROOT+':artifacts',frozen)
 files=[dict(f,bytes=base64.b64decode(f['b64']),caption='Китай · дополнение к рекламному отчёту · 14.11.2026. Три решения по РК. Выберите нужное → «Посмотреть выбранное» → «Подтвердить». Зонты: 15 снижений + 100 CNY + запуск одним пунктом. Изменения ещё не выполнены.')for f in frozen['files']]
 result=deliver(io,data['day'],files,telegram_sender(io),binder=lambda f,r:bind(io,f,r),delivery_key=ROOT+':delivery',expected_families={'drr'})
 print(json.dumps(dict(status=result['status'],message_ids=[p.get('message_id')for p in result['parts']],wb_writes=0,model_calls=0)))
if __name__=='__main__':main()
