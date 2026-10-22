import copy,unittest
from datetime import datetime,timezone
from china_loss_control import *
from china_loss_policy import evaluate
class Memory:
 def __init__(self,p):self.state={PLAN+'test':p,LATEST:dict(plan_id='test')};self.now=datetime.now(timezone.utc);self.writes=0
 def get(self,k):return copy.deepcopy(self.state.get(k))
 def save(self,k,v,insert=False):
  if insert and k in self.state:return False
  self.state[k]=copy.deepcopy(v);return True
 def create(self,k,v):return self.save(k,v,True)
 def put(self,k,v):self.save(k,v)
 def validate_owner(self,a):pass
 def card(self,nm):return copy.deepcopy(self.current)
 def update_card(self,c):self.writes+=1;self.current.update(c)
def plan():
 items=[dict(id='color',article='test',nm_id=1,kind='card_text_replace',replacements=[['красный','синий']]),dict(id='measure',article='model',nm_id=2,kind='needs_data',question='Нужен обхват горловины, см.')]
 return dict(chat_id=CHAT,bot_id=BOT,plan_sha256=digest(items),items=items,report_message_ids=[102],created_at='2026-10-22T00:00:00+00:00',expires_at='2026-10-24T00:00:00+00:00')
def job():return dict(id=66,update_id=123,request_text='сделай все',sender_id=OWNER,chat_id=CHAT,created_at='2026-10-22T11:14:43+00:00',tool_trace=[dict(name='china_saved_question',reply_message_id=102,bot_id=BOT,message_id=103)])
class Tests(unittest.TestCase):
 def test_reply_without_text_is_bound_to_document(self):
  m=Memory(plan());answer,trace=handle(m,job());self.assertIn('Команда принята',answer);self.assertEqual(m.get(APPROVAL+'66')['plan_id'],'test')
 def test_wrong_reply_never_uses_prior119(self):
  m=Memory(plan());j=job();j['tool_trace'][0]['reply_message_id']=99;answer,_=handle(m,j);self.assertIn('именно',answer);self.assertIsNone(m.get(APPROVAL+'66'))
 def test_nonowner_cannot_execute(self):
  m=Memory(plan());j=job();j['sender_id']=4;handle(m,j);self.assertIsNone(m.get(APPROVAL+'66'))
 def test_question_not_authorization(self):
  m=Memory(plan());j=job();j['request_text']='Можно сделать всё?';self.assertIsNone(handle(m,j));self.assertIsNone(m.get(APPROVAL+'66'))
 def test_repeated_command_no_duplicate_writes_and_partial_progress(self):
  m=Memory(plan());m.current=dict(nmID=1,vendorCode='test',title='x',brand='',description='красный цвет',sizes=[dict(chrtID=1,skus=['a'])],dimensions=dict(length=1,width=2,height=3,weightBrutto=.4),characteristics=[dict(id=4,value=['x'])]);handle(m,job());a=m.get(APPROVAL+'66');one=process(m,a);two=process(m,a)
  self.assertEqual(m.writes,1);self.assertEqual(one,two);self.assertEqual(one['items'][1]['status'],'needs_data');self.assertEqual(one['items'][0]['status'],'verified');self.assertEqual(m.current['sizes'][0]['skus'],['a'])
 def test_unknown_zero_not_adopted(self):
  r=dict(cabinet='token_3',currency='RUB',source_ids=[1],period_from='2026-10-01',period_to='2026-10-02',orders=3,finished=2,kept=0,expense_ids=[],advertising_rub=None)
  with self.assertRaises(ValueError):evaluate(r)
 def test_total_and_zero_buyout(self):
  r=dict(cabinet='token_3',currency='RUB',source_ids=[1],period_from='2026-10-01',period_to='2026-10-02',orders=3,finished=2,kept=0,expense_ids=['a'],advertising_rub=10,orders_sum_rub=300,seller_revenue_rub=100,commission_fraction=.2,own_cogs_rub=30,tax_per_kept_rub=0,other_per_kept_rub=0,logistics_per_order_rub=5,other_per_order_rub=0,shared_confirmed_rub=0,all_expenses_confirmed=True)
  got=evaluate(r);self.assertEqual(got['buyout_percent'],0);self.assertEqual(got['expected_total_profit_rub'],-25);r['expense_ids']=['a','a']
  with self.assertRaises(ValueError):evaluate(r)
 def test_changed_description_blocks_only_item(self):
  c=dict(nmID=1,vendorCode='test',description='другой цвет')
  with self.assertRaises(ValueError):build_card_update(c,plan()['items'][0])
if __name__=='__main__':unittest.main()
