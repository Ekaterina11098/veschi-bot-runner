"""Offline regression tests; no credentials, API calls or real delivery."""
import unittest,sys,copy,types,json,ast,time
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import china_table_png as png
class Store:
 def __init__(self):self.rows={}
 def get(self,k):return copy.deepcopy(self.rows.get(k))
 def save(self,k,v,insert=False):
  if insert and k in self.rows:return False
  self.rows[k]=copy.deepcopy(v);return True
 def once(self,k,v):assert k not in self.rows;self.save(k,v)
 def update(self,k,v,*a):self.save(k,v);return True
class Tests(unittest.TestCase):
 def test_boundary_and_cached_png(self):
  w=Store();j=dict(id=1,chat_id=-1,sender_id=307200273)
  self.assertEqual(png.delivery_parts(w,j,'я'*450,lambda x:[x]),['я'*450])
  j['id']=2;key='china_agent:reply_latency:v1:2';w.save(key,dict(context_prepare_ms=7))
  parts=png.delivery_parts(w,j,'я'*451,lambda x:[x])
  self.assertTrue(all(p.startswith(png.PREFIX)for p in parts));self.assertEqual(w.get(key)['context_prepare_ms'],7)
  original=png.render
  try:
   png.render=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Unexpected rerender'))
   self.assertEqual(png.delivery_parts(w,j,'я'*451,lambda x:[x]),parts)
  finally:png.render=original
  self.assertEqual(w.get(key)['additional_model_calls'],0)
 def test_other_sender_and_uncertain(self):
  w=Store();j=dict(id=3,chat_id=-1,sender_id=5122667182)
  self.assertEqual(png.delivery_parts(w,j,'я'*451,lambda x:[x]),['я'*451])
  j.update(id=4,sender_id=307200273);w.save('china_agent:conversion_watch_delivery:v1:codex_bridge:4:0',dict(status='uncertain'))
  with self.assertRaises(PermissionError):png.delivery_parts(w,j,'я'*451,lambda x:[x])
 def test_cloud_finish_timing_without_sdk(self):
  src=Path(png.__file__).with_name('china_codex_cloud.py').read_text(encoding='utf-8');tree=ast.parse(src)
  cls=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='Worker')
  selected=ast.ClassDef(name='Worker',bases=[],keywords=[],body=[n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name in ['finish','timing']],decorator_list=[])
  ns=dict(time=time,datetime=datetime,timezone=timezone,stamp=lambda:datetime.now(timezone.utc).isoformat(),ROOT='r:',CHAT=-1,THREAD='thread',envelope=json.loads)
  exec(compile(ast.fix_missing_locations(ast.Module(body=[selected],type_ignores=[])),'isolated_worker','exec'),ns)
  w=ns['Worker']();w.db=Store();w.db.save('in',dict(status='cloud_processing'));w.db.save('journal',dict(status='running'))
  inbox=dict(job_id=8,input_message_id=9,created_at=datetime.now(timezone.utc).isoformat())
  self.assertEqual(w.finish(inbox,'in',dict(text=json.dumps(dict(kind='answer',answer='Готово.'))),'journal'),'ready')
  lat=w.db.get('china_agent:reply_latency:v1:8');self.assertIn('response_parse_ms',lat);self.assertIn('queue_to_answer_ms',lat)
if __name__=='__main__':unittest.main()

