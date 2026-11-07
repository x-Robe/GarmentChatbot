import test from 'node:test';
import assert from 'node:assert/strict';
import { submissionPlan, searchImage } from './search.js';
import { API_BASE_URL } from './config.js';
import { initialState, message, serialize, restore } from './state.js';
import { carouselState, pageProducts, detailRows } from './products.js';
import { recentContext } from './context.js';
const file = () => new File(['image bytes'], 'reference.png', {type:'image/png'});
const payload = () => ({text:'Real image intro',search_type:'image',closing_text:'Real image closing',products:Array.from({length:8},(_,i)=>({product_id:String(i),similarity_score:.9-i*.05,attributes:{colors:['black']},image_url:`/images/tshirt/${i}.jpg`,match_type:'similar'}))});

test('image only uses original File FormData, shared base, selected mode, no context or Content-Type', async t => {
  const original = file();
  assert.equal(submissionPlan('', [original]).type,'image');
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    assert.equal(String(url),`${API_BASE_URL}/api/image-search`);
    assert.equal(options.headers,undefined);
    assert.ok(options.body instanceof FormData);
    assert.equal(options.body.get('image'),original);
    assert.equal(options.body.get('limit'),null);
    assert.deepEqual([...options.body.keys()],['mode','image']);
    assert.equal(options.body.get('mode'),'exact');
    return new Response(JSON.stringify(payload()));
  });
  const result=await searchImage({file:original,mode:'exact',context:[{text:'ignored'}]});
  assert.equal(result.text,payload().text); assert.equal(result.closing_text,payload().closing_text);
  assert.deepEqual(result.products.map(p=>p.product_id),payload().products.map(p=>p.product_id));
});
test('text only and removal restore text submission; mixed input routes to image transport',t=>{
  const fetch=t.mock.method(globalThis,'fetch',()=>assert.fail('must not send'));
  assert.equal(submissionPlan('black tee',[]).type,'text');
  assert.equal(submissionPlan('black tee',[file()]).type,'image');
  assert.equal(submissionPlan('',[]).type,'text');
  assert.equal(fetch.mock.callCount(),0);
});
test('multiple images and PDF are explicitly blocked',()=>{
  assert.throws(()=>submissionPlan('',[file(),file()]),/one image/);
  assert.throws(()=>submissionPlan('',[{type:'application/pdf'}]),/JPEG, PNG, or WebP image/);
});
test('frontend rejects unsupported and oversized files without network',async t=>{
  const fetch=t.mock.method(globalThis,'fetch',()=>assert.fail('must not send'));
  await assert.rejects(searchImage({file:new File(['bad'],'bad.gif',{type:'image/gif'})}),/JPEG, PNG, or WebP/);
  await assert.rejects(searchImage({file:{type:'image/png',size:10*1024*1024+1}}),/10 MiB/);
  assert.equal(fetch.mock.callCount(),0);
});
test('400/413/422/500/503 have friendly errors, never arbitrary server text',async t=>{
  for(const [status,detail,pattern] of [
    [400,'Image dimensions are too large (maximum 20 million pixels).',/20 million pixels/],
    [400,'Upload a JPEG, PNG, or WebP image.',/JPEG, PNG, or WebP/],
    [400,'secret traceback',/couldn't read/],[413,'secret',/10 MiB/],[422,'secret',/select/],
    [500,'secret',/temporarily unavailable/],[503,'secret',/temporarily unavailable/]]){
    t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify({detail}),{status}));
    await assert.rejects(searchImage({file:file()}),pattern); t.mock.restoreAll();
  }
});
test('backend unavailable and cancellation stay controlled',async t=>{
  t.mock.method(globalThis,'fetch',async()=>{throw new TypeError('internal');});
  await assert.rejects(searchImage({file:file()}),/Cannot connect to the Garment backend/);
  t.mock.restoreAll();
  const controller=new AbortController();controller.abort();
  t.mock.method(globalThis,'fetch',async(_,options)=>{assert.equal(options.signal,controller.signal);throw new DOMException('Aborted','AbortError');});
  await assert.rejects(searchImage({file:file(),signal:controller.signal}),{name:'AbortError'});
});
test('malformed image response fails safely',async t=>{
  for(const body of ['{bad','{}',JSON.stringify({...payload(),products:[null]})]){
    t.mock.method(globalThis,'fetch',async()=>new Response(body));
    await assert.rejects(searchImage({file:file()}),/Please try again/); t.mock.restoreAll();
  }
});
test('image history keeps eight products and closing without original file or blob preview',async t=>{
  t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(payload())));
  const result=await searchImage({file:file()}); const state=initialState();
  state.conversations[0].messages.push(message('user','Image search: reference.png',{search_type:'image',attachments:[{id:'a',name:'reference.png',type:'image/png',size:11,file:file(),previewUrl:'blob:local'}]}));
  state.conversations[0].messages.push(message('assistant',result.text,{...result,request:{type:'image',attachment_id:'a',file_name:'reference.png'},status:'complete'}));
  const raw=serialize(state);assert.ok(!raw.includes('blob:local'));assert.ok(!raw.includes('image bytes'));
  const restored=restore(raw).conversations[0].messages[1];
  assert.equal(restored.closing_text,result.closing_text);assert.equal(restored.products.length,8);
  const carousel=carouselState(8);assert.equal(pageProducts(restored.products,carousel.page).length,4);
  carousel.move(1); assert.equal(pageProducts(restored.products,carousel.page)[0].product_id,'4');
  carousel.select(4);assert.equal(carousel.selected,4);assert.ok(detailRows(restored.products[4]).some(([k,v])=>k==='Match'&&v==='Similar'));
});
test('refresh of pending image request asks for original image, not text retry',()=>{
  const state=initialState();state.conversations[0].messages.push(message('assistant','',{status:'pending',request:{type:'image',attachment_id:'a',file_name:'reference.png'}}));
  const entry=restore(serialize(state)).conversations[0].messages[0];
  assert.equal(entry.status,'interrupted');assert.match(entry.text,/Select the original image again/);
});
test('image turns expose text only, with reference marker and no filenames',()=>{
  assert.deepEqual(recentContext([message('user','Image search: reference.png',{search_type:'image',attachments:[{id:'a',name:'reference.png',type:'image/png'}]}),message('assistant','Found images',{search_type:'image',request:{type:'image',attachment_id:'a',file_name:'reference.png',query:''}})]),[{role:'user',text:'Reference image search'},{role:'assistant',text:'Found images'}]);
});

test('mixed FormData carries query and selected mode and history preserves modification', async t => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(String(url), `${API_BASE_URL}/api/image-search`);
    assert.equal(options.body.get('query'), 'make it black');
    assert.equal(options.body.get('mode'), 'auto');
    return new Response(JSON.stringify(payload()));
  });
  const result = await searchImage({file:file(), query:'make it black'});
  const state = initialState();
  state.conversations[0].messages.push(message('user','Image search: reference.png — make it black',{search_type:'image'}));
  state.conversations[0].messages.push(message('assistant',result.text,{...result,request:{type:'image',attachment_id:'a',file_name:'reference.png',query:'make it black'},status:'complete'}));
  const saved=restore(serialize(state)).conversations[0].messages;
  assert.match(saved[0].text,/make it black/);
  assert.equal(saved[1].request.query,'make it black');
  assert.equal(saved[1].products.length,8);
});

test('all image modes propagate for image-only and mixed submissions; Exact products remain Exact', async t => {
  for (const mode of ['auto','exact','similar']) {
    for (const query of ['', 'make it black']) {
      t.mock.method(globalThis,'fetch',async(_,options)=>{
        assert.equal(options.body.get('mode'),mode);
        assert.equal(options.body.get('query'),query || null);
        const data=payload();data.requested_mode=mode;data.effective_mode=mode;
        data.effective_image_strategy=mode==='exact'?'strict_attributes':'pure_image_similarity';
        data.products=data.products.map(p=>({...p,match_type:mode==='exact'?'exact':'similar'}));
        return new Response(JSON.stringify(data));
      });
      const result=await searchImage({file:file(),query,mode});
      assert.equal(result.effective_mode,mode);assert.equal(result.products[0].match_type,mode==='exact'?'exact':'similar');
      t.mock.restoreAll();
    }
  }
});
