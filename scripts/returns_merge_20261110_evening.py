"""Merge duplicate assortment identities in the single owner-authorized move."""
import collections
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
ROOT="returns_transfer:china:20261110:evening:merge:"
ident="e0202fc6-dd0b-11f1-0a80-1ef6002f52e0"
path="entity/move/"+ident
r={"status":"reading","write_attempted":False,"at":m.now()}
def save():db.put(ROOT+"result:v1",r)
def totals(ps):
 out=collections.Counter()
 for p in ps:out[m.href(p["assortment"])]+=p["quantity"]
 return out
def validate(d,ps):
 assert d["name"]=="00277" and not d.get("deleted") and d.get("applicable") is True
 assert d.get("description")=="Возвраты ВБ Китай 10 11 26 вечер"
 assert m.href(d["sourceStore"]).endswith("/c599b096-a784-11f1-0a80-15f1000f8193")
 assert m.href(d["targetStore"]).endswith("/3c67619d-f25d-11ee-0a80-0c6f000a027a")
 assert sum(p["quantity"] for p in ps)==156 and d.get("sum")==0
 assert all(p.get("price")==0 and p["quantity"]>0 for p in ps)
try:
 live=t.request(m.MS,path);before=w.ms_rows(path+"/positions");validate(live,before)
 expected=totals(before)
 grouped={}
 for p in before:
  href=m.href(p["assortment"])
  if href not in grouped:grouped[href]={"assortment":m.meta(p["assortment"]),"quantity":0,"price":0,"discount":p.get("discount",0),"vat":p.get("vat",0),"vatEnabled":p.get("vatEnabled",False)}
  assert p.get("discount",0)==grouped[href]["discount"] and p.get("vat",0)==grouped[href]["vat"] and p.get("vatEnabled",False)==grouped[href]["vatEnabled"],"Duplicate attributes differ"
  grouped[href]["quantity"]+=p["quantity"]
 counts=collections.Counter(m.href(p["assortment"]) for p in before)
 duplicates=[]
 for href,count in counts.items():
  if count>1:
   product=t.request(m.MS,href[len(m.MS):])
   duplicates.append({"id":product["id"],"code":product.get("code"),"article":product.get("article"),"name":product["name"],"rows":count,"quantity":expected[href]})
 r.update(duplicates=duplicates,before_positions=len(before),expected_positions=len(grouped),id=ident,name=live["name"])
 if len(before)>len(grouped):
  assert db.claim(ROOT+"claim:v1",{"id":ident,"at":m.now()}),"Prior merge claim exists; readback/reconciliation required"
  db.put(ROOT+"intent:v1",{"id":ident,"document":live,"positions":before,"replacement":list(grouped.values()),"at":m.now()})
  fresh=t.request(m.MS,path);freshps=w.ms_rows(path+"/positions")
  assert fresh.get("updated")==live.get("updated") and [(m.href(p["assortment"]),p["quantity"],p.get("price")) for p in freshps]==[(m.href(p["assortment"]),p["quantity"],p.get("price")) for p in before],"Document changed during preparation"
  r.update(status="inflight",write_attempted=True);save()
  t.request(m.MS,path,"PUT",{"positions":list(grouped.values())})
 afterdoc=t.request(m.MS,path);after=w.ms_rows(path+"/positions");validate(afterdoc,after)
 checks={"totals_unchanged":totals(after)==expected,"unique":len(after)==len(totals(after)),"quantity":sum(p["quantity"] for p in after)==156,"order":[m.href(p["assortment"]) for p in after]==list(grouped),"posted":afterdoc.get("applicable") is True,"zero_prices":all(p.get("price")==0 for p in after)}
 r.update(status="verified" if all(checks.values()) else "verification_failed",checks=checks,after_positions=len(after),quantity=156,url=afterdoc["meta"].get("uuidHref"),verified_at=m.now());save()
 assert all(checks.values()),"Merge verification failed"
 print("Duplicate merge verified; total quantity unchanged")
except Exception as e:
 r["error"]=str(e) if isinstance(e,(m.Stop,AssertionError)) else type(e).__name__
 if r["status"] not in ("inflight","verification_failed"):r["status"]="stopped"
 save();print("Stopped; private journal contains outcome; no write replay");raise SystemExit(1)
