import assert from 'node:assert/strict';
import {chooseWork} from './china_dialog_clock_policy.mjs';
const now=new Date('2026-11-01T15:00:00Z');
const watch=(fields={})=>({cache_key:'china_agent:conversion_watch:v1:scope',payload:{id:'a',agent_id:'china',chat_id:-1004342917488,owner_user_id:5122667182,status:'active',next_at:'2026-11-01T15:00:00Z',...fields}});
const pending=[{id:1,attempts:0,tool_trace:[{name:'china_saved_question'}]}];
assert.equal(chooseWork([], [watch()],now).action,'reports');
assert.equal(chooseWork(pending,[watch()],now).action,'reports');
assert.equal(chooseWork(pending,[],now).action,'dialog');
for(const fields of [{status:'completed'},{status:'delivery_uncertain'},{chat_id:-1},{owner_user_id:1},{next_at:'bad'},{next_at:'2026-11-01T16:00:00Z'}])
 assert.equal(chooseWork([],[watch(fields)],now),null);
assert.equal(chooseWork([],[],now),null);
console.log('clock policy: 10 cases passed');


