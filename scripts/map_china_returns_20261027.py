import os,json,collections,re
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
root="returns_transfer:china:20261027:"
req=db.get(root+"request:v1")
ps=w.ms_rows("entity/product")
def key(row):
 if " — " not in row:return row
 word,n=row.split(" — ")
 return str(int(n))+({"зонт":"з","панама":"м","шарф":"м","манишка":"м","ремень":"р"}[word])
counts=collections.Counter(key(x) for x in req["rows"])
by=collections.defaultdict(list)
for p in ps:
 if not p.get("archived"):by[p.get("code","").strip().casefold()].append(p)
mapping=[];issues=[]
for k,q in counts.items():
 candidates=by[k.casefold()]
 if len(candidates)!=1:
  issues.append({"key":k,"quantity":q,"matches":[{"id":p["id"],"name":p["name"],"article":p.get("article"),"code":p.get("code")} for p in candidates]})
 else:
  p=candidates[0];mapping.append({"key":k,"quantity":q,"id":p["id"],"name":p["name"],"article":p.get("article"),"code":p.get("code"),"assortment":m.meta(p)})
out={"status":"mapped" if not issues else "needs_mapping","quantity":sum(counts.values()),"mapping":mapping,"issues":issues,"samples":[{"id":p["id"],"name":p["name"],"article":p.get("article"),"code":p.get("code")} for p in ps if any(s in p.get("article","").casefold() for s in ["61-","538-","00-","531-","511-"])]}
db.put(root+"mapping:v1",out)
print(json.dumps({"status":out["status"],"mapped":len(mapping),"issues":len(issues)}))
