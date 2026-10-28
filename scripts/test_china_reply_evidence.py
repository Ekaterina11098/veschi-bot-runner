import copy,unittest
from datetime import datetime,timezone,timedelta
from china_reply_evidence import ROOT,DELIVERY,status_answer,reconcile
from china_catalog_price_command import handle
NOW=datetime(2026,10,28,19,tzinfo=timezone.utc);KEY=ROOT+'2026-10-28'
def job(text='Согласен. Делай',i=4,parent=3):
 return dict(id=i,request_text=text,tool_trace=[dict(name='china_saved_question',parent_job_id=parent)])
def fixture():
 selections=[dict(nm_id=str(i),article='test-'+str(i),target_cny='110',seller_discount=0,club_discount=0) for i in [1,2]]
 items=[dict(status='applied',selection=s,request=dict(nmID=int(s['nm_id']),price=110,discount=0),readback=dict(nmID=int(s['nm_id']),vendorCode=s['article'],currencyIsoCode4217='CNY',discount=0,clubDiscount=0,sizes=[dict(price=110,discountedPrice=110)])) for s in selections]
 p=dict(status='partial',day='2026-10-28',job_id=1,source_refs=[dict(job_id=1),dict(job_id=3)],rules=dict(default_percent='5',overrides=[dict(fragment='noelbag',percent='10')],exclude_verified_percent_today=['30']),verified_count=2,total_count=3,selections=selections,executions=['exec'],batch_approvals=[dict(key='approval')])
 return {KEY:p,'exec':dict(status='done',approval_key='approval',items=items)}
class W:
 now=NOW
 def __init__(self):self.mem=fixture();self.reads=[]
 def get(self,k):self.reads.append(k);return copy.deepcopy(self.mem.get(k))
 def db(self,*a,**k):return []
 def authorized(self,j):raise AssertionError('Status must never authorize a write')
 def save(self,*a,**k):raise AssertionError('Status must not write')
class Tests(unittest.TestCase):
 def test_stale_prepared_no_tool_answer_is_replaced_without_actions(self):
  w=W();before=copy.deepcopy(w.mem);a,t=reconcile(w,job(),[],'Нет инструмента. Не выполнено.',[])
  self.assertIn('WB подтвердил 2 из 3',a);self.assertIn('Да, частично.',a);self.assertTrue(t[-1]['prepared_answer_replaced']);self.assertEqual(w.mem,before)
 def test_sent_uncertain_sending_ready_and_rejected_receipt_identity_preserved(self):
  for state in ['sent','uncertain','sending','ready','rejected']:
   with self.subTest(state=state):
    w=W();w.mem[DELIVERY+'question:4:0']=dict(status=state)
    self.assertEqual(reconcile(w,job(),[],'old',[]),('old',[]))
 def test_root_success_without_child_receipt_is_not_success(self):
  w=W();w.mem.pop('exec');a,t=reconcile(w,job(),[],'Готово всё',[])
  self.assertIn('Выполнение не подтверждено',a);self.assertEqual(t[-1]['wb_verified'],0)
 def test_green_batch_without_readback_is_not_success(self):
  w=W();w.mem['exec']['items'][0].pop('readback');a,t=reconcile(w,job(),[],'готово',[])
  self.assertIn('WB подтвердил 1 из 3',a);self.assertTrue(t[-1]['receipt_mismatch'])
 def test_wrong_currency_price_sku_or_discount_cannot_count(self):
  for field,value in [('currencyIsoCode4217','RUB'),('vendorCode','other'),('nmID',99),('discount',5),('clubDiscount',7)]:
   w=W();w.mem['exec']['items'][0]['readback'][field]=value
   self.assertEqual(reconcile(w,job(),[],'old',[])[1][-1]['wb_verified'],1)
  w=W();w.mem['exec']['items'][0]['readback']['sizes'][0]['discountedPrice']=109
  self.assertEqual(reconcile(w,job(),[],'old',[])[1][-1]['wb_verified'],1)
 def test_foreign_approval_cannot_be_reused(self):
  w=W();w.mem['exec']['approval_key']='foreign'
  self.assertEqual(reconcile(w,job(),[],'old',[])[1][-1]['wb_verified'],0)
 def test_duplicate_receipt_does_not_double_count(self):
  w=W();w.mem[KEY]['executions'].append('exec')
  self.assertEqual(reconcile(w,job(),[],'old',[])[1][-1]['wb_verified'],2)
 def test_pending_without_readback_does_not_claim_done(self):
  w=W();w.mem[KEY].update(status='requested',verified_count=0,executions=[])
  a,t=reconcile(w,job(),[],'Всё поднял',[])
  self.assertIn('Зарегистрирован',a);self.assertNotIn('Да.',a);self.assertEqual(t[-1]['wb_verified'],0)
 def test_clarification_follows_catalog_context_instead_of_old_cohort(self):
  w=W();a,t=handle(w,job('Что значит проверено?',5,None),[dict(id=4,request_text='x',tool_trace=[dict(name='catalog_price_status',command_key=KEY)])])
  self.assertIn('WB подтвердил 2 из 3',a);self.assertIn('совпавшую с точной целевой',a)
 def test_yes_no_answer_starts_directly(self):
  a,t=status_answer(W(),job('Ответь да или нет',5),[])
  self.assertTrue(a.startswith('Да, частично.'))
 def test_explicit_historical_30_percent_not_substituted_by_current_5_10(self):
  self.assertIsNone(handle(W(),job('Ты поднял цены на 30%?',5,None),[]))
 def test_explicit_new_percent_is_not_trapped_by_old_cohort_history(self):
  h=[dict(id=2,tool_trace=[dict(name='zero_order_price_status',command_key='older')])]
  a,t=handle(W(),job('Ты поднял цены на 5%?',5,None),h)
  self.assertIn('WB подтвердил 2 из 3',a)
 def test_reply_to_old_cohort_outranks_current_catalog_recency(self):
  h=[dict(id=2,tool_trace=[dict(name='zero_order_price_status',command_key='older')])]
  self.assertIsNone(handle(W(),job('Ты цены поднял?',5,2),h))
 def test_unrelated_or_ambiguous_questions_not_hijacked(self):
  for text in ['Спасибо','Как дела?','Сколько корзин сегодня?','Ответь да или нет']:
   j=job(text,9,None);self.assertEqual(reconcile(W(),j,[],'normal',[]),('normal',[]))
 def test_missing_job_id_does_not_bind_none_parent(self):
  w=W();w.mem[KEY].pop('job_id')
  self.assertEqual(reconcile(w,job('Спасибо',9,None),[],'normal',[]),('normal',[]))
 def test_previous_day_exact_reply_key_can_be_read_without_execution(self):
  w=W();w.now=NOW+timedelta(days=1);j=job('Ты цены поднял?',6)
  a,t=reconcile(w,j,[dict(id=3,tool_trace=[dict(name='catalog_price_status',command_key=KEY)])],'old',[])
  self.assertIn('WB подтвердил 2 из 3',a);self.assertEqual(t[-1]['command_key'],KEY)
 def test_nested_replay_cache_is_not_a_catalog_plan(self):
  w=W();w.mem={}
  w.db=lambda *a,**k:[dict(cache_key=KEY+':route_replay',payload=dict(status='verified'))]
  self.assertIsNone(status_answer(w,job('Ты цены поднял?',6,None),[]))
if __name__=='__main__':unittest.main()
