import asyncio,json,sys,tempfile,unittest
from china_codex_appserver import Client,RPC_STREAM_LIMIT

class LargePacket(unittest.IsolatedAsyncioTestCase):
 async def test_large_utf8_final_event_does_not_drop_turn(self):
  stream=asyncio.StreamReader(limit=RPC_STREAM_LIMIT)
  for event in [{'method':'item/completed','params':{'item':{'type':'agentMessage','phase':'final_answer','text':'я'*80000}}},{'method':'turn/completed','params':{'turn':{'status':'completed'}}}]:
   stream.feed_data((json.dumps(event,ensure_ascii=False)+'\n').encode())
  stream.feed_eof()
  p=__import__('types').SimpleNamespace(stdout=stream)
  with tempfile.TemporaryDirectory() as home:
   client=Client(lambda *a:None,home,'offline');client.proc=p;client.finished=asyncio.get_running_loop().create_future()
   await asyncio.wait_for(client.read(),5)
   self.assertEqual(client.finished.result()['status'],'completed')
   self.assertEqual(client.final,['я'*80000])
if __name__=='__main__':unittest.main()
