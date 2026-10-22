"""Read-only lookup of historical demands behind orange returns in report 132."""
import json
import fbs_document_chain as m
class ReadOnly(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":raise m.Stop("Writes prohibited")
  for attempt in range(3):
   try:return super().request(base,path,method,body,params)
   except m.Stop:
    if method!="GET" or attempt==2:raise
t=ReadOnly();db=m.Cache(t)
def rows(path,params=None):
 out=[]
 while True:
  d=t.request(m.MS,path,params={**(params or {}),"limit":100,"offset":len(out)})
  out.extend(d["rows"])
  if len(out)==d["meta"]["size"]:return out
  assert d["rows"] and len(out)<10000
all_returns=rows("entity/salesreturn",{"filter":"moment>=2026-10-19 00:00:00;moment<=2026-10-22 23:59:59"})
out={"at":m.now(),"status":"reading","returns":[]}
for doc in all_returns:
 desc=doc.get("description","")
 if not ("876125188" in desc or "876125192" in desc or "0(132)" in desc or "0( 132)" in desc):continue
 path=m.href(doc)[len(m.MS):]
 doc["expanded_positions"]=rows(path+"/positions",{"expand":"assortment"})
 link=m.href(doc.get("demand",{}))
 if link.startswith(m.MS):
  demand=t.request(m.MS,link[len(m.MS):])
  doc["basis_demand"]={k:demand.get(k) for k in ("id","name","moment","description","applicable","sum","store","customerOrder")}
  orderlink=m.href(demand.get("customerOrder",{}))
  if orderlink.startswith(m.MS):
   order=t.request(m.MS,orderlink[len(m.MS):])
   doc["basis_order"]={k:order.get(k) for k in ("id","name","moment","description","applicable","sum","store")}
 out["returns"].append(doc)
 db.put("weekly_report_review:132:orange_returns:v1",out)
out["status"]="verified"
db.put("weekly_report_review:132:orange_returns:v1",out)
print(json.dumps({"status":"verified","returns":len(out["returns"])}))
