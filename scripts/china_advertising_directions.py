"""Four-way review coverage from completed sources, without writes or implicit approvals."""
import copy
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
LABELS={'raise':'Повышение ставок','add':'Добавление товаров','reduce':'Снижение ставок','exclude':'Исключение из РК'}
def addition_shortlist(source,products):
 from china_advertising_v2 import history,event_time
 active={n['nm_id'] for b in source.get('batches',{}).values() for c in b['campaigns'].get('adverts',[]) if c['status']in[9,11] for n in c.get('nm_settings',[])}
 end=date.fromisoformat(source['period_to']);changed=set();removed=set()
 for event in history(source.get('executions',[])):
  if event['kind']=='excluded':removed.add(event['nm']) # reinstatement needs a separate owner review
  if event['kind']in['price','bid','added','returned','relaunch']and event_time(event['at']).astimezone(ZoneInfo('Europe/Moscow')).date()+timedelta(days=1)>=end:changed.add(event['nm'])
 known={r['nmID'] for r in source['catalogue']['rows']};candidates=[]
 for r in products.get('rows',[]):
  nm=int(r['nm_id']);finished=r.get('finished_orders')or 0;paid=r.get('is_payed')or 0;opens=r.get('open_card_count')or 0;orders=r.get('funnel_orders_count')or 0
  if nm in active or nm in removed or nm in changed or nm not in known:continue
  if finished<5 or paid<3 or opens<=0 or orders/opens<.005:continue
  candidates.append((orders,paid,nm))
 return [nm for _,_,nm in sorted(candidates,reverse=True)[:12]]
def attach(bundle,source):
 out=copy.deepcopy(bundle);sections={key:dict(label=label,rows=[],status='checked',note='Подтверждённых кандидатов нет.')for key,label in LABELS.items()}
 seen=set()
 for c in out['campaigns']:
  if c['status']!=9:continue
  for r in c.get('focus',[]):
   a=r.get('action')or{};kind=a.get('kind');key='exclude'if kind=='ad_exclude_sku'else'raise'if kind=='ad_set_bid'and a.get('target_minor',0)>a.get('old_minor',0)else'reduce'if kind=='ad_set_bid'else None
   if not key:continue
   signature=(key,c['id'],r['nm'])
   if signature in seen:continue
   seen.add(signature);sections[key]['rows'].append(dict(article=r['article'],campaign_id=c['id'],decision=r['decision'],action=a,period=r.get('period'),economics=r.get('economics')or{},ready=True))
 scan=source.get('addition_scan')or{};labels={r['nmID']:r['vendorCode']for r in source['catalogue']['rows']}
 growth=out.get('growth_review')or{}
 if growth.get('status')=='blocked':sections['raise'].update(status='unavailable',note='Подбор повышений не завершён: '+str(growth.get('reason','неполные данные'))+'. Это не отсутствие кандидатов.')
 if scan.get('status')!='complete':sections['add'].update(status='unavailable',note='Полный подбор товаров без рекламы не завершён; отсутствие кандидатов не установлено.')
 else:
  sections['add']['period']=[scan['period_from'],scan['period_to']]
  for nm in scan.get('candidate_ids',[]):
   e=(source.get('economics',{}).get('rows')or{}).get(str(nm))or{}
   if e and isinstance(e.get('stock_free'),(int,float)) and e['stock_free']<=0:continue
   if not e or e.get('expected_margin_before_ads_cny')is None:
    sections['add']['rows'].append(dict(article=labels.get(nm,'WB '+str(nm)),nm_id=nm,decision='Предварительный кандидат без рекламы: собственная экономика/цена/остаток не подтверждены полностью. Готового добавления нет.',ready=False));continue
   if e['expected_margin_before_ads_cny']<=0 or e.get('stock_free',0)<=0:continue
   if e.get('buyout_fallback')or e.get('sample_size',0)<5:continue
   quote=(source.get('addition_bid_quotes')or{}).get(str(nm))or{}
   sections['add']['rows'].append(dict(article=labels.get(nm,'WB '+str(nm)),nm_id=nm,campaign_id=quote.get('campaign_id'),target_minor=quote.get('target_minor'),bid_verified=quote.get('bid_verified')is True,decision='Добавить только после отдельного согласования точного плана.',economics=e,ready=False))
  sections['add']['note']='Предварительные кандидаты; точная РК/ставка требуют проверки.'if sections['add']['rows']else'Проверены товары без активной рекламы; положительная подтверждённая экономика не выделила кандидатов.'
 for key,s in sections.items():
  if s['rows']and key!='add':s['note']=str(len(s['rows']))+' готовых предложений; только после согласования.'
  s['count']=len(s['rows'])
 out['recommendation_directions']=sections
 archives=[c for c in out['campaigns']if c['status']==7]
 missing=[c['id']for c in archives if c.get('period')is None or c.get('missing_stats')]
 totals={k:sum(c['period'][k]for c in archives if c.get('period')is not None)for k in ['spend','amount','orders']}
 out['archive_expenses']=dict(campaign_ids=[c['id']for c in archives],missing_stats_ids=missing,totals=totals,complete=not missing,rule='Архивные расходы включены в исторический итог. Отсутствующий ответ не равен нулю. Архивы не кандидаты на запуск/пополнение.')
 return out

def campaign_table(bundle):
 """Preserve the approved campaign-row table. Only the recommendation cell is brief."""
 out=copy.deepcopy(bundle);byid={c['id']:c for c in out['campaigns']}
 for c in out['campaigns']:c['direction_recommendations']=['Не запускать.']if c['status']==7 else[]
 for key,section in out['recommendation_directions'].items():
  for r in section['rows']:
   cid=r.get('campaign_id')
   if key=='add'and not cid:
    # The addition scan must select an evidenced actual campaign before display.
    continue
   c=byid.get(cid)
   if not c or c['status']!=9:continue
   a=r.get('action')or{}
   if key=='add':
    if r.get('bid_verified')is not True or type(r.get('target_minor'))is not int:continue
    text='Добавить · ставка '+str(r['target_minor']/100)+' CNY.'
   elif key=='exclude':text='Исключить из РК.'
   else:text=(('Тест: повысить'if a.get('manual_experiment')else'Повысить')if key=='raise'else'Снизить')+' '+str(a['old_minor']/100)+' → '+str(a['target_minor']/100)+' CNY.'
   c['direction_recommendations'].append(r['article']+': '+text)
 # Unready research stays in the private Codex analysis journal.
 return out

def overview(bundle):
 """Read-only summary page; bound actionable rows remain on their detailed PNG pages."""
 import io
 from PIL import Image,ImageDraw
 from china_advertising_v2_png import font,NAVY,BG,INK
 W,H=2200,7000;files=[];actions=[];im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im);y=170
 def header():
  d.rectangle((0,0,W,140),fill=NAVY);d.text((40,25),'Китай · все направления рекламного разбора',font=font(42,True),fill='white');d.text((40,88),str(bundle.get('source_observed_at','Датированный срез')),font=font(25),fill='white')
 def finish():
  buf=io.BytesIO();im.crop((0,0,W,min(y+40,H))).save(buf,format='PNG');files.append(dict(family='drr',bytes=buf.getvalue(),actions=copy.deepcopy(actions)))
 def line(text,size=27,bold=False):
  nonlocal y,im,d,actions
  words=str(text).split();row=''
  for word in words+['']:
   if row and(word==''or d.textlength(row+' '+word,font=font(size,bold))>W-100):
    if y>H-120:finish();im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im);y=170;actions=[];header()
    d.text((40,y),row,font=font(size,bold),fill=INK);y+=size+13;row=word
   else:row=(row+' '+word).strip()
 header()
 for key,section in bundle['recommendation_directions'].items():
  line(section['label'],32,True)
  if not section['rows']:line('Пока нет готовых рекомендаций.'if section.get('status')=='unavailable'else'Пока без изменений.')
  for r in section['rows']:
   a=r.get('action')or{};cid=r.get('campaign_id');suffix=' · РК '+str(cid)if cid else''
   if key=='add':
    if r.get('bid_verified')is not True or type(r.get('target_minor'))is not int:continue
    decision='Добавить · ставка '+str(r['target_minor']/100)+' CNY'+suffix+'.'
   elif key=='exclude':decision='Исключить'+suffix+'.'
   else:decision=('Повысить'if key=='raise'else'Снизить')+' '+str(a['old_minor']/100)+' → '+str(a['target_minor']/100)+' CNY'+suffix+'.'
   line(r['article']+' — '+decision)
   if a and r.get('ready'):actions.append(a)
  y+=25
 finish();return files

