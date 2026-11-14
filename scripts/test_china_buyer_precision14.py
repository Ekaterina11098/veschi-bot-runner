import unittest
from datetime import date
from china_buyer_price_forecast import build,forecast
class Precision(unittest.TestCase):
 def test_exact_buyer_prices_with_whole_percent_spp(self):
  data=[(1473244342,3698,3048),(1473244358,3561,2935),(1473243897,3101,2555),(1473243896,2839,2355),(1473243919,2839,2339)]
  rows=[dict(nm_id=n,sa_name=str(n),price_after_spp=b,price_final=b,price_after_discount=p,price_spp=17)for n,p,b in data]
  catalog=dict(cabinet='token_3',observed_at='2026-11-14T07:31:00+00:00',rows=[dict(nmID=n,vendorCode=str(n),currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=100)])for n,_,_ in data])
  marker=dict(id=22090,collected_at='2026-11-14T07:31:44+00:00',period_from='2026-11-13',period_to='2026-11-13')
  basis=build(rows,marker,catalog,date(2026,11,14));self.assertEqual(len(basis['rows']),5)
  self.assertEqual(forecast(basis,1473244342,str(1473244342),100,105,date(2026,11,14)),3200)
  rows[0]['price_final']=1;self.assertNotIn('1473244342',build(rows,marker,catalog,date(2026,11,14))['rows'])
  rows[1]['price_after_spp']=rows[1]['price_final']=2500;self.assertNotIn('1473244358',build(rows,marker,catalog,date(2026,11,14))['rows'])
if __name__=='__main__':unittest.main()
