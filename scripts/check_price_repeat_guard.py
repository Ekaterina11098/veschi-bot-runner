from datetime import date
from types import SimpleNamespace
import copy
from china_price_review_guard import protected_repeats
state={'latest':{'data_available':True,'period_from':'2026-11-07','period_to':'2026-11-10','results':{'1':dict(article='A',action='raise',raise_kind='repeat',orders_stable=True,conversion_held=True,full_days=5,orders_each_day=[1,2,1,3])}},'price_history':{'1':{'price':{'current_cny':100,'target_cny':105}}}}
rows={'r':'Повышение · A Продавец: 100 → 105 ¥\nПокупатель: 1000 → 1050 ₽'}
def test(v):return protected_repeats(SimpleNamespace(day=date(2026,11,11),get=lambda k:v),rows)
assert test(state)=={'r'}
for field,value in [('conversion_held',False),('full_days',3),('orders_each_day',[1,0,1,3]),('action','observe')]:
 bad=copy.deepcopy(state);bad['latest']['results']['1'][field]=value;assert not test(bad)
bad=copy.deepcopy(state);bad['latest']['period_to']='2026-11-09';assert not test(bad)
bad=copy.deepcopy(state);bad['price_history']['1']['price']['current_cny']=99;assert not test(bad)
print('PASS: ready +5% repeat preserved; stale/incomplete/changed-price/unheld-conversion rejected')

