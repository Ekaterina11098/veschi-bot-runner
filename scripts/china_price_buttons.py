"""Keyboard and exact frozen price report registry; never executes prices."""
import hashlib
CHAT=-1004342917488
BOT=8780468043
def prepare(answer,offers,job_id,day,expires_at):
 if not offers:return None,None
 if type(job_id)is not int or job_id<=0:raise ValueError('Exact report job required')
 sha=hashlib.sha256(answer.encode()).hexdigest()
 token=hashlib.sha256((str(job_id)+':'+sha+':'+day).encode()).hexdigest()[:24]
 modes=['all'];buttons=[[dict(text='Сделай всё',callback_data='cpb1:'+token+':all')]]
 for mode,label,action in [('up','Только повышение цен','Повышение'),('down','Только снижение цен','Снижение')]:
  if any(r[0]==action for r in offers):
   modes.append(mode);buttons.append([dict(text=label,callback_data='cpb1:'+token+':'+mode)])
 registry=dict(status='active',chat_id=CHAT,bot_id=BOT,report_job_id=job_id,report_sha256=sha,report_date=day,expires_at=expires_at,allowed_modes=modes,execution_authorized=False)
 return dict(inline_keyboard=buttons),dict(key='china_agent:price_buttons:v1:'+token,payload=registry)
