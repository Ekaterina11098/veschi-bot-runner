import copy,unittest
from datetime import datetime,timezone
from china_catalog_price_command import parse,resolve,handle,choose_percent,selection,ROOT
NOW=datetime(2026,10,28,18,20,tzinfo=timezone.utc)
FULL='Подними цены на 5% на все товары. И завтра скажешь где упали конверсии чтобы опустить цену'
NOEL='Артикулы в которых есть noelbag (разные цвета и виды одной сумки) подними цену не на 5% а на 10%'
EXCLUDE='Ты только не поднимай те что уже сегодня поднимали на 30% помнишь их да'
def job(i,t):return dict(id=i,sender_id=307200273,chat_id=-1004342917488,agent_id='china',request_text=t)
class W:
 def __init__(self):self.now=NOW;self.mem={};self.allowed=True
 def get(self,k):return copy.deepcopy(self.mem.get(k))
 def save(self,k,v,insert=False):
  if insert and k in self.mem:return False
  self.mem[k]=copy.deepcopy(v);return True
 def authorized(self,j):return self.allowed
class Tests(unittest.TestCase):
 def test_real_full_request(self):self.assertEqual(parse(FULL),dict(kind='catalog',percent='5'))
 def test_short(self):self.assertEqual(parse('Все товары +5%')['percent'],'5')
 def test_override(self):self.assertEqual(parse(NOEL),dict(kind='contains',fragment='noelbag',percent='10'))
 def test_exclusion(self):self.assertEqual(parse(EXCLUDE),dict(kind='exclude_earlier',percent='30'))
 def test_no_action_for_questions_negation_and_bids(self):
  for t in ['Не поднимай все цены на 5%','Можно поднять все цены на 5%','Может поднять все цены на 5%?','Если поднять все цены на 5%','Рассчитай повышение всех цен на 5%','Подними ставки всем товарам на 5%','Подними все рекламные бюджеты на 5%','Подними цены на 30% всем товарам без заказов']:
   with self.subTest(t=t):self.assertIsNone(parse(t))
 def test_followup_same_intent(self):self.assertEqual(resolve('Просто подними цену',[dict(request_text=FULL)])['percent'],'5')
 def test_followup_without_context(self):self.assertIsNone(resolve('Просто подними цену',[]))
 def test_non_stacking_pending_amendments(self):
  w=W();handle(w,job(166,FULL),[]);handle(w,job(171,NOEL),[]);handle(w,job(172,EXCLUDE),[])
  p=w.get(ROOT+'2026-10-28');rules=p['rules']
  self.assertEqual(choose_percent('529-NoelBag-lpink',rules),'10')
  self.assertEqual(choose_percent('154-ReginaBag-green',rules),'5')
  self.assertEqual(rules['exclude_verified_percent_today'],['30'])
  handle(w,job(169,'Все товары +5%'),[])
  self.assertEqual(w.get(ROOT+'2026-10-28'),p)
 def test_no_amendment_after_freeze(self):
  w=W();handle(w,job(166,FULL),[]);k=ROOT+'2026-10-28';w.mem[k]['status']='prepared';before=w.get(k)
  handle(w,job(171,NOEL),[]);self.assertEqual(w.get(k),before)
 def test_bound_done_confirmation_does_not_repeat(self):
  w=W();handle(w,job(166,FULL),[]);k=ROOT+'2026-10-28'
  w.mem[k].update(status='partial',verified_count=243,total_count=245,source_refs=[dict(job_id=172)])
  before=w.get(k);j=job(173,'Согласен. Делай');j['tool_trace']=[dict(name='china_saved_question',parent_job_id=172)]
  answer,trace=handle(w,j,[])
  self.assertIn('243',answer);self.assertTrue(trace[0]['duplicate_prevented']);self.assertEqual(w.get(k),before)
 def test_old_followup_cannot_create_next_day_price_write(self):
  w=W();w.now=datetime(2026,10,29,8,tzinfo=timezone.utc)
  answer,trace=handle(w,job(200,'Просто подними цену'),[dict(request_text=FULL)])
  self.assertFalse(w.mem);self.assertEqual(trace[0]['status'],'missing_current_plan')
 def test_bare_percent_without_price_context_cannot_change_prices(self):
  w=W();answer,trace=handle(w,job(10,'Все товары +5%'),[dict(request_text='Подними ставки всем товарам на 5%')])
  self.assertFalse(w.mem);self.assertEqual(trace[0]['status'],'ambiguous_price_scope')
 def test_permission(self):
  w=W();w.allowed=False;handle(w,job(166,FULL),[]);self.assertEqual(w.mem,{})
 def test_target_preserves_discounts(self):
  g=dict(nmID=1,vendorCode='Blue',currencyIsoCode4217='CNY',editableSizePrice=False,discount=30,clubDiscount=5,sizes=[dict(price=390,discountedPrice=273)])
  s=selection(g,'5');self.assertEqual(s['target_cny'],'287.0');self.assertEqual(s['seller_discount'],30);self.assertEqual(s['club_discount'],5)
  g['vendorCode']='Red-NoelBag';s=selection(g,'10');self.assertEqual(s['target_cny'],'300.3')
 def test_zero_and_rub_blocked(self):
  g=dict(nmID=1,vendorCode='Zero',currencyIsoCode4217='CNY',editableSizePrice=False,discount=0,clubDiscount=0,sizes=[dict(price=0,discountedPrice=0)])
  with self.assertRaises(ValueError):selection(g,'5')
  g['currencyIsoCode4217']='RUB'
  with self.assertRaises(ValueError):selection(g,'5')
if __name__=='__main__':unittest.main()
