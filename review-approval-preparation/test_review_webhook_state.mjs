import assert from 'node:assert/strict';
import {readStateResponse} from './webhook_state_response.mjs';
assert.equal(await readStateResponse(new Response(null,{status:201})),null);
assert.equal(await readStateResponse(new Response(null,{status:204})),null);
assert.deepEqual(await readStateResponse(new Response('[{"active":true}]',{status:200})),[{active:true}]);
await assert.rejects(()=>readStateResponse(new Response('invalid',{status:200})),SyntaxError);
await assert.rejects(()=>readStateResponse(new Response('{"code":"forbidden"}',{status:403})),/State unavailable/);
console.log('5 database response regression checks passed');
