"""Freeze existing IP recommendations/budgets privately; never sends, collects, or calls a model."""
import os,sys,json,copy,base64,hashlib
from pathlib import Path
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parent/'private-source'))
from advertising_agent import agent_store as store
from advertising_budget_evidence import load_daily_table_view
from ip_daily_png_contract import build_contract,render_recommendations,freeze_plan
from ip_campaign_table_png import render_campaign_table
from ip_budget_table_png import render_budget_png
ROOT='advertising:ip:report_clock:v1:'
CHAT=-1004378639510;BOT=8987327588

def credentials():
 from cryptography.hazmat.primitives.ciphers.aead import AESGCM
 secret=os.environ['SUPABASE_SECRET_KEY'].strip();token=os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()
 fingerprint=hashlib.sha256(secret.encode()).hexdigest();aad=f'ip-report-clock|{BOT}|{CHAT}'.encode();nonce=os.urandom(12)
 cipher=AESGCM(hashlib.sha256(secret.encode()).digest()).encrypt(nonce,token.encode(),aad)
 store.cache_set(ROOT+'sender_credential',dict(key_fingerprint=fingerprint,nonce=base64.b64encode(nonce).decode(),cipher=base64.b64encode(cipher).decode(),bot_id=BOT,chat_id=CHAT),ttl_days=365)

def metric(c):
 if not c or not c.get('metrics_complete')or any(c.get(k)is None for k in('spend','revenue')):return None
 return dict(spend=c['spend'],amount=c['revenue'],orders=c.get('total_orders'),clicks=c.get('clicks'))

def midday_image(full,current,contract,out):
 from ip_campaign_table_png import render_ip
 # Reuse the existing campaign-row renderer to obtain the identical table layout.
 import ip_campaign_table_png as renderer
 original=renderer.render_campaign_table
 def adapt(bundle):
  bundle=copy.deepcopy(bundle);by={c['campaign_id']:c for c in current['campaigns']}
  for c in bundle['campaigns']:
   now=by.get(c['id'],{});c['last']=metric(now);c['status']=now.get('status_id',c.get('status'));c['no_order_count']=now.get('no_order_count');c['no_order_spend']=now.get('no_order_spend')
  bundle.update(intraday=True,observed_day=current['period'],observed_at=current['observed_at'])
  bundle['source_observed_at']='Сегодня '+current['period']+' до '+datetime.fromisoformat(current['observed_at']).astimezone(ZoneInfo('Europe/Moscow')).strftime('%H:%M')+' МСК · неполный день; решения по завершённым дням'
  return original(bundle)
 renderer.render_campaign_table=adapt
 try:return render_ip(full,contract,out)
 finally:renderer.render_campaign_table=original

def main():
 now=datetime.now(timezone.utc);day=str(now.astimezone(ZoneInfo('Europe/Moscow')).date());slot=os.environ.get('IP_REPORT_SLOT','morning');verify=os.environ.get('IP_REPORT_VERIFY_ONLY')=='true'
 if slot not in('morning','midday'):raise ValueError('slot')
 key=ROOT+'artifact:'+day+':'+slot
 if not verify and(store.cache_get(key)or{}).get('status')=='ready':return {'status':'frozen_artifact_reused','source_calls':0}
 source=store.cache_get('advertising:ip:scheduled_source:v1:'+day+':'+slot)or{}
 if verify:source=store.cache_get('advertising:ip:morning_recovery:'+day+':v1')or{}
 if source.get('status')!='complete':raise RuntimeError('Complete dated source required; no empty PNGs')
 current=copy.deepcopy(source['view']);current['observed_at']=current.get('observed_at')or source.get('finished_at')or now.isoformat()
 if slot=='midday':
  fullsource=store.cache_get('advertising:ip:scheduled_source:v1:'+day+':morning')or store.cache_get('advertising:ip:morning_recovery:'+day+':v1')or{}
  full=copy.deepcopy(fullsource.get('view')or load_daily_table_view(store,now))
 else:full=copy.deepcopy(current)
 full['_recent_views']=[]
 for back in(2,1):
  older=load_daily_table_view(store,now-timedelta(days=back));full['_recent_views'].append(older)
 contract=build_contract(store,full)
 # A stale WB configuration cannot turn a paused catalog campaign into ready traffic growth.
 active={c['campaign_id']for c in current['campaigns']if c.get('status_id')==9}
 contract['actions']=[a for a in contract['actions']if a['campaign']in active]
 contract['plan_sha256']=hashlib.sha256(json.dumps(contract['actions'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 from ip_report_analysis import review_report
 contract=review_report(store,full,contract)
 for c in full['campaigns']:c['campaign_name']=c.get('campaign_name')or(contract.get('campaign_labels',{}).get(str(c['campaign_id']))or{}).get('name')or''
 out=Path(os.environ['RUNNER_TEMP'])/'ip-report-frozen'
 recommendation=midday_image(full,current,contract,out)if slot=='midday'else render_recommendations(full,contract,out)
 budgetview=copy.deepcopy(full);budgetview['observed_day']=day;budgetview['intraday']=slot=='midday'
 if slot=='midday':
  for c in budgetview['campaigns']:
   recent=next((r for r in current['campaigns']if r['campaign_id']==c['campaign_id']),{})
   c['budget']=recent.get('budget')or{};c['status_id']=recent.get('status_id')
 budget,coverage=render_budget_png(budgetview,out)
 images=[]
 for item in[recommendation]+([budget]if budget else[]):
  raw=Path(item['path']).read_bytes();images.append(dict(kind=item['kind'],sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(raw).decode()))
 if verify:
  store.cache_set('advertising:ip:report-analysis:v1:'+full['period']+':preview',dict(contract=contract,images=images,view=full),ttl_days=32)
  return dict(status='verified_saved_only',period=full['period'],analysis=contract.get('sol_analysis'),model_calls=contract['sol_analysis']['model_calls_this_run'],charged_micro_usd=contract['sol_analysis'].get('charged_micro_usd'),actions=[{k:a.get(k)for k in('sku','campaign','kind','target_bid_minor')}for a in contract['actions']],images=[{k:i[k]for k in('kind','sha256')}for i in images],source_calls=0,wb_writes=0,telegram_calls=0)
 plan_key=None
 if slot=='morning':
  plan_key,_=freeze_plan(store,contract,images[0]['sha256'])
  from ip_cloud_dialog import publish_context
  publish_context(store,full,contract)
 credentials()
 store.cache_set('advertising:ip:report-analysis:v1:'+full['period']+':prepared',dict(contract=contract,view=full,images=[{k:i[k]for k in('kind','sha256')}for i in images],verified_saved_only=verify),ttl_days=32)
 payload=dict(status='ready',slot=slot,day=day,data_period=full['period'],images=images,chat_id=CHAT,bot_id=BOT,plan_key=plan_key,new_actions=len(contract['actions']),budget_coverage=coverage,prepared_at=now.isoformat(),intraday=slot=='midday',own_summary=source.get('own_summary'))
 store.cache_set(key,payload,ttl_days=32)
 if store.cache_get(key)!=payload:raise RuntimeError('Frozen PNG readback mismatch')
 # Event wakeup also covers a late runner, without another periodic collector or a blind resend.
 import hmac,requests
 signature=hmac.new(os.environ['SUPABASE_SECRET_KEY'].encode(),f'{day}|{slot}|prepared'.encode(),hashlib.sha256).hexdigest()
 response=requests.post(os.environ['SUPABASE_URL'].rstrip('/')+'/functions/v1/ip-report-clock',headers={'x-ip-prepared-signature':signature},json={'prepared_event':True,'day':day,'slot':slot},timeout=(10,90))
 store.cache_set(ROOT+'prepared_event:'+day+':'+slot,{'http_status':response.status_code,'observed_at':datetime.now(timezone.utc).isoformat()},ttl_days=32)
 return dict(status='ready',images=len(images),source_calls=0,wb_writes=0,telegram_calls=0)

if __name__=='__main__':
 try:
  result=main();print(json.dumps({k:result[k]for k in('status','period','source_calls','wb_writes','telegram_calls')if k in result}))
 except Exception as e:print(json.dumps({'status':'report_freeze_blocked','error_type':type(e).__name__}));raise SystemExit(1)
