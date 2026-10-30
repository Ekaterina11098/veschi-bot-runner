import unittest
from unittest.mock import patch
import fbs_document_chain as m

class SequenceTransport(m.Transport):
 def __init__(self,values):
  super().__init__();self.values=iter(values);self.calls=[]
 def _request_once(self,base,path,method="GET",body=None,params=None):
  self.calls.append(method)
  value=next(self.values)
  if isinstance(value,Exception):raise value
  return value

class RetryTests(unittest.TestCase):
 @patch.object(m.time,"sleep")
 def test_get_recovers_twice(self,sleep):
  t=SequenceTransport([m.Stop("HTTP_503 GET entity/customerorder"),m.Stop("HTTP_502 GET entity/customerorder"),{"rows":[]}])
  self.assertEqual(t.request(m.MS,"entity/customerorder"),{"rows":[]})
  self.assertEqual(t.calls,["GET"]*3)
  self.assertEqual([x.args[0] for x in sleep.call_args_list],[2,4])
 @patch.object(m.time,"sleep")
 def test_post_is_never_replayed(self,sleep):
  t=SequenceTransport([m.Stop("HTTP_503 POST entity/customerorder")])
  with self.assertRaises(m.Stop):t.request(m.MS,"entity/customerorder","POST",{})
  self.assertEqual(t.calls,["POST"]);sleep.assert_not_called()
 @patch.object(m.time,"sleep")
 def test_permanent_failure_is_not_retried(self,sleep):
  t=SequenceTransport([m.Stop("HTTP_401 GET entity/customerorder")])
  with self.assertRaises(m.Stop):t.request(m.MS,"entity/customerorder")
  self.assertEqual(t.calls,["GET"]);sleep.assert_not_called()
 @patch.object(m.time,"sleep")
 def test_retry_limit(self,sleep):
  t=SequenceTransport([m.Stop("HTTP_503 GET entity/customerorder")]*3)
  with self.assertRaises(m.Stop):t.request(m.MS,"entity/customerorder")
  self.assertEqual(t.calls,["GET"]*3);self.assertEqual(sleep.call_count,2)
 @patch.object(m.time,"sleep")
 def test_uncertain_read_recovers(self,sleep):
  t=SequenceTransport([m.Stop("API transport outcome uncertain"),{"ok":True}])
  self.assertTrue(t.request(m.MS,"entity/customerorder")["ok"])
  self.assertEqual(t.calls,["GET"]*2)
 def test_uncertain_creation_is_reconciled_without_second_post(self):
  created={"id":"existing-id","name":"supply","meta":{"href":m.MS+"entity/customerorder/existing-id","type":"customerorder","mediaType":"application/json"}}
  class Cache:
   def put(self,key,value):pass
  class CreationTransport:
   def __init__(self):self.posts=0
   def request(self,*args):
    self.posts+=1
    raise m.Stop("HTTP_503 POST entity/customerorder")
  t=CreationTransport();w=m.Worker(t,Cache(),{});state={"supply":{"id":"supply"}}
  answers=iter([[],[]]);w.ms_rows=lambda *args:next(answers);w.verify=lambda *args:None
  with self.assertRaises(m.Stop):w.ensure("customerorder",{},state,"key")
  self.assertEqual(state["inflight"],"customerorder")
  w.ms_rows=lambda *args:[created]
  self.assertEqual(w.ensure("customerorder",{},state,"key"),m.meta(created))
  self.assertEqual(t.posts,1);self.assertNotIn("inflight",state)
 def test_unconfirmed_creation_stays_blocked(self):
  class Cache:
   def put(self,*args):pass
  t=SequenceTransport([]);w=m.Worker(t,Cache(),{});w.ms_rows=lambda *args:[]
  state={"supply":{"id":"supply"},"inflight":"customerorder"}
  with self.assertRaisesRegex(m.Stop,"Uncertain prior"):w.ensure("customerorder",{},state,"key")
  self.assertEqual(t.calls,[])
class RejectedCreationTests(unittest.TestCase):
 def test_validation_rejection_does_not_leave_uncertain_marker(self):
  class Cache:
   def put(self,*args):pass
  t=SequenceTransport([m.Stop("HTTP_412 POST entity/demand")])
  w=m.Worker(t,Cache(),{});w.ms_rows=lambda *args:[]
  state={"supply":{"id":"supply"}}
  with self.assertRaises(m.Stop):w.ensure("demand",{},state,"key")
  self.assertNotIn("inflight",state)
  self.assertEqual(state["status"],"demand_rejected")
  self.assertEqual(t.calls,["POST"])
 def test_server_failure_keeps_uncertain_marker(self):
  class Cache:
   def put(self,*args):pass
  t=SequenceTransport([m.Stop("HTTP_503 POST entity/demand")])
  w=m.Worker(t,Cache(),{});w.ms_rows=lambda *args:[]
  state={"supply":{"id":"supply"}}
  with self.assertRaises(m.Stop):w.ensure("demand",{},state,"key")
  self.assertEqual(state["inflight"],"demand")
  self.assertEqual(t.calls,["POST"])
if __name__=="__main__":unittest.main()

