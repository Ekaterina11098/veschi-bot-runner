"""Read-only token diagnosis. Never print token values, claims or seller data."""
import base64, json, os, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

def call(url, token, body=None):
    headers={"Authorization":token,"Content-Type":"application/json"}
    req=urllib.request.Request(url,headers=headers,data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            return r.status,json.load(r)
    except urllib.error.HTTPError as error:
        try:
            body=json.loads(error.read().decode("utf-8"))
        except Exception:
            body={}
        return error.code,body

def main():
    raw=os.getenv("WB_TOKEN_3","")
    token=raw.strip()
    result={"setting":"WB_TOKEN_3"}
    pieces=token.split(".")
    result["contains_quotes"]=token.startswith(('"',"'")) or token.endswith(('"',"'"))
    result["contains_prefix"]=token.lower().startswith(("bearer ","wb_token_3"))
    result["contains_internal_whitespace"]=any(c.isspace() for c in token)
    claims=None
    if len(pieces)==3 and not any(result[k] for k in ("contains_quotes","contains_prefix","contains_internal_whitespace")):
        try:
            claims=json.loads(base64.urlsafe_b64decode(pieces[1]+"="*(-len(pieces[1])%4)))
        except Exception:
            pass
    result["jwt_structure_valid"]=isinstance(claims,dict)
    if isinstance(claims,dict):
        exp=claims.get("exp")
        result["expired"]=not isinstance(exp,(int,float)) or exp<=time.time()
        if isinstance(exp,(int,float)):
            result["expires_at"]=datetime.fromtimestamp(exp,timezone.utc).isoformat()
        mask=int(claims.get("s",0))
        result["content_category"]=bool(mask & 1)
        result["marketplace_category"]=bool(mask & (1<<3))
        result["statistics_category"]=bool(mask & (1<<5))
        if not result["expired"]:
            status,body=call("https://content-api.wildberries.cn/ping",token)
            result["content_ping_http"]=status
            if status==200:
                status,body=call("https://content-api.wildberries.cn/content/v2/get/cards/list",token,
                    {"settings":{"cursor":{"limit":1},"filter":{"withPhoto":-1}}})
                result["content_read_http"]=status
            if status!=200:
                detail=body.get("detail",body.get("message","")) if isinstance(body,dict) else ""
                result["wb_detail"]=str(detail).replace(token,"[redacted]")[:700]
    key=os.environ["SUPABASE_SECRET_KEY"].strip()
    headers={"apikey":key,"Content-Type":"application/json","Prefer":"resolution=merge-duplicates"}
    if not key.startswith("sb_secret_"):
        headers["Authorization"]="Bearer "+key
    now=datetime.now(timezone.utc)
    body={"cache_key":"runner:credential-check","payload":result,"updated_at":now.isoformat(),
          "expires_at":(now+timedelta(days=1)).isoformat()}
    req=urllib.request.Request(os.environ["SUPABASE_URL"].strip().rstrip("/")+"/rest/v1/telegram_api_cache?on_conflict=cache_key",
        headers=headers,data=json.dumps(body).encode())
    with urllib.request.urlopen(req,timeout=25):
        pass
    print("Read-only credential diagnosis saved in protected backend.")
    print("No stock changes or Telegram messages.")

if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("Diagnosis failed: "+type(exc).__name__)
        raise SystemExit(1)
