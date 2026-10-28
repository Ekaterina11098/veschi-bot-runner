"""Preflight the private return batch against exact product codes and available source stock."""
import collections,json,re,math,os,urllib.request,urllib.parse,urllib.error,gzip,time
import fbs_document_chain as m
ROOT="returns_transfer:multi:20261027:batch2:"
class StockTransport(m.Transport):
 def _request_once(self,base,path,method="GET",body=None,params=None):
  if base!=m.MS or path!="report/stock/all" or method!="GET":
   return super()._request_once(base,path,method,body,params)
  request=urllib.request.Request(base+path+"?"+urllib.parse.urlencode(params or {}),headers={"Authorization":"Bearer "+os.environ["MOYSKLAD_API_TOKEN"],"Accept":"application/json;charset=utf-8","Accept-Encoding":"gzip"})
  try:
   with urllib.request.urlopen(request,timeout=120) as r:
    raw=r.read()
    return json.loads(gzip.decompress(raw) if r.headers.get("Content-Encoding")=="gzip" else raw)
  except urllib.error.HTTPError as e:raise m.Stop("HTTP_"+str(e.code)+" GET report/stock/all") from None
  except (TimeoutError,urllib.error.URLError):raise m.Stop("API transport outcome uncertain") from None
t=StockTransport();db=m.Cache(t);w=m.Worker(t,db,{})
req=db.get(ROOT+"request:v1")
def norm(s):return s.strip().casefold().replace("c","с")
def code(item):
 match=re.fullmatch(r"(зонт|панама|манишка|ремень|шарф)\s*—\s*(\d+)",item)
 if match:return str(int(match[2]))+{"зонт":"з","панама":"м","манишка":"м","ремень":"р","шарф":"м"}[match[1]]
 number=re.match(r"^\d+",item).group()
 if number=="00":number="0"
 return req.get("code_aliases",{}).get(number+"с",number+"с")
out={"status":"reading","sources":[],"issues":[],"at":m.now()}
try:
 stores=w.ms_rows("entity/store")
 products=w.ms_rows("entity/product")
 by=collections.defaultdict(list)
 for p in products:
  if not p.get("archived"):by[norm(p.get("code",""))].append(p)
 target=[s for s in stores if s["name"]==req["target_store"] and not s.get("archived")]
 assert len(target)==1,"Target warehouse ambiguous"
 out["target"]=target[0]
 current=t.request(m.MS,"report/stock/bystore/current",params={"stockType":"freeStock","include":"zeroLines"})
 assert isinstance(current,list),"Short stock report must be a complete array"
 stockindex={}
 for r in current:
  pair=(r["storeId"],r["assortmentId"])
  assert pair not in stockindex,"Duplicate short stock row"
  assert type(r["freeStock"]) in (int,float) and math.isfinite(r["freeStock"])
  stockindex[pair]=r["freeStock"]
 for source in req["sources"]:
  selected=[s for s in stores if s["name"]==source["store_name"] and not s.get("archived")]
  record={"label":source["label"],"slug":source["slug"],"description":source["description"],"quantity":len(source["rows"]),"mapping":[],"issues":[]}
  if len(selected)!=1:record["issues"].append({"issue":"source_warehouse_ambiguous","matches":[s["name"] for s in stores]});out["sources"].append(record);continue
  record["store"]=selected[0]
  counts=collections.Counter(code(r["item"]) for r in source["rows"])
  for k,q in counts.items():
   found=by[norm(k)]
   if len(found)!=1:
    number=re.match(r"\d+",k).group()
    suggestions=[{"id":p["id"],"name":p["name"],"article":p.get("article"),"code":p.get("code")} for p in products if re.match(r"^0*"+re.escape(str(int(number)))+r"(?:-|$)",p.get("article",""))]
    record["issues"].append({"issue":"product_mapping","code":k,"quantity":q,"matches":len(found),"suggestions":suggestions});continue
   p=found[0]
   assert not p.get("variantsCount",0),"Product variants require separate mapping"
   record["mapping"].append({"id":p["id"],"code":k,"article":p.get("article"),"name":p["name"],"quantity":q,"assortment":m.meta(p)})
  for p in record["mapping"]:
   pair=(selected[0]["id"],p["id"])
   if pair not in stockindex:
    record["issues"].append({"issue":"stock_unconfirmed","code":p["code"],"article":p["article"],"required":p["quantity"]})
    continue
   a=stockindex[pair]
   p.update(available=a,stock_source="report/stock/bystore/current:freeStock")
   if a<p["quantity"]:record["issues"].append({"issue":"shortage","code":p["code"],"article":p["article"],"name":p["name"],"required":p["quantity"],"available":a,"shortage":p["quantity"]-a})
  record["status"]="ready" if not record["issues"] else "needs_review"
  out["sources"].append(record)
  db.put(ROOT+"preflight_fast:v1",out)
 assert sum(x["quantity"] for x in out["sources"])==183
 out["status"]="ready" if all(not x["issues"] for x in out["sources"]) else "needs_review"
 out["completed_at"]=m.now()
 db.put(ROOT+"preflight:v1",out)
 print(json.dumps({"status":out["status"],"sources":len(out["sources"]),"issues":sum(len(s["issues"]) for s in out["sources"])}))
except Exception as e:
 out.update(status="stopped",error=str(e) if isinstance(e,(m.Stop,AssertionError)) else type(e).__name__)
 db.put(ROOT+"preflight:v1",out)
 print(json.dumps({"status":"stopped","error_type":type(e).__name__}));raise SystemExit(1)
