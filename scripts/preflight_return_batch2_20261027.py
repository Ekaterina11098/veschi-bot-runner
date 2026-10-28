"""Preflight the private return batch against exact product codes and available source stock."""
import collections,json,re,math
import fbs_document_chain as m
ROOT="returns_transfer:multi:20261027:batch2:"
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
req=db.get(ROOT+"request:v1")
def norm(s):return s.strip().casefold().replace("c","с")
def code(item):
 match=re.fullmatch(r"(зонт|панама|манишка|ремень|шарф)\s*—\s*(\d+)",item)
 if match:return str(int(match[2]))+{"зонт":"з","панама":"м","манишка":"м","ремень":"р","шарф":"м"}[match[1]]
 number=re.match(r"^\d+",item).group()
 if number=="00":number="0"
 return number+"с"
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
  stock=w.ms_rows("report/stock/all",{"filter":"store="+m.href(selected[0])+";stockMode=all;quantityMode=all"})
  stockby=collections.defaultdict(list)
  for r in stock:stockby[(r.get("article") or "").strip().casefold()].append(r)
  for p in record["mapping"]:
   matches=stockby[(p["article"] or "").strip().casefold()]
   if len(matches)!=1:
    record["issues"].append({"issue":"stock_unconfirmed","code":p["code"],"article":p["article"],"required":p["quantity"],"stock_rows":len(matches)})
    continue
   s=matches[0];a=s.get("stock");r=s.get("reserve")
   if not all(type(x) in (int,float) and math.isfinite(x) for x in (a,r)) or r<0:raise m.Stop("Incomplete stock or reserve")
   p.update(stock=a,reserve=r,available=a-r)
   if p["available"]<p["quantity"]:record["issues"].append({"issue":"shortage","code":p["code"],"article":p["article"],"name":p["name"],"required":p["quantity"],"stock":a,"reserve":r,"available":a-r,"shortage":p["quantity"]-(a-r)})
  record["status"]="ready" if not record["issues"] else "needs_review"
  out["sources"].append(record)
 assert sum(x["quantity"] for x in out["sources"])==183
 out["status"]="ready" if all(not x["issues"] for x in out["sources"]) else "needs_review"
 out["completed_at"]=m.now()
 db.put(ROOT+"preflight:v1",out)
 print(json.dumps({"status":out["status"],"sources":len(out["sources"]),"issues":sum(len(s["issues"]) for s in out["sources"])}))
except Exception as e:
 out.update(status="stopped",error=str(e) if isinstance(e,(m.Stop,AssertionError)) else type(e).__name__)
 db.put(ROOT+"preflight:v1",out)
 print(json.dumps({"status":"stopped","error_type":type(e).__name__}));raise SystemExit(1)
