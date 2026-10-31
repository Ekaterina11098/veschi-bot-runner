import copy,unittest
from datetime import datetime,timezone
from china_once_report import prepare,requested
from conversion_watches import Worker,intent
NOW=datetime.fromisoformat('2026-10-31T18:35:00+00:00')
class W:
 def __init__(self):self.now=NOW;self.data={}
 def config(self):return dict(chat_id=-1004342917488,owner_user_id=5122667182)
 def authorized(self,obj):return obj.get('chat_id')==-1004342917488
 def catalog(self):return [('1473243911','59-NoelBag-grey'),('1473245494','143-ReginaBag-black'),('1473245495','144-SamiraBag-brown'),('1473245508','587-ReginaBag-orange')]
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def save(self,k,v,insert=False):
  if insert and k in self.data:return False
  self.data[k]=copy.deepcopy(v);return True
 def db(self,*a,**kw):return [dict(id=204,request_text='завтра по этим артикулам',answer=None),dict(id=201,request_text='Дай таблицу',answer='59-NoelBag-grey 143-ReginaBag-black 144-SamiraBag-brown 587-ReginaBag-orange')]
def job():return dict(id=205,agent_id='china',chat_id=-1004342917488,sender_id=307200273,created_at='2026-10-31T18:28:07.14648+00:00',request_text='Сам без напоминаний завтра дай статистику около 18.00 по этим артикулам за сегодня и неполный завтра день')
class OnceTests(unittest.TestCase):
 def test_exact_pavel_instruction_creates_once_not_daily_or_immediate(self):
  w=W();text=prepare(w,job());saved=next(iter(w.data.values()))
  self.assertEqual(intent(job()['request_text']),'create_once')
  self.assertEqual(saved['next_at'],'2026-11-01T15:00:00+00:00');self.assertFalse(saved['initial_pending'])
  self.assertEqual(saved['kind'],'once_task');self.assertEqual(len(saved['nm_ids']),4);self.assertEqual(saved['scope_job_id'],201)
  self.assertIn('2026-10-31',saved['task_text']);self.assertIn('2026-11-01',saved['task_text']);self.assertIn('разовый',text)
 def test_same_saved_job_does_not_duplicate(self):
  w=W();a=prepare(w,job());self.assertEqual(prepare(w,job()),a);self.assertEqual(len(w.data),1)
 def test_relative_date_anchored_to_message_not_delayed_worker(self):
  w=W();w.now=datetime.fromisoformat('2026-11-01T10:00:00+00:00');prepare(w,job())
  self.assertEqual(next(iter(w.data.values()))['next_at'],'2026-11-01T15:00:00+00:00')
 def test_unknown_scope_not_invented(self):
  w=W();w.db=lambda *a,**kw:[]
  with self.assertRaises(ValueError):prepare(w,job())
 def test_after_due_not_silently_moved_to_day_after(self):
  w=W();w.now=datetime.fromisoformat('2026-11-01T16:00:00+00:00')
  with self.assertRaises(ValueError):prepare(w,job())
 def test_scheduled_text_cannot_schedule_again(self):
  w=W();j=dict(job(),origin='scheduled');self.assertIsNone(prepare(w,j));self.assertFalse(w.data)
 def test_worker_executes_once_at_due_and_terminal_after_receipt(self):
  owner=W();prepare(owner,job());key=next(iter(owner.data));watch=owner.data[key]
  class Runner(Worker):
   def __init__(self):self.now=NOW;self.data=copy.deepcopy(owner.data);self.sent=[]
   def watches(self):return [(key,self.data[key])]
   def get(self,k):return copy.deepcopy(self.data.get(k))
   def save(self,k,v,insert=False):self.data[k]=copy.deepcopy(v);return True
   def authorized(self,obj):return True
   def dialog(self,j,h):self.sent.append(('generate',j));return 'Статистика за31Oct и1Nov до18MSK',[]
   def send_once(self,k,chat,text):self.sent.append(('deliver',k));return 'sent'
  r=Runner();self.assertEqual(r.reports(),0);self.assertFalse(r.sent)
  r.now=datetime.fromisoformat('2026-11-01T15:00:00+00:00');self.assertEqual(r.reports(),1)
  self.assertEqual(r.data[key]['status'],'completed');self.assertEqual(r.reports(),0);self.assertEqual(len([x for x in r.sent if x[0]=='deliver']),1)
if __name__=='__main__':unittest.main()
