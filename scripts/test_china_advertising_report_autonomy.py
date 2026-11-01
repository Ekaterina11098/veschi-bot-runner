import copy,sys,types,unittest
from contextlib import nullcontext
from datetime import datetime,timezone
from unittest.mock import patch
from conversion_watches import Worker,PREFIX,RECEIPTS
import china_table_png as png

NOW=datetime.fromisoformat('2026-11-01T15:00:00+00:00')
TABLE='Реклама: срез18:00МСК;31Oct полный,1Nov неполный.\n\n| Артикул | Расходы31 | ДРР31 | Расходы1 | ДРР1 |\n|---|---:|---:|---:|---:|\n|143|617.60|14.84%|385.04|12.34%|'
def watch(wid='a'):
 return dict(id=wid,kind='once_task',agent_id='china',chat_id=-1004342917488,owner_user_id=5122667182,status='active',revision=1,next_at=NOW.isoformat(),initial_pending=False,clock='18:00',task_text='Таблица статистики',output_format='png_table')
class Runner(Worker):
 def __init__(self):
  self.now=NOW;self.data={PREFIX+'a':watch()};self.transport_calls=[];self.answer=TABLE
 def watches(self):return [(k,copy.deepcopy(v))for k,v in self.data.items()if k.startswith(PREFIX)]
 def authorized(self,v):return True
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def save(self,k,v,insert=False):
  if insert and k in self.data:return False
  self.data[k]=copy.deepcopy(v);return True
 def dialog(self,j,h):
  self.assert_scheduled=j
  if isinstance(self.answer,Exception):raise self.answer
  return self.answer,[]
 def transport(self,chat,text):
  image=png.photo(self,chat,text)
  self.transport_calls.append((chat,text,image))
  if self.uncertain:raise TimeoutError()
  return dict(ok=True,result=dict(chat=dict(id=chat),message_id=100+len(self.transport_calls)))
 uncertain=False

class AutonomyTests(unittest.TestCase):
 def setUp(self):
  self.guard=patch('conversion_watches.saved_network_guard',return_value=nullcontext());self.guard.start()
  self.renderer=patch.object(png,'render',return_value=[b'PNG']);self.renderer.start()
  self.binders=patch.dict(sys.modules,{'china_bid_proposals':types.SimpleNamespace(bind_photo=lambda *a:None),'china_ad_rule':types.SimpleNamespace(bind=lambda *a:None)});self.binders.start()
 def tearDown(self):self.binders.stop();self.renderer.stop();self.guard.stop()
 def test_native_due_to_png_receipt_completion_and_no_replay(self):
  r=Runner();self.assertEqual(r.reports(),1)
  images=[x for x in r.transport_calls if x[2]]
  self.assertEqual(len(images),1);self.assertEqual(images[0][2][0],b'PNG')
  state=r.data[PREFIX+'a'];self.assertEqual(state['status'],'completed');self.assertIsNone(state['next_at'])
  self.assertEqual(r.reports(),0)
  receipts=[v for k,v in r.data.items()if ':part:'in k];self.assertTrue(all(v['status']=='sent'and v['message_id']for v in receipts))
 def test_before_due_no_source_or_send(self):
  r=Runner();r.now=NOW.replace(hour=14);self.assertEqual(r.reports(),0);self.assertFalse(r.transport_calls)
 def test_bad_format_not_frozen_and_next_tick_recovers(self):
  r=Runner();r.answer='Обычный текст';self.assertEqual(r.reports(),0)
  self.assertNotIn(RECEIPTS+'report:a:2026-11-01',r.data)
  self.assertFalse(r.transport_calls)
  self.assertEqual(r.data['china_agent:scheduled_report_error:v1:a']['error_code'],'scheduled_png_table_required')
  r.answer=TABLE;self.assertEqual(r.reports(),1)
 def test_uncertain_does_not_retry(self):
  r=Runner();r.uncertain=True;self.assertEqual(r.reports(),0)
  self.assertEqual(r.data[PREFIX+'a']['status'],'delivery_uncertain')
  n=len(r.transport_calls);self.assertEqual(r.reports(),0);self.assertEqual(len(r.transport_calls),n)
 def test_failure_of_one_report_does_not_block_another(self):
  r=Runner();r.data[PREFIX+'b']=watch('b')
  original=r.dialog
  def dialog(j,h):
   if r.active_test_id=='a':raise ValueError('Source failed')
   return original(j,h)
  r.dialog=dialog;deliver=r.deliver_report
  def selected(k,w):r.active_test_id=w['id'];return deliver(k,w)
  r.deliver_report=selected
  self.assertEqual(r.reports(),1);self.assertEqual(r.data[PREFIX+'a']['status'],'active');self.assertEqual(r.data[PREFIX+'b']['status'],'completed')
 def test_delayed_after_midnight_keeps_original_receipt_identity(self):
  r=Runner();r.now=NOW.replace(day=2,hour=1);self.assertEqual(r.reports(),1)
  self.assertIn(RECEIPTS+'report:a:2026-11-01',r.data)
  self.assertNotIn(RECEIPTS+'report:a:2026-11-02',r.data)

class ReadOnlyGuardTests(unittest.TestCase):
 def test_scheduled_transport_blocks_wb_mutations(self):
  import os
  from conversion_watches import saved_network_guard
  class Session:
   def request(self,method,url,*args,**kwargs):return 'allowed'
  requests=types.SimpleNamespace(sessions=types.SimpleNamespace(Session=Session))
  modules={'requests':requests}
  for name in ['china_search_analytics','china_ad_cost_collect','china_ad_rule','china_analytic_dialog']:
   modules[name]=types.SimpleNamespace(allowed_read=lambda *a:False)
  with patch.dict(sys.modules,modules),patch.dict(os.environ,{'SUPABASE_URL':'https://example.supabase.co','CHINA_TELEGRAM_BOT_TOKEN':'test'}):
   with saved_network_guard():
    session=Session()
    self.assertEqual(session.request('GET','https://example.supabase.co/rest/v1/telegram_api_cache'),'allowed')
    for method,url in [('POST','https://advert-api.wildberries.ru/adv/v0/bids'),('PATCH','https://discounts-prices-api.wildberries.ru/api/v2/upload/task'),('POST','https://api.telegram.org/bottest/deleteMessage')]:
     with self.assertRaises(PermissionError):session.request(method,url)

if __name__=='__main__':unittest.main()
