// No arbitrary SQL, eval, source collection or imports from operational agents.
export const CABINETS = ['token_1', 'token_2', 'token_3'];
export function normalizeSource(source) {
  const aliases={'wb orders':'orders','wb sales':'sales','wb stocks':'stocks','wb cards':'cards','wb finance':'finance'};
  return aliases[String(source).trim().toLowerCase()]??source;
}
export function validateArgs(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Object required');
  if (JSON.stringify(value).length > 12000) throw new Error('Arguments too large');
  return value;
}
export function calculate({operation, values}) {
  if (!Array.isArray(values) || !values.length || values.length > 200 || values.some(x => typeof x !== 'number' || !Number.isFinite(x))) throw new Error('Finite numbers required; missing is not zero');
  let result;
  switch (operation) {
    case 'sum': result = values.reduce((a,b)=>a+b,0); break;
    case 'subtract': result = values.slice(1).reduce((a,b)=>a-b,values[0]); break;
    case 'multiply': result = values.reduce((a,b)=>a*b,1); break;
    case 'divide': if(values.length!==2 || values[1]===0) throw new Error('Nonzero denominator required'); result=values[0]/values[1]; break;
    case 'change_pct': if(values.length!==2 || values[0]===0) throw new Error('Nonzero baseline required'); result=(values[1]/values[0]-1)*100; break;
    default: throw new Error('Unsupported operation');
  }
  if(!Number.isFinite(result)) throw new Error('Nonfinite result');
  return {result, operation, values, note:'Arithmetic only; verify units, source scope and completeness.'};
}
export class Database {
  constructor({url, key, fetcher=fetch}) {
    const parsed=new URL(url);
    if(parsed.protocol!=='https:' || !parsed.hostname.endsWith('.supabase.co')) throw new Error('Supabase HTTPS URL required');
    if(!key) throw new Error('Database credential missing');
    this.url=parsed.origin+'/rest/v1/'; this.key=key; this.fetcher=fetcher;
  }
  async request(path, {method='GET',body,prefer}={}) {
    if(!/^(owner_agent_(config|members|jobs|setup)(\?|$)|rpc\/owner_agent_read$)/.test(path)) throw new Error('Endpoint forbidden');
    const r=await this.fetcher(this.url+path,{method,headers:{apikey:this.key,...(!this.key.startsWith('sb_secret_')?{Authorization:'Bearer '+this.key}:{}),'Content-Type':'application/json',...(prefer?{Prefer:prefer}:{})},...(body===undefined?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(30000)});
    if(!r.ok) throw new Error('Database HTTP '+r.status);
    if(r.status===204)return null;
    const text=await r.text();
    return text?JSON.parse(text):null;
  }
  read(operation,args) { return this.request('rpc/owner_agent_read',{method:'POST',body:{operation,args}}); }
}
const spec=(name,description,properties,required=Object.keys(properties))=>({type:'function',name,description,strict:false,parameters:{type:'object',properties,required,additionalProperties:false}});
const string={type:'string'}, integer={type:'integer'};
export const TOOLS=[
  spec('sources','Inventory of saved source/cabinet periods, statuses and freshness. All cabinets by default. Never treats latest collection as latest covered date.',{search:string,cabinet:string},[]),
  spec('snapshots','List exact snapshot metadata; narrow source/cabinet/date. Includes pages, completion markers and raw IDs; not summed.',{source:string,cabinet:string,from:string,to:string,offset:integer},['source']),
  spec('read_snapshot','Read one exact snapshot with JSON path array (e.g. ["0","products"]). Paged rows; inspect total, returned and has_more. Empty/null is not confirmed zero.',{id:integer,path:{type:'array',items:string},offset:integer,limit:integer},['id','path']),
  spec('count_snapshot','Count ALL records in one exact snapshot array, not just a page. Filter equality supports JSON booleans as strings, e.g. filters={isCancel:"true"}. Preserves actual source, cabinet, period and status. A page is not a complete report.',{id:integer,path:{type:'array',items:string},filters:{type:'object',additionalProperties:string}},['id','path']),
  spec('aggregate_snapshot','Aggregate ONE snapshot array in database using exact nested field paths. Does not join batches or certify completeness. Missing counts retained. Optional exact field equality filters. Supported group/sum only.',{id:integer,path:{type:'array',items:string},group_by:string,fields:{type:'array',items:string},filters:{type:'object',additionalProperties:string}},['id','path','group_by','fields']),
  spec('economics','Read latest stored SKU economics for exact period/cabinet, with quality flags; not recomputed and not a complete business total. Paged.',{cabinet:string,from:string,to:string,article:string,offset:integer},['from','to']),
  spec('costs','Own article costs and dates. Missing is unknown. Paged.',{article:string,offset:integer},[]),
  spec('ozon','Read saved Ozon observations for exact period; duplicate runs remain explicit, never sum across them. Paged.',{from:string,to:string,source:string,sku:string,offset:integer},['from','to']),
  spec('calculate','Deterministic finite arithmetic. For change_pct use [old,new]. Unknown values forbidden.',{operation:{type:'string',enum:['sum','subtract','multiply','divide','change_pct']},values:{type:'array',items:{type:'number'}}})
];
export async function dispatch(db,name,args) {
  validateArgs(args);
  if(!TOOLS.some(t=>t.name===name)) throw new Error('Tool forbidden');
  if(args.cabinet && ![...CABINETS,'shared'].includes(args.cabinet)) throw new Error('Unknown cabinet');
  if(args.source)args={...args,source:normalizeSource(args.source)};
  return name==='calculate'?calculate(args):db.read(name,args);
}
