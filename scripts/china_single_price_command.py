"""Future explicit single-product China price requests; never infer financial consent."""
import re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from china_catalog_price_command import ROOT,signature,status_text
def parse_single(text):
 if re.search(r'вс[её]х?\s+(?:товар|цен)|всем|всему|noelbag.*все',text,re.I):return None
 if not re.search(r'цен',text,re.I) or re.search(r'ставк|бюджет|реклам',text,re.I):return None
 if re.search(r'\bне\b|как|почему|напомни|объясни|обсуд|план|завтра|потом|позже|через|когда|после|вчера|уже|поднимал|повышал|снижал',text,re.I):return None
 if '?' in text or re.search(r'не\s+(?:надо|подним|повыш|сниж|меня)|может|если|можно|стоит ли|проверь|рассчитай|предложи|поднял|поменял|изменил',text,re.I):return None
 matches=re.findall(r'(?<![\w-])(\d{1,12}-[A-Za-z][\w-]+)',text)
 if not matches:
  matches=re.findall(r'(?:артикул|арт[.]?|товар)\s*(\d{1,12})(?!\d)(?!\s*%)',text,re.I)
 if not matches:matches=re.findall(r'(\d{1,12})\s+сумк',text,re.I)
 if not matches:matches=re.findall(r'цен[уы]\s+(?:на\s+)?(\d{1,12})(?!\d)(?!\s*%)',text,re.I)
 if len(set(matches))!=1:return None
 percentages=re.findall(r'([+-]?\d+(?:[.,]\d+)?)\s*%',text)
 if len(percentages)!=1:return None
 pct=float(percentages[0].replace(',','.'))
 lower=bool(re.search(r'сниз|сниж|уменьш|опуст',text,re.I))
 if lower:pct=-abs(pct)
 action=bool(re.search(r'подним|поднять|повысь|повыс|увелич|сниз|сниж|уменьш|опуст|меня|\+\s*\d',text,re.I))
 if not action or pct==0 or not -90<=pct<=100:return None
 return dict(reference=matches[0],percent=format(pct,'g'))
def handle(w,job,history=()):
 text=job.get('request_text','');p=parse_single(text)
 if not p:
  if re.search(r'цен|поднял|изменил|поменял|выполн',text,re.I) or re.fullmatch(r'\s*(?:делай|сделай|пробуй|давай)[.! ]*',text,re.I):
   today=w.now.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
   for h in reversed(history[-4:]):
    previous=parse_single(h.get('request_text',''))
    if not previous or h.get('id') is None:continue
    ref=previous['reference'].casefold()
    found=[str(n) for n,a in w.catalog() if str(n)==ref or a.casefold()==ref or (ref.isdecimal() and a.casefold().startswith(ref+'-'))]
    if len(found)!=1:continue
    key=ROOT+today+':sku:'+found[0]+':'+str(h['id']);old=w.get(key)
    if old:
     return status_text(old),[dict(name='single_price_status',command_key=key,status=old['status'],wb_writes=0)]
  return None
 if re.search(r'ООО|\bИП\b|в обоих|два кабинет',text,re.I):
  return 'Этот ценовой исполнитель привязан к Китаю. Изменение другого кабинета здесь не выполняю и выполненным не называю.',[dict(name='single_price_command',status='cabinet_mismatch')]
 if not w.authorized(job):return 'Нет подтверждённых прав действующего участника группы.',[dict(name='single_price_command',status='unauthorized')]
 ref=p['reference'].casefold()
 found=[(str(n),a) for n,a in w.catalog() if str(n)==ref or a.casefold()==ref or (ref.isdecimal() and a.casefold().startswith(ref+'-'))]
 if len(found)!=1:return 'Артикул не определён однозначно в каталоге Китая; цену не меняю.',[dict(name='single_price_command',status='ambiguous_identity')]
 nm,article=found[0];day=w.now.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
 key=ROOT+day+':sku:'+nm+':'+str(job['id'])
 old=w.get(key)
 if old:return status_text(old),[dict(name='single_price_command',command_key=key,duplicate_prevented=True)]
 # A repeated request in the same conversation is a status check, not a compounded raise.
 parent=next((t.get('parent_job_id') for t in job.get('tool_trace',[]) if t.get('name')=='china_saved_question'),None)
 for h in reversed(history[-4:]):
  hp=parse_single(h.get('request_text',''))
  if hp==p and (h.get('id')==parent or h.get('request_text')==text):
   prior=w.get(ROOT+day+':sku:'+nm+':'+str(h['id']))
   if prior:return status_text(prior),[dict(name='single_price_command',duplicate_prevented=True)]
 stamp=w.now.astimezone(timezone.utc)
 value=dict(status='requested',scope='single',day=day,actor_user_id=job['sender_id'],source_channel='telegram',request_text=text,job_id=job['id'],last_human_job_id=job['id'],
  created_at=stamp.isoformat(),expires_at=(stamp+timedelta(hours=2)).isoformat(),article=article,
  rules=dict(default_percent=p['percent'],overrides=[],include_nm_ids=[nm],single_exact_percent=True),
  source_refs=[dict(job_id=job['id'],request_text=text)])
 value['signature']=signature(value);w.save(key,value,insert=True)
 return status_text(w.get(key) or value),[dict(name='single_price_command',command_key=key,status='requested',wb_writes=0)]
