import unittest,tempfile,json,os
from pathlib import Path
from unittest.mock import patch
import requests
import egress_meter
class MeterTests(unittest.TestCase):
    def test_meter_preserves_response_and_counts_only_supabase_without_query_values(self):
        response=type('Response',(),{'content':b'12345','headers':{'Content-Length':'3'}})()
        callbacks=[]
        original=requests.sessions.Session.request
        try:
            with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'SUPABASE_URL':'https://example.supabase.co'}),patch.object(requests.sessions.Session,'request',return_value=response),patch.object(egress_meter.atexit,'register',side_effect=callbacks.append):
                stats=egress_meter.install(str(Path(tmp)/'m.json'))
                session=requests.Session()
                self.assertIs(session.request('GET','https://example.supabase.co/rest/v1/x?apikey=secret'),response)
                self.assertIs(session.request('GET','https://api.telegram.org/test'),response)
                self.assertEqual(stats['calls'],1);self.assertEqual(stats['wire_response_bytes'],3)
                self.assertEqual(stats['response_body_bytes'],5)
                self.assertEqual(list(stats['by_path']),['/rest/v1/x'])
                callbacks[0]()
                self.assertNotIn('secret',(Path(tmp)/'m.json').read_text())
        finally:requests.sessions.Session.request=original
    def test_zero_traffic_does_not_write_anywhere(self):
        with patch('requests.post') as post:
            egress_meter.persist({'calls':0},'test')
            post.assert_not_called()
