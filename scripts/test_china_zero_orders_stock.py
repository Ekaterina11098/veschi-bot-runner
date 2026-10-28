import unittest,copy
from datetime import datetime,timezone,timedelta
from china_zero_orders_stock import attach
class T(unittest.TestCase):
 def base(self):return dict(zero=[dict(article=x,orders=0) for x in ['a','b','c','d']],unknown=[dict(article='e',orders=None)])
 def source(self):return dict(complete=True,observed_at=datetime.now(timezone.utc).isoformat(),rows=[dict(article='a',stock=10,reserve=2),dict(article='b',stock=0,reserve=0),dict(article='c',stock=4,reserve=4)])
 def test_split(self):
  p=attach(self.base(),self.source());self.assertEqual(p['stock_counts'],dict(available=1,empty=1,reserved=1,unknown=1));self.assertEqual(p['zero'][0]['moysklad']['available'],8);self.assertEqual(len(p['unknown']),1)
 def test_missing_reserve_unknown(self):
  s=self.source();s['rows'][0].pop('reserve');self.assertEqual(attach(self.base(),s)['zero'][0]['moysklad']['group'],'unknown')
 def test_duplicates_unknown(self):
  s=self.source();s['rows'].append(s['rows'][0]);self.assertEqual(attach(self.base(),s)['zero'][0]['moysklad']['group'],'unknown')
 def test_stale_unknown(self):
  s=self.source();s['observed_at']=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat();self.assertEqual(attach(self.base(),s)['stock_counts']['unknown'],4)
 def test_partial_unknown(self):
  s=self.source();s['complete']=False;self.assertEqual(attach(self.base(),s)['stock_counts']['unknown'],4)
if __name__=='__main__':unittest.main()

