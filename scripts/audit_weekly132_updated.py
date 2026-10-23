"""Read-only reconciliation of report 132 against current MoySklad documents."""
import collections,json,re
from decimal import Decimal
import fbs_document_chain as m
KEY="weekly_report_review:132:audit_result:20261023"
class ReadOnly(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":raise m.Stop("MoySklad writes prohibited")
  for attempt in range(3):
   try:return super().request(base,path,method,body,params)
   except m.Stop:
    if method!="GET" or attempt==2:raise
t=ReadOnly();db=m.Cache(t)
expected=db.get("weekly_report_review:132:audit_expected:20261023")
assert expected and expected["CK_sum"]==4921
def rows(path,params=None):
 out=[]
 while True:
  d=t.request(m.MS,path,params={**(params or {}),"limit":100,"offset":len(out)})
  out.extend(d["rows"])
  if len(out)==d["meta"]["size"]:return out
  assert d["rows"] and len(out)<10000
def counter(ps):
 c=collections.Counter()
 for p in ps:
  a=p["assortment"]
  article=(a.get("article") or "").strip().casefold()
  if a.get("id")=="93e21aa3-862f-11ef-0a80-096400115a88":article="5belts-chocolate"
  assert article
  c[article]+=p["quantity"]
 return c
def diffs(actual,wanted):
 return [{"article":a,"actual":actual.get(a,0),"expected":wanted.get(a,0)} for a in sorted(set(actual)|set(wanted)) if actual.get(a,0)!=wanted.get(a,0)]
result={"at":m.now(),"status":"reading","file_sha256":expected["sha256"],"documents":[]}
orders=rows("entity/customerorder",{"filter":"name=876125188, 876125192"})
result["order_candidates"]=len(orders)
assert len(orders)==1
specs=[("customerorder",orders[0]["id"]),("demand","40ca02e6-cbbc-11f1-0a80-0c5400527d96"),("salesreturn","5c6f906b-cbb3-11f1-0a80-02d3004ed68e"),("salesreturn","8fc62ba0-cbb3-11f1-0a80-02d3004ee4da")]
return_counter=collections.Counter()
for kind,uid in specs:
 path="entity/"+kind+"/"+uid
 d=t.request(m.MS,path);ps=rows(path+"/positions",{"expand":"assortment"})
 checks={"posted":d.get("applicable") is True,"zero_sum":d["sum"]==0,"all_prices_zero":all(p["price"]==0 for p in ps),"organization":m.href(d["organization"]).endswith("/61c199c8-fd78-11ee-0a80-1479002a9f95"),"buyer":m.href(d["agent"]).endswith("/4cc3ffa2-fd7c-11ee-0a80-0b56002b7934"),"store":m.href(d["store"]).endswith("/fcf31c2d-07ac-11ef-0a80-014d00489826")}
 c=counter(ps)
 if kind!="salesreturn":
  checks["items_match"]=not diffs(c,expected["expected_order"])
  item_diffs=diffs(c,expected["expected_order"])
 else:
  return_counter.update(c);item_diffs=[]
 if kind=="customerorder":
  checks["comment"]=" ".join(d.get("description","").split())==" ".join(expected["order_comment"].split())
 if kind=="demand":
  checks["basis"]=m.href(d.get("customerOrder",{})).endswith("/"+orders[0]["id"])
  amounts=re.findall(r"\d[\d\s]*(?:[,.]\d+)?",d.get("description",""))
  values=[Decimal(re.sub(r"\s","",v).replace(",",".")) for v in amounts]
  checks["comment"]=values==[Decimal("231936.60"),Decimal("4921"),Decimal("227015.60")]
  checks["comment_labels"]="Опт" in d.get("description","") and "возврат" in d.get("description","")
 if kind=="salesreturn":
  checks["comment"]=" ".join(d.get("description","").split())==" ".join(expected["return_comment"].split())
  basis=t.request(m.MS,m.href(d["demand"])[len(m.MS):])
  original_order=t.request(m.MS,m.href(basis["customerOrder"])[len(m.MS):])
  checks["basis_posted"]=basis.get("applicable") is True
  checks["basis_order_posted"]=original_order.get("applicable") is True
  checks["prior_period"]=basis["moment"]<"2026-10-12 00:00:00" if d["name"]=="02428" else basis["moment"]<"2026-10-19 00:00:00"
 else:basis=None;original_order=None
 result["documents"].append({"type":kind,"id":uid,"name":d["name"],"moment":d["moment"],"comment":d.get("description",""),"checks":checks,"positions":len(ps),"quantity":sum(p["quantity"] for p in ps),"items":dict(c),"item_differences":item_diffs,"document":d,"raw_positions":ps,"basis":None if basis is None else {"name":basis["name"],"id":basis["id"],"posted":basis["applicable"],"order":original_order["name"],"order_posted":original_order["applicable"]}})
 db.put(KEY,result)
result["return_differences"]=diffs(return_counter,expected["expected_returns"])
result["returns_match"]=not result["return_differences"]
result["status"]="verified" if result["returns_match"] and all(all(d["checks"].values()) for d in result["documents"]) else "differences"
db.put(KEY,result)
print(json.dumps({"status":result["status"],"documents":len(result["documents"])}))
