import test from 'node:test';
import assert from 'node:assert/strict';
import {createConversation, initialState, restore, serialize, applySearchState, validActiveSearch, message} from './state.js';
import {recentContext, contextBeforeReply, CONTEXT_CHAR_LIMIT, CONTEXT_MESSAGE_LIMIT} from './context.js';
import {searchReferences} from './search.js';
const active = ids => ({search_type:'text',resolved_query:'black tees',mode:'exact',search_strategy:'exact',attributes:{colors:['black']},shown_product_ids:ids,shown_point_ids:[]});
const response = ids => ({active_search:active(ids),text:'Found more',response_id:'x',products:[],search_results:{exact:[],similar:[]}});

test('independent chats, refresh, new chat and legacy state',()=>{
  const state=initialState();const a=state.conversations[0];const b=createConversation();state.conversations.push(b);
  const entry=message('assistant','',{request:{query:'black',mode:'exact'}});a.messages.push(entry);
  applySearchState(a,entry,response(['101']));assert.equal(b.active_search,null);
  const restored=restore(serialize(state));assert.deepEqual(restored.conversations[0].active_search.shown_product_ids,['101']);assert.equal(restored.conversations[1].active_search,null);
  delete a.active_search;assert.equal(restore(serialize(state)).conversations[0].active_search,null);
  a.active_search={wrong:'state'};assert.equal(restore(serialize(state)).conversations[0].active_search,null);
  assert.equal(createConversation().active_search,null);
});
test('state changes only on accepted successful response; historical retry cannot overwrite',()=>{
  const chat=createConversation();chat.active_search=active(['1']);const first=message('assistant','',{request:{query:'more'}});chat.messages.push(first);
  applySearchState(chat,first,response(['1','2']));assert.deepEqual(chat.active_search.shown_product_ids,['1','2']);
  const next=message('assistant','',{request:{query:'white'}});chat.messages.push(next);
  applySearchState(chat,next,response(['new']));applySearchState(chat,first,response(['old']));assert.deepEqual(chat.active_search.shown_product_ids,['new']);
  next.request={type:'image'};applySearchState(chat,next,{products:[]});assert.deepEqual(chat.active_search,{search_type:'image'});
});
test('large history bounded by recent characters and records; no products, current duplicate or other chat',()=>{
  const messages=Array.from({length:250},(_,i)=>message('user',`${i} `+'a'.repeat(9990),{products:[{embedding:[1,2]}]}));
  const c=recentContext(messages);assert.ok(c.length<=CONTEXT_MESSAGE_LIMIT);assert.ok(c.reduce((n,r)=>n+r.text.length,0)<=CONTEXT_CHAR_LIMIT);assert.match(c.at(-1).text,/^249 /);
  assert.ok(!JSON.stringify(c).includes('embedding'));
  const small=[message('user','old topic'),message('assistant','answer'),message('user','current'),message('assistant','',{status:'pending'})];
  assert.deepEqual(contextBeforeReply(small,small.at(-1).id),[{role:'user',text:'old topic'},{role:'assistant',text:'answer'}]);
  assert.deepEqual(recentContext(createConversation().messages),[]);
});
test('transport sends compact state and full normal text, not product snapshots',async t=>{
  t.mock.method(globalThis,'fetch',async(url,opts)=>{
    const body=JSON.parse(opts.body);assert.deepEqual(body.active_search,active(['1','2']));assert.equal(body.context.length,12);assert.ok(!('products' in body));return new Response(JSON.stringify(response(['1','2','3'])));
  });
  const context=Array.from({length:12},()=>({role:'user',text:'a fashion topic'}));
  const result=await searchReferences({query:'more',mode:'exact',context,active_search:active(['1','2'])});assert.deepEqual(result.active_search.shown_product_ids,['1','2','3']);
  assert.ok(validActiveSearch(result.active_search));assert.ok(!validActiveSearch({...active([]),shown_product_ids:Array(4097).fill('1')}));
});

test('saved requests do not duplicate full context and legacy image continuation is marked',()=>{
  const state=initialState();const chat=state.conversations[0];
  chat.messages.push(message('assistant','Found',{status:'complete',search_type:'image',products:[],request:{type:'image',attachment_id:'a',file_name:'x.jpg',context:[{role:'user',text:'duplicated history'}]}}));
  delete chat.active_search;
  const raw=serialize(state);assert.ok(!raw.includes('duplicated history'));
  assert.deepEqual(restore(raw).conversations[0].active_search,{search_type:'image'});
});
