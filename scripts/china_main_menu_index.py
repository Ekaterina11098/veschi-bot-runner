"""Index only actually delivered advertising reports for cache-only menu navigation."""
ROOT='china_agent:main_menu:v1:report:'
def bind(io,f,p,receipt):
 family=f.get('family') or f.get('kind','').split(':',1)[0]
 if family not in ('drr','budgets'):return
 if receipt.get('chat',{}).get('id')!=-1004342917488 or receipt.get('from',{}).get('id')!=8780468043 or type(receipt.get('message_id'))is not int:raise ValueError('Menu report receipt scope')
 pointer=io.get('china_agent:daily_ad_current_report:v1:'+family)
 if not pointer or pointer.get('plan_id')!=p['plan_id']:return
 key=ROOT+family;old=io.get(key)
 mids=old.get('message_ids',[old['message_id']]) if old and old.get('plan_id')==p['plan_id'] and old.get('plan_sha256')==p['plan_sha256'] else []
 generation=p.get('report_generation',p['plan_id'])
 same=old and (old.get('report_generation')==generation or old.get('plan_id')==p['plan_id'])
 pages=list(old.get('pages',[])) if same else []
 if same and not pages and old.get('receipt'):pages=[dict(message_id=old['message_id'],receipt=old['receipt'],plan_id=old['plan_id'],plan_sha256=old['plan_sha256'],kind='legacy')]
 pages=[x for x in pages if x['message_id']!=receipt['message_id']]+[dict(message_id=receipt['message_id'],receipt=receipt,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],kind=f.get('kind',''))]
 pages.sort(key=lambda x:x['message_id'])
 mids=[x['message_id'] for x in pages]
 from datetime import datetime,timezone,timedelta
 day=datetime.fromtimestamp(receipt['date'],timezone(timedelta(hours=3))).date().isoformat()
 value=dict(status='sent',family=family,chat_id=-1004342917488,bot_id=8780468043,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],message_id=receipt['message_id'],message_ids=mids,report_day=day,receipt=receipt,pages=pages,report_generation=generation,wb_writes=0)
 if old:io.put(key,value)
 elif not io.create(key,value):raise RuntimeError('Menu report index claimed')
