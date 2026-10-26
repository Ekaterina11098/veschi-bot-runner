"""Read-only comparison of attached picking PDF to exact supply documents."""
import collections,json
import fbs_document_chain as m
class ReadOnly(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":raise m.Stop("Document writes prohibited")
  for attempt in range(3):
   try:return super().request(base,path,method,body,params)
   except m.Stop:
    if method!="GET" or attempt==2:raise
t=ReadOnly();db=m.Cache(t);w=m.Worker(t,db,{})
p=db.get("fbs_document_chain:china:pdf_comparison:298590867:expected")
ledger=db.get("fbs_document_chain:china:supply:v1:WB-GI-298590867")
scope=db.get("fbs_document_chain:china:picking_scope:v1:WB-GI-298590867")
out={"at":m.now(),"status":"reading","pdf_quantity":len(p["items"]),"pdf_articles":len(p["counts"]),"scope":scope,"documents":[]}
out["raw_id_difference"]={"pdf_only":sorted(set(x["order_id"] for x in p["items"])-set(ledger["order_ids"])),"supply_only":sorted(set(ledger["order_ids"])-set(x["order_id"] for x in p["items"]))}
for kind,d in ledger["documents"].items():
 path="entity/"+kind+"/"+d["id"];doc=t.request(m.MS,path)
 ps=w.ms_rows(path+"/positions",{"expand":"assortment"})
 actual=collections.Counter()
 for pos in ps:actual[(pos["assortment"].get("article") or "").strip().casefold()]+=pos["quantity"]
 diff=[{"article":a,"pdf":p["counts"].get(a,0),"document":actual.get(a,0),"difference":actual.get(a,0)-p["counts"].get(a,0)} for a in sorted(set(actual)|set(p["counts"])) if actual.get(a,0)!=p["counts"].get(a,0)]
 out["documents"].append({"type":kind,"id":doc["id"],"name":doc["name"],"quantity":sum(actual.values()),"articles":len(actual),"differences":diff,"posted":doc["applicable"]})
 db.put("fbs_document_chain:china:pdf_comparison:298590867:result",out)
out["status"]="verified";db.put("fbs_document_chain:china:pdf_comparison:298590867:result",out)
print(json.dumps({"status":"verified","documents":len(out["documents"])}))
