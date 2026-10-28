"""Plain Telegram formatting and cached current advertising membership, no network."""
import re
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
RULES=('Пиши обычным текстом без Markdown ** и буквальных символов обратный слеш+n. '
 'Высокая историческая ДРР не означает, что товар сейчас рекламируется в той же РК. '
 'Перед списком товаров с высокой ДРР используй read_recent_actions и текущий состав РК; '
 'в каждой строке укажи отдельно: РК/период показателя, уже исключён здесь или ещё активен, '
 'где остался в других РК и текущая ставка. Исключение из одной РК не равно исключению из всех. '
 'Число всех проблемных позиций называй только после проверки всех РК; при частичных данных явно напиши число проверенных и неполноту. '
 'Скрытые здоровые SKU входят в расходы РК: нельзя объяснять маленький расход РК скрытием товаров. '
 'Сначала сверь даты: сегодня неполный день против полных вчерашних суток. '
 'Если причин расхождения не проверено, не выдумывай объяснение. '
 'При complete=false в текущем составе РК не объявляй список полным и отсутствие товара доказанным исключением. '
 'Неизвестная ставка не равна нулю. «Да или нет» начинай с прямого ответа и отдельно называй подтвержденную часть и исключения. '
 'Уточнение относится к конкретному плану: не подменяй каталог прежним списком товаров без заказов.')
def normalize_answer(text):
 if not isinstance(text,str) or '[[' in text:return text
 if r'\n\n' in text:text=text.replace(r'\n','\n')
 return re.sub(r'\*\*([^\n]+?)\*\*',r'\1',text)
def _time(value):
 try:return datetime.fromisoformat(value.replace('Z','+00:00'))
 except (AttributeError,ValueError,TypeError):return None
def current_memberships(w):
 day=str(w.now.astimezone(MSK).date())
 cached=w.get('china_agent:advertising_intraday:'+day+':v1') or {}
 observed=_time(cached.get('observed_at'))
 if not cached.get('complete') or observed is None or observed.tzinfo is None:return dict(available=False,note='Текущий состав не подтверждён в общем кэше; исторический расход не доказывает текущую рекламу.')
 labels=dict(w.catalog());rows={};camps=cached.get('campaigns',[])
 if isinstance(camps,dict):camps=list(camps.values())
 camps={str(c['id']):c for c in camps if isinstance(c,dict) and c.get('id') is not None}
 sources=[];unresolved=[]
 registry=w.get('china_agent:verified_campaign_state:v1') or {}
 for cid,key in registry.items():
  if not str(cid).isdigit() or not isinstance(key,str):continue
  e=w.get(key) or {};after=e.get('after') or {};at=_time(e.get('verified_at'))
  if at is not None and at.tzinfo is not None and at<observed:continue
  if e.get('status')!='verified' or str(after.get('id'))!=str(cid) or at is None or at.tzinfo is None or at>max(w.now,datetime.now(timezone.utc))+timedelta(minutes=1) or not isinstance(after.get('nm_settings'),list):
   unresolved.append(str(cid));continue
  camps[str(cid)]=after;sources.append(dict(rc=after['id'],execution_key=key,verified_at=e['verified_at']))
 for c in camps.values():
  if c.get('status')!=9:continue
  placements=c.get('settings',{}).get('placements',{})
  zones=[(field,label) for field,label in [('search','поиск'),('recommendations','рекомендации')] if placements.get(field) is True]
  if not zones:unresolved.append(str(c['id']));continue
  for n in c.get('nm_settings',[]):
   nm=n.get('nm_id')
   if type(nm) is not int:unresolved.append(str(c['id']));continue
   article=labels.get(str(nm),labels.get(nm,'WB '+str(nm)))
   for field,zone in zones:
    raw=n.get('bids_kopecks',{}).get(field)
    bid=raw/100 if type(raw) is int and raw>0 else None
    rows.setdefault(article,[]).append(dict(rc=c['id'],zone=zone,bid_cny=bid))
 return dict(available=True,complete=not unresolved,observed_at=cached['observed_at'],verified_overlays=sources,unresolved_campaigns=sorted(set(unresolved)),active_memberships=rows,wb_reads=0,
  note='Сохранённый общий состав и более поздние WBverified-квитанции. При complete=false отсутствие товара не доказывает исключение из всех РК. Неизвестная ставка не равна 0; исторический расход сохраняется.')
