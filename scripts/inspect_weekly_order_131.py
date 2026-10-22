"""Read-only weekly-report customer order and linked document inspection."""
import json
import fbs_document_chain as m
class ReadOnly(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":raise m.Stop("Document writes prohibited")
  for attempt in range(3):
   try:return super().request(base,path,method,body,params)
   except m.Stop:
    if method!="GET" or attempt==2:raise
t=ReadOnly();db=m.Cache(t)
class SmallPages(m.Worker):
 def ms_rows(self,path,params=None):
  rows=[]
  while True:
   data=self.t.request(m.MS,path,params={**(params or {}),"limit":100,"offset":len(rows)})
   batch=data["rows"];rows.extend(batch)
   if len(rows)==data["meta"]["size"]:return rows
   assert batch and len(rows)<20000
w=SmallPages(t,db,{})
orders=w.ms_rows("entity/customerorder",{"filter":"name=869904413, 869904457"})
assert len(orders)==1,"Order not uniquely identified"
root=orders[0]
result={"at":m.now(),"status":"reading","root":root,"documents":[],"references":{}}
KEY="weekly_report_review:order:869904413_869904457:inspection:v1"
db.put(KEY,result)
queue=[m.href(root)]
seen=set()
def add(link):
 if link.startswith(m.MS+"entity/") and link not in seen:queue.append(link)
while queue:
 link=queue.pop(0).split("?")[0]
 if link in seen:continue
 assert len(seen)<60
 seen.add(link);path=link[len(m.MS):]
 doc=t.request(m.MS,path)
 if doc.get("positions"):
  doc["expanded_positions"]=w.ms_rows(path+"/positions",{"expand":"assortment"})
 try:doc["audit_events"]=t.request(m.MS,path+"/audit")
 except Exception as e:doc["audit_error"]=str(e)
 for key in ("organization","agent","store","state"):
  ref=doc.get(key)
  if isinstance(ref,dict) and m.href(ref).startswith(m.MS):
   href=m.href(ref).split("?")[0]
   if href not in result["references"]:result["references"][href]=t.request(m.MS,href[len(m.MS):])
 for key in ("demands","returns","salesReturns","invoicesOut","payments"):
  for value in doc.get(key,[]) if isinstance(doc.get(key),list) else []:add(m.href(value))
 for key in ("customerOrder","demand","invoiceOut"):
  value=doc.get(key)
  if isinstance(value,dict):add(m.href(value))
 result["documents"].append(doc);db.put(KEY,result)
# Returns may be absent from demand links; look up a bounded reporting interval.
returns=w.ms_rows("entity/salesreturn",{"filter":"moment>=2026-10-01 00:00:00;moment<=2026-10-22 23:59:59"})
demand_links={m.href(d) for d in result["documents"] if d.get("meta",{}).get("type")=="demand"}
for r in returns:
 if m.href(r.get("demand",{})) not in demand_links or m.href(r) in seen:continue
 path=m.href(r)[len(m.MS):];doc=t.request(m.MS,path)
 doc["expanded_positions"]=w.ms_rows(path+"/positions",{"expand":"assortment","fields":"stock"})
 for key in ("organization","agent","store","state"):
  href=m.href(doc.get(key,{})).split("?")[0]
  if href.startswith(m.MS) and href not in result["references"]:result["references"][href]=t.request(m.MS,href[len(m.MS):])
 result["documents"].append(doc)
result["status"]="verified";db.put(KEY,result)
print(json.dumps({"status":"verified","documents":len(result["documents"])}))
