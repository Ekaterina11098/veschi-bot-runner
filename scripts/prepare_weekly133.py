"""Read-only MS preparation for user-requested weekly report; data stays private."""
import json,collections
import fbs_document_chain as m
class ReadOnly(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":raise m.Stop("MS writes prohibited")
  return super().request(base,path,method,body,params)
t=ReadOnly();db=m.Cache(t);w=m.Worker(t,db,{})
key="weekly_report_review:133:"
inp=db.get(key+"input:v1");assert inp and inp["rules_version"]=="2026-10-23-reviewed"
out={"at":m.now(),"status":"reading","products":{},"demands":[],"duplicates":[]}
wanted=set(inp["sales"])|set(inp["returns"])
for p in w.ms_rows("entity/product",{"filter":"archived=false"}):
 a=(p.get("article") or "").strip().casefold()
 if a in wanted:out["products"].setdefault(a,[]).append({k:p.get(k) for k in ("id","article","name","meta","buyPrice","salePrices")})
db.put(key+"prepare:v1",out)
for a in inp["returns"]:
 for p in out["products"].get(a,[]):
  p["stock_rows"]=w.ms_rows("report/stock/all",{"filter":"product="+m.MS+"entity/product/"+p["id"],"stockMode":"all","quantityMode":"all"})
out["organization"]=t.request(m.MS,"entity/organization/61c199c8-fd78-11ee-0a80-1479002a9f95")
out["agent"]=t.request(m.MS,"entity/counterparty/4cc3ffa2-fd7c-11ee-0a80-0b56002b7934")
out["store"]=t.request(m.MS,"entity/store/fcf31c2d-07ac-11ef-0a80-014d00489826")
flt="organization="+m.MS+"entity/organization/"+out["organization"]["id"]+";agent="+m.MS+"entity/counterparty/"+out["agent"]["id"]+";store="+m.MS+"entity/store/"+out["store"]["id"]
for typ in ("customerorder","demand","salesreturn"):
 for d in w.ms_rows("entity/"+typ,{"filter":flt+";moment>=2026-10-19 00:00:00"}):
  if any(str(n) in d.get("name","")+" "+d.get("description","") for n in inp["report_ids"]) or "0(133)" in d.get("description",""):
   d["type"]=typ;out["duplicates"].append(d)
db.put(key+"prepare:v1",out)
for d in w.ms_rows("entity/demand",{"filter":flt+";moment>=2026-08-01 00:00:00;moment<2026-10-26 00:00:00","expand":"customerOrder","order":"moment,desc"}):
 order=d.get("customerOrder",{})
 if m.href(order).startswith(m.MS):order=t.request(m.MS,m.href(order)[len(m.MS):])
 d["customerOrder"]=order
 if not ("0(" in order.get("description","") or "ВБ ВА" in order.get("description","")):continue
 pos=w.ms_rows("entity/demand/"+d["id"]+"/positions",{"expand":"assortment","fields":"stock"})
 matching=[p for p in pos if (p.get("assortment",{}).get("article") or "").strip().casefold() in inp["returns"]]
 if not matching:continue
 item={k:d.get(k) for k in ("id","name","moment","description","applicable","customerOrder","meta")}
 item["positions"]=matching
 item["returns"]=w.ms_rows("entity/salesreturn",{"filter":"demand="+m.MS+"entity/demand/"+d["id"]})
 for r in item["returns"]:r["positions_full"]=w.ms_rows("entity/salesreturn/"+r["id"]+"/positions",{"expand":"assortment"})
 out["demands"].append(item);db.put(key+"prepare:v1",out)
out["status"]="prepared";out["completed_at"]=m.now();db.put(key+"prepare:v1",out)
print(json.dumps({"status":out["status"],"missing_products":len(wanted-set(out["products"])),"ambiguous_products":sum(len(v)!=1 for v in out["products"].values()),"basis_demands":len(out["demands"]),"existing_documents":len(out["duplicates"])}))
