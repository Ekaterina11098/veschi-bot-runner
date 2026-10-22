"""Read-only inspection of exact user-requested demand 02729."""
import json
import fbs_document_chain as m
class ReadOnly(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":raise m.Stop("Document writes prohibited")
  return super().request(base,path,method,body,params)
t=ReadOnly();db=m.Cache(t);w=m.Worker(t,db,{})
ident="40ca02e6-cbbc-11f1-0a80-0c5400527d96"
doc=t.request(m.MS,"entity/demand/"+ident)
positions=w.ms_rows("entity/demand/"+ident+"/positions",{"expand":"assortment"})
refs={}
for key in ("organization","agent","store","customerOrder","project","contract","state","rate"):
 value=doc.get(key)
 if isinstance(value,dict) and m.href(value).startswith(m.MS):
  refs[key]=t.request(m.MS,m.href(value)[len(m.MS):].split("?")[0])
related={}
for key in ("returns","salesReturns","invoicesOut","payments"):
 for value in doc.get(key,[]) if isinstance(doc.get(key),list) else []:
  link=m.href(value)
  if link.startswith(m.MS):
   path=link[len(m.MS):].split("?")[0]
   d=t.request(m.MS,path)
   if d.get("positions"):d["expanded_positions"]=w.ms_rows(path+"/positions",{"expand":"assortment"})
   related.setdefault(key,[]).append(d)
db.put("weekly_report_review:demand:02729:inspection:v1",{"at":m.now(),"status":"verified","document":doc,"positions":positions,"references":refs,"related":related})
print(json.dumps({"status":"verified","positions":len(positions),"quantity":sum(p["quantity"] for p in positions)}))
