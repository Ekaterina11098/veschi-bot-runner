"""Compare visual hashes against the authenticated IP catalog. No external writes."""
import json,io,math,time,urllib.request,concurrent.futures
import numpy as np
from PIL import Image,ImageOps
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t);root="photo_rights_review:ip:20261026:"
targets=db.get(root+"targets:v1");catalog=db.get(root+"catalog:v1");assert catalog["status"]=="complete"
cards=[]
for p in catalog["pages"]:cards+=db.get(root+"cards:"+str(p["page"]))
N=32;cos=np.cos(np.pi*np.arange(N)[:,None]*(2*np.arange(N)[None,:]+1)/(2*N))
def hashes(im):
 out=[]
 for top,bottom in ((0,1),(.12,.90)):
  x=im.crop((0,int(im.height*top),im.width,int(im.height*bottom))).convert("RGB")
  a=np.asarray(x.resize((32,32)).convert("L"),dtype=float);d=cos@a@cos.T;v=d[:8,:8].flatten();bits=v>np.median(v[1:])
  out.append(hex(sum(int(z)<<i for i,z in enumerate(bits)))[2:].zfill(16))
 return out
def read(task):
 c,i,p=task
 url=p.get("c246x328") or p.get("big")
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req,timeout=15) as r:im=Image.open(io.BytesIO(r.read())).convert("RGB")
  return {"nmID":c["nmID"],"article":c["vendorCode"],"photo":i+1,"url":url,"hashes":hashes(im),"flipped_hashes":hashes(ImageOps.mirror(im))}
 except Exception:return {"nmID":c["nmID"],"photo":i+1,"error":"image_read_failed"}
tasks=[(c,i,p) for c in cards for i,p in enumerate((c.get("photos") or [])[:3])]
out={"status":"comparing","at":m.now(),"total":len(tasks),"read":0,"errors":0,"best":{z["article"]:[] for z in targets}}
index=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 for row in pool.map(read,tasks):
  out["read"]+=1
  if row.get("error"):out["errors"]+=1
  else:
   index.append(row)
   for target in targets:
    norm=min((int(x,16)^int(y,16)).bit_count() for x,y in zip(target["hashes"],row["hashes"]))
    flip=min((int(x,16)^int(y,16)).bit_count() for x,y in zip(target["hashes"],row["flipped_hashes"]))
    best=out["best"][target["article"]]
    best.append({**{k:row[k] for k in ("nmID","article","photo","url")},"distance":min(norm,flip),"mirrored":flip<norm})
    best.sort(key=lambda z:z["distance"]);del best[5:]
  if out["read"]%100==0:db.put(root+"matches:v1",out)
for off in range(0,len(index),100):db.put(root+"hashes:"+str(off),index[off:off+100])
out["status"]="compared";out["completed_at"]=m.now();db.put(root+"matches:v1",out)
print(json.dumps({"status":out["status"],"read":out["read"],"errors":out["errors"]}))
