"""Merge separately read held-SKU facts without authorizing changes to those SKUs."""
import copy
def merge_held(v):
 held=v.get('held_evidence')or{}
 for family,key in [('prices','nm_id'),('stock','article')]:
  rows=v.get(family,{}).get('rows',[]);seen={str(r[key]).casefold()for r in rows}
  for r in held.get(family,{}).get('rows',[]):
   if str(r[key]).casefold()not in seen:rows.append(copy.deepcopy(r));seen.add(str(r[key]).casefold())
 pub=v.get('published_stock',{});hp=held.get('published_stock',{})
 for nm,amount in hp.get('amounts',{}).items():
  if nm not in pub.get('amounts',{}):
   pub.setdefault('amounts',{})[nm]=amount
 for nm,e in v.get('economics',{}).get('rows',{}).items():
  if nm in hp.get('amounts',{}) and e.get('published_stock')is None:
   e.update(published_stock=hp['amounts'][nm],published_stock_observed_at=hp['observed_at'])
 return v
