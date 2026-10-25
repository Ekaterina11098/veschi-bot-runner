"""Read already validated exact-period MPStats product snapshots; no external collection."""
def saved_products(w,first,last,ids):
 found=w.db('GET','analytics_snapshots',params={'cabinet':'eq.token_3','source':'eq.mpstats_lk_wb_products','status':'eq.complete','period_from':'eq.'+str(first),'period_to':'eq.'+str(last),'select':'id,payload,collected_at','order':'collected_at.desc','limit':1}) or []
 if not found:return None
 snap=found[0];payload=snap.get('payload')
 observations=payload if isinstance(payload,list) else []
 for o in observations:
  args=o.get('arguments') or {}
  if o.get('tool')!='lk_wb_products' or o.get('status')!='received' or o.get('scope_verified') is not True:continue
  if args.get('date_from')!=str(first) or args.get('date_to')!=str(last):continue
  data=o.get('data',{}).get('data',{});rows=data.get('data')
  if not isinstance(rows,list) or data.get('need_update')!=0 or (data.get('pagination_complete') is not True and data.get('total')!=len(rows)):continue
  selected=[]
  for r in rows:
   if ids and int(r['nm_id']) not in ids:continue
   p={k:r.get(k) for k in ['nm_id','sa_name','finished_orders','is_payed','finish_as_return','not_finished_orders','orders_sum','orders_count','funnel_orders_count','open_card_count','add_to_cart_count','advertisement','price_after_discount','price_after_spp','sales_sum','returns_sum','rating','commentsvaluation']}
   p['buyout_pct']=100*p['is_payed']/p['finished_orders'] if p['finished_orders'] else None
   selected.append(p)
  return dict(source='saved validated MPStats exact-period products',snapshot_id=snap['id'],observed_at=snap['collected_at'],period_from=str(first),period_to=str(last),rows=selected,cached=True,wb_reads=0,mpstats_reads=0,note='Точный сохранённый период. Не смешивать общую воронку с рекламной; деньги исходного отчёта не складывать с CNY без подтверждённого курса. Неподтверждённые расходы не0.')
 return None

def ground_answer(text,trace):
 """Attach only identifiers and FX assumptions actually returned by verified tools."""
 for t in trace:
  result=t.get('result') or {}
  if t.get('name')=='get_saved_product_context' and len(result.get('rows',[]))==1:
   article=result['rows'][0].get('article')
   if article and article.casefold() not in text.casefold():text=article+':\n'+text
  if t.get('name')=='get_saved_profit_comparison':
   assumptions=result.get('assumptions') or {};fx=assumptions.get('fx_rub_per_cny')
   if fx is not None and not __import__('re').search(r'курс|₽/¥|RUB/CNY',text,__import__('re').I):
    text+='\nРасчётный курс '+str(fx)+' ₽/¥; налог '+str(assumptions.get('tax_pct'))+'% и обработка '+str(assumptions.get('handling_rub_per_order'))+' ₽ — допущения модели.'
 return text
