import test from 'node:test';
import assert from 'node:assert/strict';
import { initialState, createConversation, message, applySearchState, serialize, restore, validReference, referenceForRequest, persistState } from './state.js';
import { recentContext } from './context.js';
import { searchReferences } from './search.js';
const reference = (i=0) => ({version:1,dimension:512,model:'test-model',embedding:Array.from({length:512},(_,j)=>j===i?1:0),image_analysis:{}});
const active = {search_type:'image',text_overrides:{colors:['black']},effective_filters:{colors:['black']},shown_product_ids:['1'],shown_point_ids:['1']};
function upload(chat,ref=reference()) {
 const entry=message('assistant','Found designs',{request:{type:'image',attachment_id:'a',file_name:'a.jpg'},status:'complete',products:[]});chat.messages.push(entry);
 applySearchState(chat,entry,{image_reference:ref,active_search:active});return entry;
}
test('reference stored once, survives restore and is excluded from textual context',()=>{
 const state=initialState(),chat=state.conversations[0];chat.messages.push(message('user','Reference image search'));upload(chat);
 const saved=serialize(state);assert.equal((saved.match(/"embedding"/g)||[]).length,1);
 const restored=restore(saved).conversations[0];assert.deepEqual(restored.reference_image,reference());assert.deepEqual(restored.active_search,active);
 assert.ok(!JSON.stringify(recentContext(chat.messages)).includes('embedding'));
 assert.deepEqual(referenceForRequest(restored,{reference_revision:chat.reference_revision}),reference());
});
test('independent chats, new reference resets state and historical replies cannot replace it',()=>{
 const a=createConversation(),b=createConversation();const old=upload(a);upload(b,reference(1));const rev=a.reference_revision;
 upload(a,reference(2));assert.deepEqual(a.reference_image,reference(2));assert.deepEqual(b.reference_image,reference(1));
 assert.throws(()=>referenceForRequest(a,{reference_revision:rev}));
 applySearchState(a,old,{image_reference:reference(3),active_search:active});assert.deepEqual(a.reference_image,reference(2));
 assert.equal(createConversation().reference_image,null);
});
test('old and corrupted references remain readable, quota failure preserves memory',()=>{
 const state=initialState(),chat=state.conversations[0];delete chat.reference_image;assert.equal(restore(serialize(state)).conversations[0].reference_image,null);
 chat.reference_image={...reference(),embedding:[0]};assert.equal(restore(serialize(state)).conversations[0].reference_warning,true);
 upload(chat);assert.equal(persistState({setItem(){throw new Error('quota');}},state),false);assert.deepEqual(chat.reference_image,reference());
 let saved;assert.equal(persistState({setItem(k,v){saved=v;}},state),true);assert.deepEqual(restore(saved).conversations[0].reference_image,reference());
 for(const v of [{...reference(),version:2},{...reference(),embedding:Array(512).fill(0)},{...reference(),embedding:Array(512).fill(Infinity)}])assert.equal(validReference(v),false);
});
test('continuation transport sends reference only to backend JSON, original text route unchanged',async()=>{
 const original=globalThis.fetch;const requests=[];
 globalThis.fetch=async(url,opts)=>{requests.push({url:String(url),body:JSON.parse(opts.body)});return new Response(JSON.stringify({text:'more',response_id:'r',products:[],search_results:{exact:[],similar:[]}}));};
 try {
  await searchReferences({query:'make it black',mode:'auto',reference_image:reference(),active_search:active});
  await searchReferences({query:'Japanese streetwear',mode:'auto'});
  assert.ok(requests[0].url.endsWith('/api/image-search/continue'));assert.deepEqual(requests[0].body.reference_image,reference());
  assert.ok(requests[1].url.endsWith('/api/chat'));assert.ok(!('reference_image' in requests[1].body));
 }finally{globalThis.fetch=original;}
});

test('image-mode state survives history with frozen filters; old state remains compatible',()=>{
 const image=reference();
 for(const mode of ['auto','exact','similar']) {
  const s=initialState(),chat=s.conversations[0];
  const imageState={search_type:'image',mode,effective_image_strategy:mode==='exact'?'strict_attributes':'explicit_text_filtered_similarity',text_overrides:{colors:['black']},effective_filters:{colors:['black']},shown_product_ids:['1'],shown_point_ids:[]};
  const entry=message('assistant','',{request:{type:'image',attachment_id:'a',file_name:'a.jpg',mode}});chat.messages.push(entry);
  applySearchState(chat,entry,{image_reference:image,active_search:imageState});
  const restored=restore(serialize(s)).conversations[0];
  assert.deepEqual(restored.active_search,imageState);assert.deepEqual(restored.reference_image,image);
 }
 const old=initialState();old.conversations[0].active_search={search_type:'image',text_overrides:{},effective_filters:{},shown_product_ids:[],shown_point_ids:[]};
 assert.deepEqual(restore(serialize(old)).conversations[0].active_search,old.conversations[0].active_search);
});

test('Exact clarification keeps the new image reference; invalid mode state is rejected',()=>{
 const s=initialState(),chat=s.conversations[0],entry=message('assistant','',{request:{type:'image',attachment_id:'a',file_name:'a.jpg',mode:'exact'}});chat.messages.push(entry);
 const imageState={search_type:'image',mode:'exact',effective_image_strategy:'attributes_required',text_overrides:{},effective_filters:{},shown_product_ids:[],shown_point_ids:[]};
 applySearchState(chat,entry,{intent:'clarification',effective_image_strategy:'attributes_required',image_reference:reference(),active_search:imageState});
 assert.ok(chat.reference_image);assert.equal(chat.active_search.mode,'exact');
 const bad=structuredClone(s);bad.conversations[0].active_search.mode='bogus';assert.equal(restore(serialize(bad)).conversations[0].active_search,null);
});
