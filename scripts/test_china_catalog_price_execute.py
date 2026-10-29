from china_catalog_price_execute import catalogue_snapshot
import copy,unittest
from unittest.mock import patch
from china_catalog_price_execute import verified_prior,CatalogIO
class HistoryIO:
 def __init__(self,rows):self.rows=rows
 def db(self,path):return self.rows
 def get(self,k):
  if k=='a':return dict(basis='explicit_zero_order_percent',report_job_id=155)
  if k.endswith(':155'):return dict(percent='30')
  return None
def receipt(status='applied',target='130'):
 return dict(cache_key='receipt',payload=dict(status='done',approval_key='a',completed_at='2026-10-28T06:38:05+00:00',items=[dict(status=status,selection=dict(nm_id='1',article='A',target_cny='130'),readback=dict(currencyIsoCode4217='CNY',vendorCode='A',sizes=[dict(discountedPrice=target)]))]))
class Tests(unittest.TestCase):
 def test_exclude_only_wb_verified_30(self):
  io=HistoryIO([receipt(),dict(cache_key='other',payload=dict(status='done',approval_key='a',completed_at='2026-10-28T06:38:05+00:00',items=[dict(status='failed',selection=dict(nm_id='2',article='B',target_cny='130'))]))])
  got=verified_prior(io,dict(day='2026-10-28',rules=dict(exclude_verified_percent_today=['30'])))
  self.assertEqual(set(got),{'1'})
 def test_not_excluding_unverified_claim(self):
  with self.assertRaises(ValueError):verified_prior(HistoryIO([receipt(target='100')]),dict(day='2026-10-28',rules=dict(exclude_verified_percent_today=['30'])))
 def test_writes_are_scoped_and_no_messages(self):
  io=object.__new__(CatalogIO);io.write_selections={'1':dict(target_cny='105',seller_discount=0)}
  good=dict(data=[dict(nmID=1,price=105,discount=0)])
  with patch('china_price_apply.IO.wb',return_value={}) as transport:
   io.wb('/api/v2/upload/task','POST',good);self.assertEqual(transport.call_count,1)
   invalid=[]
   for field,value in [('nmID',2),('price',110),('discount',10)]:
    b=copy.deepcopy(good);b['data'][0][field]=value;invalid.append(b)
   b=copy.deepcopy(good);b['data'].append(copy.deepcopy(b['data'][0]));invalid.append(b)
   for body in invalid:
    with self.assertRaises(ValueError):io.wb('/api/v2/upload/task','POST',body)
   with self.assertRaises(ValueError):io.wb('/api/v2/upload/task/size','POST',good)
   with self.assertRaises(ValueError):io.tg('sendMessage',dict(text='test'))
   self.assertEqual(transport.call_count,1)
if __name__=='__main__':unittest.main()

class PriceSnapshotContractTests(unittest.TestCase):
 def test_catalog_writer_preserves_cabinet_required_by_daily_reader(self):
  row=dict(nmID=100,vendorCode='test-bag',currencyIsoCode4217='CNY',sizes=[])
  snap=catalogue_snapshot({'100':row},'execution')
  self.assertEqual(snap['cabinet'],'token_3');self.assertEqual(snap['rows'],[row]);self.assertEqual(snap['execution_key'],'execution')
 def test_wrong_currency_never_labeled_as_china(self):
  for rows in [{}, {'1':dict(nmID=1,vendorCode='A',currencyIsoCode4217='RUB')},{'1':dict(nmID=1,currencyIsoCode4217='CNY')}]:
   with self.assertRaises(ValueError):catalogue_snapshot(rows,'e')
 def test_duplicate_cards_rejected(self):
  row=dict(nmID=1,vendorCode='A',currencyIsoCode4217='CNY')
  with self.assertRaises(ValueError):catalogue_snapshot({'a':row,'b':row},'e')
