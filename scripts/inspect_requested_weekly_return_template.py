"""Inspect the official return template; never save an accounting document."""
import os,json
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t);root=os.environ["WEEKLY_REVIEW_ROOT"]
plan=db.get(root+"plan:v1");ident=next(iter(set(plan["basis"].values())))
d=t.request(m.MS,"entity/demand/"+ident)
template=t.request(m.MS,"entity/salesreturn/new","PUT",{"demand":m.meta(d)})
db.put(root+"return_template:v1",{"status":"read_verified","at":m.now(),"basis":d,"template":template})
print(json.dumps({"status":"read_verified","template_only":True}))
