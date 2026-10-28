"""Read prior cabinet-specific weekly document scope without operational writes."""
import os,json
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
root=os.environ["WEEKLY_REVIEW_ROOT"];req=db.get(root+"request:v1")
c=db.get("fbs_document_chain:"+req["cabinet"]+":config:v1")
store_ref=c["templates"]["salesreturn"]["store"]
store_id=m.href(store_ref).rsplit("/",1)[-1]
out={"at":m.now(),"status":"reading","store":t.request(m.MS,"entity/store/"+store_id),"orders":[],"duplicates":[]}
db.put(root+"scope:v1",out)
name=str(req["report_id"])
for d in w.ms_rows("entity/customerorder",{"filter":"name="+name}):out["duplicates"].append(d)
orders=w.ms_rows("entity/customerorder",{"filter":"store="+m.href(store_ref)+";moment>=2026-08-01 00:00:00","order":"moment,desc"})
for d in orders[:15]:
 if d.get("deleted"):continue
 d=t.request(m.MS,"entity/customerorder/"+d["id"],params={"expand":"organization,agent,store,rate.currency,state"})
 linked=[]
 for ref in d.get("demands",[]):
  uid=m.href(ref).rsplit("/",1)[-1]
  linked.append(t.request(m.MS,"entity/demand/"+uid,params={"expand":"rate.currency"}))
 out["orders"].append({"order":d,"demands":linked})
 if name in (d.get("name","")+" "+d.get("description","")):out["duplicates"].append(d)
 db.put(root+"scope:v1",out)
out["status"]="read_verified";out["completed_at"]=m.now();db.put(root+"scope:v1",out)
print(json.dumps({"status":out["status"],"prior_orders":len(out["orders"]),"duplicates":len(out["duplicates"])}))
