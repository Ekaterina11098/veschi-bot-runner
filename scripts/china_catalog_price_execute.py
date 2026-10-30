"""Prospective catalog percentage prices via the existing exact-price engine. No Telegram sends."""
import copy,json,os,time
from datetime import datetime,timezone
from decimal import Decimal
from urllib.parse import quote
from china_price_apply import IO,process,plan,PREFIX,POLICY,day,sha
from china_catalog_price_command import ROOT,digest,signature,parse,selection,choose_percent
from china_cloud_cost_control import Cache,WB,validate_identity
CHAT=-1004342917488;BOT=8780468043
def stamp():return datetime.now(timezone.utc).isoformat()
def catalogue_snapshot(goods,execution_key):
 rows=list(goods.values())
 if not rows or len({g.get('nmID') for g in rows})!=len(rows):raise ValueError('Price snapshot identities incomplete')
 if any(type(g.get('nmID'))is not int or g['nmID']<=0 or not g.get('vendorCode') or g.get('currencyIsoCode4217')!='CNY' for g in rows):raise ValueError('China price snapshot currency or identity unavailable')
 return dict(cabinet='token_3',observed_at=stamp(),rows=rows,source='catalog_price_percent_verified_readback',execution_key=execution_key)
def verified_prior(io,p):
 excluded={};wanted=set(p['rules'].get('exclude_verified_percent_today',[]))
 if not wanted:return excluded
 records=io.db('telegram_api_cache?cache_key=like.china_agent:price_execution:v1:*&updated_at=gte.'+p['day']+'T00:00:00%2B03:00&select=cache_key,payload&limit=500')
 if len(records)>=500:raise ValueError('Prior price history truncated')
 for row in records:
  e=row['payload'];a=io.get(e.get('approval_key','')) or {};percent=None
  if a.get('basis')=='explicit_zero_order_percent':
   cmd=io.get('china_agent:zero_order_price_command:v1:'+str(a['report_job_id'])) or {};percent=cmd.get('percent')
  for it in e.get('items',[]):
   s=it.get('selection') or {};rb=it.get('readback') or {};pct=s.get('percent',percent)
   if pct not in wanted or it.get('status')!='applied':continue
   if rb.get('currencyIsoCode4217')!='CNY' or rb.get('vendorCode')!=s.get('article') or not rb.get('sizes') or not all(Decimal(str(z.get('discountedPrice')))==Decimal(s['target_cny']) for z in rb['sizes']):raise ValueError('Prior applied price lacks verified readback')
   when=e.get('completed_at') or e.get('created_at')
   if not when or (datetime.fromisoformat(when.replace('Z','+00:00'))+__import__('datetime').timedelta(hours=3)).date().isoformat()!=p['day']:continue
   excluded[s['nm_id']]=dict(article=s['article'],percent=pct,execution_key=row['cache_key'])
 if wanted and not excluded:raise ValueError('Cannot establish requested prior-price exclusion')
 return excluded
class CatalogIO(IO):
 def catalog(self):
  out={}
  for offset in range(0,10000,1000):
   batch=self.wb('/api/v2/list/goods/filter?limit=1000&offset='+str(offset)).get('listGoods',[])
   for g in batch:
    k=str(g['nmID'])
    if k in out:raise ValueError('Duplicate price catalog page')
    out[k]=g
   if len(batch)<1000:return out
  raise ValueError('Price catalog pagination incomplete')
 def prices(self,ids):
  for attempt in range(4):
   goods=self.catalog();selected={str(n):goods[str(n)] for n in ids if str(n) in goods}
   if not getattr(self,'readback_phase',False) or all(str(n) in selected and all(Decimal(str(z['discountedPrice']))==Decimal(self.write_selections[str(n)]['target_cny']) for z in selected[str(n)]['sizes']) for n in ids):break
   if attempt<3:time.sleep(3)
  if set(selected)!=set(map(str,ids)):raise ValueError('Exact goods missing in fresh WB read')
  return selected
 def validate(self,a):
  p=self.get(a['command_key']) or {};self.command=p;self.command_key=a['command_key'];self.readback_phase=False
  if p.get('signature')!=signature(p) or p.get('signature')!=a.get('command_signature') or datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']):raise ValueError('Catalog approval changed or expired')
  cfg=self.db('business_agent_config?agent_id=eq.china&select=active,chat_id,bot_id,owner_user_id')
  if cfg!=[dict(active=True,chat_id=CHAT,bot_id=BOT,owner_user_id=5122667182)]:raise ValueError('China identity changed')
  if p['source_channel']=='codex':
   if p['actor_user_id']!=5122667182 or not p.get('execution_authorized'):raise ValueError('Codex owner authority missing')
  elif p['source_channel']=='telegram':
   j=self.db('business_agent_jobs?id=eq.'+str(p['job_id'])+'&select=id,chat_id,sender_id,request_text')[0]
   if j['chat_id']!=CHAT or j['sender_id']!=p['actor_user_id'] or j['request_text']!=p['request_text']:raise ValueError('Human source changed')
   m=self.tg('getChatMember',dict(chat_id=CHAT,user_id=p['actor_user_id']))
   if m.get('user',{}).get('is_bot') or m.get('status') not in ['creator','administrator','member']:raise ValueError('Current human membership required')
  else:raise ValueError('Unknown price approval origin')
  selected={s['nm_id']:s for s in p['selections']}
  if a.get('basis')!='explicit_catalog_percent' or not a.get('selections') or any(selected.get(s['nm_id'])!=s for s in a['selections']) or a['selections_sha256']!=digest(a['selections']):raise ValueError('Exact catalog batch mismatch')
  self.write_selections={s['nm_id']:s for s in a['selections']}
  newer=self.db('business_agent_jobs?agent_id=eq.china&chat_id=eq.'+str(CHAT)+'&id=gt.'+str(p.get('last_human_job_id',0))+'&select=id,request_text&limit=100')
  if len(newer)>=100:raise ValueError('Newer human requests truncated')
  from china_single_price_command import parse_single
  for j in newer:
   text=j['request_text'];single=parse_single(text)
   same=single and any(single['reference'].casefold() in (nm,s['article'].casefold()) or (single['reference'].isdigit() and s['article'].casefold().startswith(single['reference']+'-')) for nm,s in selected.items())
   if parse(text) is not None or same or __import__('re').search(r'отмен|стой|стоп|не.{0,20}(?:меня|подним|повыш|сниж|цен)',text,__import__('re').I):
    raise ValueError('Newer human price clarification or cancellation requires review before applying')
 def tg(self,method,body):
  if method!='getChatMember':raise ValueError('No Telegram messages in catalog price executor')
  return super().tg(method,body)
 def wb(self,path,method='GET',body=None):
  if method!='GET':
   if method!='POST' or path!='/api/v2/upload/task' or set(body)!={'data'} or not body['data']:raise ValueError('Only exact catalog price upload allowed')
   seen=set()
   for row in body['data']:
    nm=str(row.get('nmID'));s=self.write_selections.get(nm)
    if not s or nm in seen or set(row)!={'nmID','price','discount'} or row['discount']!=s['seller_discount'] or Decimal(row['price'])*Decimal(100-row['discount'])/100!=Decimal(s['target_cny']):raise ValueError('Unapproved catalog price mutation')
    seen.add(nm)
  result=super().wb(path,method,body)
  if method=='GET' and path.startswith('/api/v2/history/goods/task?'):self.readback_phase=True
  return result
def prepare(io,key,p):
 validate_identity(Cache(),WB());io.capability()
 if datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']) or p.get('signature')!=signature(p):raise ValueError('Expired or changed catalog command')
 goods=io.catalog()
 included=p['rules'].get('include_nm_ids')
 if included:
  if len(included)!=1 or p.get('scope')!='single':raise ValueError('Single-price scope changed')
  if not all(n in goods for n in included):raise ValueError('Exact product missing')
  goods={n:goods[n] for n in included}
 if not goods:raise ValueError('Catalog empty')
 prior=verified_prior(io,p);ss=[];rows=[]
 for nm,g in sorted(goods.items(),key=lambda kv:int(kv[0])):
  if nm in prior:
   rows.append(dict(nm_id=nm,article=g.get('vendorCode'),status='excluded_prior_raise',prior=prior[nm]));continue
  try:
   if p['rules'].get('single_exact_percent'):
    base=selection(g,'1')
    pct=Decimal(p['rules']['default_percent']);target=Decimal(base['current_cny'])*(1+pct/100)
    if target<=0:raise ValueError('Price must be positive')
    s=dict(base,percent=str(pct),target_cny=str(target),nominal_target_cny=str(target),action='Снижение' if pct<0 else 'Повышение')
   else:s=selection(g,choose_percent(g['vendorCode'],p['rules']))
   request=plan(s,g);ss.append(s);rows.append(dict(selection=s,status='ready'))
  except ValueError as ex:rows.append(dict(nm_id=nm,article=g.get('vendorCode'),status='blocked',reason=str(ex)))
 p.update(status='prepared',prepared_at=stamp(),catalog_count=len(goods),excluded_prior=prior,selections=ss,rows=rows,source_goods={nm:g for nm,g in goods.items() if nm in {s['nm_id'] for s in ss}},batch_approvals=[])
 for start in range(0,len(ss),100):
  group=ss[start:start+100];hh=digest(dict(command=p['signature'],selections=group));jid=p.get('job_id',0);ak=PREFIX+str(CHAT)+':'+str(jid)+':'+str(p['actor_user_id'])+':'+hh
  a=dict(schema_version=2,execution_authorized=True,execution_policy=POLICY,approval_policy='all_current_human_group_members',decision='approved_recommendation',chat_id=CHAT,bot_id=BOT,report_job_id=jid,report_date=p['day'],report_sha256=sha(p['request_text']),actor_user_id=p['actor_user_id'],created_at=stamp(),selections=group,basis='explicit_catalog_percent',command_key=key,command_signature=p['signature'],selections_sha256=digest(group))
  p['batch_approvals'].append(dict(key=ak,approval=a))
 io.put(key,p);return p
def run_one(io,key):
 p=io.get(key)
 if not p or p.get('day')!=day() or p.get('status') not in ['requested','prepared','applying','submitted']:return p
 if p['status']=='requested':p=prepare(io,key,p)
 p['status']='applying';io.put(key,p);outputs=[]
 for b in p['batch_approvals']:
  if not io.get(b['key']):io.create(b['key'],b['approval'])
  e=process(io,b['key'],polls=8);outputs.append(e)
  results={x['selection']['nm_id']:x for part in outputs for x in part.get('items',[])}
  for r in p['rows']:
   nm=(r.get('selection') or {}).get('nm_id')
   if nm in results:r.update(results[nm])
  p['executions']=['china_agent:price_execution:v1:'+b['key'][len(PREFIX):] for b in p['batch_approvals'][:len(outputs)]]
  p['verified_count']=sum(r.get('status') in ['applied','already_at_target'] for r in p['rows']);p['total_count']=len(p['selections'])+sum(r['status']=='blocked' and 'selection' not in r for r in p['rows']);io.put(key,p)
  if e['status'] in ['submitted','submitting','uncertain']:
   p.update(status='submitted' if e['status']=='submitted' else 'uncertain',reason=e.get('reason','WB result unresolved'));io.put(key,p);return p
 if not p['selections']:p.update(verified_count=0,total_count=len(p['rows'])-len(p['excluded_prior']))
 p.update(status='verified' if p['verified_count']==p['total_count'] else 'partial',completed_at=stamp(),verified_at=stamp() if p['verified_count'] else None)
 io.put(key,p)
 # Preserve a compact canonical full-catalog snapshot and no personal data.
 io.put('china_agent:prices:v1',catalogue_snapshot(io.catalog(),key))
 return p
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 io=CatalogIO()
 keys=[ROOT+day()]
 rows=io.db('telegram_api_cache?cache_key=like.'+ROOT+day()+':sku:*&select=cache_key&order=updated_at.asc&limit=100')
 if len(rows)>=100:raise ValueError('Single-price queue truncated')
 keys.extend(r['cache_key'] for r in rows)
 for key in keys:
  p=io.get(key)
  if not p or p.get('status') not in ['requested','prepared','applying','submitted']:continue
  try:r=run_one(io,key)
  except (ValueError,RuntimeError) as ex:
   p=io.get(key);states=[io.get('china_agent:price_execution:v1:'+b['key'][len(PREFIX):]) or {} for b in p.get('batch_approvals',[])]
   has_write=any(e.get('status') in ['submitting','submitted','uncertain'] or e.get('upload_id') for e in states)
   p.update(status='uncertain' if has_write else 'blocked',reason=str(ex),updated_at=stamp());io.put(key,p);r=p
  print(json.dumps({k:r.get(k) for k in ['status','catalog_count','verified_count','total_count','reason']}))

if __name__=='__main__':main()
