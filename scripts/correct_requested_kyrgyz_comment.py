"""Correct only the explicitly authorized weekly demand comment."""
import json
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
root="weekly_report_review:ooo:883046423:"
cfg=db.get(root+"comment_correction:v1");assert cfg and cfg["authorized"] is True
path="entity/demand/"+cfg["demand_id"]
before=t.request(m.MS,path);positions=w.ms_rows(path+"/positions")
assert before["name"]==cfg["expected_name"] and before["applicable"] is True and before["sum"]==0 and all(p["price"]==0 for p in positions)
snapshot={"document":before,"positions":positions,"at":m.now()}
if not db.get(root+"comment_correction:before:v1"):db.put(root+"comment_correction:before:v1",snapshot)
if before.get("description")!=cfg["comment"]:t.request(m.MS,path,"PUT",{"description":cfg["comment"]})
after=t.request(m.MS,path);after_positions=w.ms_rows(path+"/positions")
assert after["description"]==cfg["comment"] and after["applicable"] is True and after["sum"]==0
assert [(p["id"],p["quantity"],p["price"]) for p in positions]==[(p["id"],p["quantity"],p["price"]) for p in after_positions]
out={"status":"verified","at":m.now(),"id":after["id"],"name":after["name"],"comment":after["description"],"posted":True,"prices_zero":True,"positions_unchanged":True}
db.put(root+"comment_correction:result:v1",out)
cfg["authorized"]=False;cfg["status"]="completed";db.put(root+"comment_correction:v1",cfg)
print(json.dumps({"status":"verified","comment_only":True}))
