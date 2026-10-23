const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {stripTypeScriptTypes}=require('node:module');
const src=fs.readFileSync(__dirname+'/ip_png_reply_webhook.ts','utf8');
const fn=stripTypeScriptTypes(src.slice(src.indexOf('async function exactPngApproval'),src.indexOf('Deno.serve(async')));
let writes=0,dispatches=0;
const p={delivery_status:'sent',message_id:42,file_unique_id:'png',message_thread_id:null,expires_at:'2036-10-23T00:00:00Z',plan_sha256:'frozen'};
const scope={Response,Date,Number,JSON,encodeURIComponent,AbortSignal,GITHUB:'test',reply:(chat,text)=>({chat,text}),database:async(path,method,body)=>{if(!method)return [{payload:p}];if(body?.cache_key?.includes('rejected:'))return [];writes++;return method==='POST'?[{}]:null;},fetch:async()=>{dispatches++;return {ok:true}}};
vm.createContext(scope);vm.runInContext(fn+';this.approve=exactPngApproval',scope);
const m={chat:{id:-1004378639510},from:{id:123},message_id:50,text:'Сделай всё',reply_to_message:{message_id:42,from:{id:8987327588,is_bot:true},photo:[{file_unique_id:'png'}]}};
(async()=>{
 assert.equal(await scope.approve({update_id:1},{...m,text:'да',reply_to_message:undefined},{bot_id:8987327588}),null);
 assert.equal(await scope.approve({update_id:1},{...m,text:'не применяй'},{bot_id:8987327588}),null);
 await scope.approve({update_id:1},{...m,reply_to_message:{...m.reply_to_message,message_id:41}},{bot_id:8987327588});assert.equal(writes,0);
 await scope.approve({update_id:1},{...m,forward_origin:{}},{bot_id:8987327588});assert.equal(writes,0);
 await scope.approve({update_id:1},{...m,chat:{...m.chat,is_forum:true},message_thread_id:8},{bot_id:8987327588});assert.equal(writes,0);
 for(const text of ['сделай все','сделй все','примени','поменяй','согласен','да, сделай всё']){
  await scope.approve({update_id:1},{...m,text,message_thread_id:42},{bot_id:8987327588});
 }
 assert.equal(dispatches,6);assert.equal(writes,12);
 scope.database=async()=>[];await scope.approve({update_id:1},m,{bot_id:8987327588});assert.equal(dispatches,6);
 console.log('12 reply-binding, non-forum thread, alias and negative checks passed; no network');
})().catch(e=>{console.error(e);process.exit(1)});

