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
 mids=sorted(set(mids+[receipt['message_id']]))
 from datetime import datetime,timezone,timedelta
 day=datetime.fromtimestamp(receipt['date'],timezone(timedelta(hours=3))).date().isoformat()
 value=dict(status='sent',family=family,chat_id=-1004342917488,bot_id=8780468043,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],message_id=receipt['message_id'],message_ids=mids,report_day=day,receipt=receipt,wb_writes=0)
 if old:io.put(key,value)
 elif not io.create(key,value):raise RuntimeError('Menu report index claimed')
