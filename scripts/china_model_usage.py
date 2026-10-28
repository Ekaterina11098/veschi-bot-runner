"""Private content-free model accounting; logging failure never repeats a paid call."""
import json,os,time,uuid,re
from datetime import datetime,timezone
PREFIX='china_agent:model_usage:v1:'
def task_type(text):
 text=(text or '').lower()
 for name,pattern in [('zero_orders',r'без заказ|не имеют заказ|нет заказ|14 д'),('bid_plan',r'ставк|подним|повыс.*реклам'),('price_review',r'цен'),('profit',r'прибыл|экономик'),('report',r'отч[её]т|дрр'),('sales_analysis',r'продаж|заказ|выкуп')]:
  if re.search(pattern,text):return name
 return 'general_dialog'
def number(obj,key):
 value=obj.get(key)
 return value if type(value)is int and value>=0 else None
def size(value):
 return len(json.dumps(value,ensure_ascii=False,separators=(',',':'),default=str).encode())
def record(body,response,context,elapsed,error=None):
 response=response or {};usage=response.get('usage');usage=usage if isinstance(usage,dict) else {}
 details=usage.get('input_tokens_details') or {};out=usage.get('output_tokens_details') or {}
 messages=body.get('input') or [];messages=messages if isinstance(messages,list) else []
 role_bytes={};tool_results=[]
 for m in messages:
  if not isinstance(m,dict):continue
  role=m.get('role') or m.get('type') or 'other';role_bytes[role]=role_bytes.get(role,0)+size(m)
  if m.get('type')=='function_call_output':tool_results.append(size(m))
 return dict(version=1,recorded_at=datetime.now(timezone.utc).isoformat(),source='responses_api',
  job_id=context.get('job_id'),agent_id=context.get('agent_id','china'),task_type=context.get('task_type','unattributed'),stage=context.get('stage','unknown'),turn=context.get('turn'),
  model=response.get('model') or body.get('model'),response_id=response.get('id'),request_id=context.get('request_id'),
  status='error' if error else response.get('status','received'),error_type=type(error).__name__ if error else None,
  input_tokens=number(usage,'input_tokens'),cached_input_tokens=number(details,'cached_tokens'),cache_write_input_tokens=number(details,'cache_write_tokens'),
  output_tokens=number(usage,'output_tokens'),reasoning_tokens=number(out,'reasoning_tokens'),total_tokens=number(usage,'total_tokens'),
  usage_status='reported' if usage else 'missing_not_zero',duration_ms=round(elapsed*1000),
  input_bytes=size(body.get('input')),tool_schema_bytes=size(body.get('tools',[])),message_count=len(messages),role_bytes=role_bytes,
  tool_result_count=len(tool_results),largest_tool_results_bytes=sorted(tool_results,reverse=True)[:5],
  tool_names=list(context.get('tool_names') or []),cost_usd=None,cost_status='unpriced_requires_verified_tariff',
  synthetic=context.get('synthetic',False))
def persist(value):
 import requests
 base=os.environ.get('SUPABASE_URL');secret=os.environ.get('SUPABASE_SECRET_KEY')
 if not base or not secret:return False
 key=('china_agent:model_usage_smoke:v1:' if value.get('synthetic') else PREFIX)+(value.get('response_id') or value.get('request_id') or uuid.uuid4().hex)
 headers={'apikey':secret,'Prefer':'resolution=ignore-duplicates,return=minimal'}
 if not secret.startswith('sb_secret_'):headers['Authorization']='Bearer '+secret
 r=requests.post(base.rstrip('/')+'/rest/v1/telegram_api_cache',params={'on_conflict':'cache_key'},headers=headers,
  json=dict(cache_key=key,payload=value,updated_at=value['recorded_at'],expires_at='2036-10-28T00:00:00+00:00'),timeout=5)
 return bool(r.ok)
def metered_request(request,body,**context):
 started=time.monotonic();context=dict(context,request_id=uuid.uuid4().hex)
 try:response=request(body)
 except Exception as error:
  try:
   if not persist(record(body,None,context,time.monotonic()-started,error)):print('model_usage_log_unavailable')
  except Exception:print('model_usage_log_unavailable')
  raise
 try:
  if not persist(record(body,response,context,time.monotonic()-started)):print('model_usage_log_unavailable')
 except Exception:print('model_usage_log_unavailable')
 return response
