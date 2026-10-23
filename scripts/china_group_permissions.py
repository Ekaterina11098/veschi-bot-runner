"""Owner-authorized shared command permissions, confined to current China humans."""
from china_loss_control import CHAT,BOT,OWNER,marker
KEY='china_agent:command_permissions:v2'
def shared(w):
 p=w.get(KEY) or {}
 return p.get('policy')=='all_current_human_group_members' and p.get('chat_id')==CHAT and p.get('bot_id')==BOT and p.get('enabled') is True
def allowed(w,job):
 cfg=w.config() if hasattr(w,'config') else dict(chat_id=CHAT,bot_id=BOT,owner_user_id=OWNER)
 actor=job.get('sender_id')
 if type(actor) is not int or actor<=0:return False
 if not shared(w):return job.get('chat_id')==cfg.get('chat_id') and actor==cfg.get('owner_user_id',OWNER)
 if job.get('chat_id')!=CHAT or cfg.get('chat_id')!=CHAT or cfg.get('bot_id')!=BOT or marker(job).get('bot_id') not in (None,BOT) or marker(job).get('forwarded') is True:return False
 check=getattr(w,'member_check',None)
 if not callable(check):return False
 try:m=check(actor)
 except Exception:return False
 user=m.get('user') or {}
 return user.get('id')==actor and user.get('is_bot') is False and (m.get('status') in ('creator','administrator','member') or m.get('status')=='restricted' and m.get('is_member') is True)
