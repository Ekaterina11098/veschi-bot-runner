import assert from 'node:assert/strict';
const hash=async s=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)))].map(n=>n.toString(16).padStart(2,'0')).join('');
let handler,lookups=0;
const config={active:true,chat_id:-1004342917488,bot_id:8780468043,secret_digest:await hash('old-test-secret')};
const transition={status:'prepared',bot_id:config.bot_id,chat_id:config.chat_id,old_digest:config.secret_digest,new_digest:await hash('new-test-secret'),valid_until:new Date(Date.now()+60000).toISOString()};
globalThis.Deno={env:{get:k=>({SUPABASE_URL:'https://unit.invalid',SUPABASE_SERVICE_ROLE_KEY:'unit-key'})[k]},serve:f=>{handler=f;}};
globalThis.fetch=async(url)=>{if(String(url).includes('/rest/v1/business_agent_config?'))return Response.json([config]);if(String(url).includes('inline_ingress_transition')){lookups++;return Response.json([{payload:transition}]);}throw Error('Unexpected external request');};
await import('./china_webhook.ts');
const probe=secret=>handler(new Request('https://unit.invalid/webhook',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':secret,'Content-Type':'application/json'},body:'{"probe":true}'}));
assert.equal((await probe('old-test-secret')).status,200);assert.equal(lookups,0);
assert.equal((await probe('new-test-secret')).status,200);
assert.equal((await probe('wrong-secret')).status,401);
transition.valid_until='2020-01-01T00:00:00Z';assert.equal((await probe('new-test-secret')).status,401);
transition.valid_until=new Date(Date.now()+60000).toISOString();transition.bot_id=1;assert.equal((await probe('new-test-secret')).status,401);
transition.bot_id=config.bot_id;transition.status='completed';assert.equal((await probe('new-test-secret')).status,401);
config.secret_digest=await hash('new-test-secret');assert.equal((await probe('new-test-secret')).status,200);assert.equal((await probe('old-test-secret')).status,401);
console.log('PASS canonical ingress authentication, bounded exact-scope transition, expired/wrong/complete transition rejected; new canonical verified; no external writes.');


const selected=await handler(new Request('https://unit.invalid/webhook',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':'new-test-secret','Content-Type':'application/json'},body:JSON.stringify({update_id:123,message:{message_id:9,chat:{id:config.chat_id,type:'supergroup'},from:{id:7,is_bot:false},via_bot:{id:config.bot_id},text:'ДРР · 454-NoelBag-cream\nВыберите РК товара:'}})}));assert.equal(selected.status,200);console.log('PASS selected inline card never becomes a queued cloud question.');
