"""Offline regression of saved advertising diagnostics before midday."""
import copy,unittest
from datetime import datetime,timezone
from china_growth_saved import saved
class Work:
 now=datetime(2026,10,27,6,tzinfo=timezone.utc)
 def __init__(self,records):self.records=records
 def get(self,key):return self.records.get(key)
class SavedGrowthMorningTests(unittest.TestCase):
 def setUp(self):
  self.camp={'id':1,'status':9,'settings':{'placements':{'search':False}},'nm_settings':[{'nm_id':2,'bids_kopecks':{'recommendations':28}}]}
  stat={'advertId':1,'days':[{'date':'2026-10-26','apps':[{'nms':[{'nmId':2,'sum':3,'sum_price':100,'orders':1,'clicks':10}]}]}]}
  self.source={'status':'complete','observed_at':'2026-10-27T04:33:00+00:00','catalogue':{'rows':[{'nmID':2,'vendorCode':'test'}]},'batches':{'0':{'campaigns':{'adverts':[self.camp]},'stats':[stat]}}}
  self.records={'china_agent:advertising_source:2026-10-27:v2':self.source}
 def test_morning_used_without_midday_and_today_stays_unknown(self):
  r=saved(Work(self.records),'raise',3)
  self.assertEqual(len(r['rows']),1);self.assertEqual(r['rows'][0]['article'],'test')
  self.assertIsNone(r['rows'][0]['today']);self.assertIsNone(r['rows'][0]['today_drr'])
  self.assertEqual(r['wb_reads'],0);self.assertFalse(r['execution_ready'])
 def test_missing_timestamp_returns_specific_gap(self):
  r=saved(Work({'china_agent:verified_campaign_state:v1':{'1':'receipt'},'receipt':{'status':'verified','after':self.camp}}),'raise',3)
  self.assertEqual(r['rows'],[]);self.assertIn('дата',r['limitations'][0])
 def test_catalogue_list_is_supported(self):
  self.source['catalogue']=[{'nmID':2,'vendorCode':'list'}]
  self.assertEqual(saved(Work(self.records),'raise',3)['rows'][0]['article'],'list')
 def test_midday_preferred_to_morning(self):
  current=copy.deepcopy(self.source);current['observed_at']='2026-10-27T05:55:00+00:00'
  current['catalogue']['rows'][0]['vendorCode']='midday'
  self.records['china_agent:advertising_midday_source:2026-10-27:v2']=current
  self.assertEqual(saved(Work(self.records),'raise',3)['rows'][0]['article'],'midday')
if __name__=='__main__':unittest.main()
