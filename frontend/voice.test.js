import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRecognition, createPlayback, createSpeakerButton, speechText } from './voice.js';
import { searchReferences } from './search.js';

function fixture(options = {}) {
  const instances = [], sent = [], states = [], recovered = [];
  class Recognition {
    constructor() { instances.push(this); }
    start() { this.started = true; this.onstart?.(); }
    abort() { this.aborted = true; this.onerror?.({error:'aborted'}); this.onend?.(); }
  }
  let reason = '';
  const voice = createRecognition({platform: { [options.prefixed ? 'webkitSpeechRecognition' : 'SpeechRecognition']: Recognition },
    blocked: () => reason, submit: text => { sent.push(text); return options.submit?.(text); }, recover: text => recovered.push(text), changed: state => states.push(state) });
  return {voice,instances,sent,states,recovered,block: value => { reason = value; }, current: () => instances.at(-1)};
}
function result(recognition, text, final = true, index = 0) {
  const item = [{transcript:text}]; item.isFinal = final;
  const results = Array(index).fill(null); results.push(item);
  recognition.onresult({resultIndex:index,results});
}

test('recognition detects standard, prefixed and unsupported APIs', () => {
  assert.equal(fixture().voice.supported,true); assert.equal(fixture({prefixed:true}).voice.supported,true);
  const sent=[]; const v=createRecognition({platform:{},blocked:()=>'',submit:t=>sent.push(t),recover:()=>{}});
  assert.equal(v.supported,false);v.toggle();assert.deepEqual(sent,[]);
});
test('click activation starts a single English endpointed session and listening indicator', () => {
  const f=fixture();f.voice.toggle();const r=f.current();
  assert.equal(r.started,true);assert.equal(r.lang,'en-US');assert.equal(r.continuous,false);assert.equal(r.interimResults,true);
  assert.equal(f.voice.active,true);assert.ok(f.states.some(s=>s.status==='listening'&&s.active));
});
test('interim and speechend never submit; final plus end automatically sends trimmed text once', () => {
  const f=fixture();f.voice.toggle();const r=f.current();
  result(r,'interim',false);r.onspeechend();assert.deepEqual(f.sent,[]);
  result(r,'  Show me five black T-shirts.  ');assert.deepEqual(f.sent,[]);
  r.onend();r.onend();r.onspeechend();assert.deepEqual(f.sent,['Show me five black T-shirts.']);assert.equal(f.voice.active,false);
});
test('repeated final events replace the same slot and distinct final segments accumulate', () => {
  const f=fixture();f.voice.toggle();const r=f.current();
  result(r,'Show me');result(r,'Show me');result(r,'three more.',true,1);r.onend();
  assert.deepEqual(f.sent,['Show me three more.']);
});
test('empty and interim-only sessions do not submit', () => {
  for(const text of ['', '   ']) {const f=fixture();f.voice.toggle();result(f.current(),text);f.current().onend();assert.deepEqual(f.sent,[]);}
  const f=fixture();f.voice.toggle();result(f.current(),'not final',false);f.current().onend();assert.deepEqual(f.sent,[]);
});
for (const error of ['no-speech','not-allowed','service-not-allowed','network','audio-capture','aborted','unknown']) {
  test(`${error} invalidates even a captured final and restores idle without submission`,()=>{
    const f=fixture();f.voice.toggle();const r=f.current();result(r,'old final');r.onerror({error});r.onend();
    assert.deepEqual(f.sent,[]);assert.equal(f.voice.active,false);assert.ok(f.states.at(-1).text);
    f.voice.toggle();f.current().onend();assert.deepEqual(f.sent,[]);
  });
}
test('second microphone click cancels; late old events cannot affect a new session', () => {
  const f=fixture();f.voice.toggle();const old=f.current();result(old,'canceled');f.voice.toggle();
  assert.equal(old.aborted,true);assert.deepEqual(f.sent,[]);
  f.voice.toggle();result(old,'stale');old.onend();assert.equal(f.voice.active,true);
  result(f.current(),'fresh');f.current().onend();assert.deepEqual(f.sent,['fresh']);
});
test('draft, attachment and in-flight guards prevent activation without mutation',()=>{
  for(const reason of ['Unsent text draft','Pending image attachment','Request in flight']) {
    const f=fixture();f.block(reason);f.voice.toggle();assert.equal(f.instances.length,0);assert.deepEqual(f.sent,[]);assert.equal(f.states.at(-1).text,reason);
  }
});
test('a newly busy composer retains transcript for recovery without sending',()=>{
  const f=fixture();f.voice.toggle();result(f.current(),'Show me three more.');f.block('Wait for the response.');f.current().onend();
  assert.deepEqual(f.sent,[]);assert.deepEqual(f.recovered,['Show me three more.']);assert.match(f.states.at(-1).text,/not sent/);
});
test('rejected submit and overlong transcript recover without repeated attempts',()=>{
  const f=fixture({submit:()=>false});f.voice.toggle();result(f.current(),'query');f.current().onend();f.current().onend();assert.deepEqual(f.recovered,['query']);assert.equal(f.sent.length,1);
  const long=fixture();long.voice.toggle();result(long.current(),'a'.repeat(501));long.current().onend();assert.equal(long.sent.length,0);assert.equal(long.recovered[0].length,501);
});
test('constructor/start failure restores microphone without leaking browser exception',()=>{
  let state;class Broken { start(){throw Error('private browser details');} abort(){} }
  const v=createRecognition({platform:{SpeechRecognition:Broken},blocked:()=>'',submit:()=>assert.fail(),recover:()=>{},changed:s=>state=s});v.toggle();assert.equal(v.active,false);assert.doesNotMatch(state.text,/private/);
});
test('voice result count and pagination text reach the normal search request unchanged',async()=>{
  const original=globalThis.fetch;const requests=[];
  globalThis.fetch=async(url,options)=>{requests.push(JSON.parse(options.body));return {ok:true,json:async()=>({text:'Done',response_id:'r',products:[],search_results:{exact:[],similar:[]}})};};
  try {
    const active_search={search_type:'text',shown_product_ids:['seen']};const jobs=[];
    const f=fixture({submit:text=>{jobs.push(searchReferences({query:text,mode:'auto',active_search}));return true;}});
    for(const text of ['Show me five black oversized T-shirts.','Show me three more.']) {f.voice.toggle();result(f.current(),text);f.current().onend();}
    await Promise.all(jobs);assert.deepEqual(requests.map(r=>r.query),['Show me five black oversized T-shirts.','Show me three more.']);assert.deepEqual(requests[1].active_search,active_search);
  } finally {globalThis.fetch=original;}
});

function playbackFixture() {
  const spoken=[],states=[],notices=[];let cancellations=0;
  class Utterance {constructor(text){this.text=text;}}
  const platform={SpeechSynthesisUtterance:Utterance,speechSynthesis:{speak:u=>spoken.push(u),cancel:()=>{cancellations++;}}};
  const playback=createPlayback({platform,changed:id=>states.push(id),notice:s=>notices.push(s)});
  return {playback,spoken,states,notices,canceled:()=>cancellations};
}
test('synthesis feature detection degrades gracefully',()=>{
  const p=createPlayback({platform:{}});assert.equal(p.supported,false);p.toggle('a','text');p.stop();assert.equal(p.activeId,null);
});
test('speaker starts English playback only on toggle and second click stops',()=>{
  const f=playbackFixture();assert.equal(f.spoken.length,0);f.playback.toggle('a','An explanation.');
  assert.equal(f.spoken[0].text,'An explanation.');assert.equal(f.spoken[0].lang,'en-US');assert.equal(f.spoken[0].rate,1);assert.equal(f.playback.activeId,'a');
  f.playback.toggle('a','An explanation.');assert.equal(f.canceled(),1);assert.equal(f.playback.activeId,null);assert.equal(f.spoken.length,1);
});
test('new speakers cancel old playback and stale end/error/start events cannot clear newer state',()=>{
  const f=playbackFixture();f.playback.toggle('a','first');const old=f.spoken[0];f.playback.toggle('b','second');
  assert.equal(f.canceled(),1);old.onend();old.onerror();old.onstart();assert.equal(f.playback.activeId,'b');assert.equal(f.notices.length,0);
  f.spoken[1].onend();assert.equal(f.playback.activeId,null);
});
test('playback error and conversation/page stop restore state',()=>{
  const f=playbackFixture();f.playback.toggle('a','first');f.spoken[0].onerror();assert.equal(f.playback.activeId,null);assert.equal(f.notices.length,1);
  f.playback.toggle('b','second');f.playback.stop();assert.equal(f.playback.activeId,null);assert.equal(f.canceled(),1);
});
test('speech uses conversational intro/closing without duplicated text or product payload',()=>{
  assert.equal(speechText({text:'I found five designs.',closing_text:'I found five designs.',products:[{product_id:'secret'}]}),'I found five designs.');
  assert.equal(speechText({text:'I found designs.',closing_text:'I found designs. Try another color.'}),'I found designs. Try another color.');
  const text=speechText({text:'Matches:\n1. Product 123\nproduct_id: 123\nimage_path: data/images/tshirt/1.jpg\nsimilarity_score: .9\n{"embedding": [1,2]}',products:[{}],closing_text:'Try another color.'});
  assert.doesNotMatch(text,/123|\.9|embedding|jpg/);assert.match(text,/Try another color/);
  assert.equal(speechText({text:'1. Details\n2. More details',products:[{},{}]}),'I found 2 matching designs for you.');
  assert.equal(speechText({text:'Cotton is breathable and comfortable.'}),'Cotton is breathable and comfortable.');
});
test('speaker button rendering is accessible, optional, and excludes pending/error messages',()=>{
  const f=playbackFixture();let click;
  const doc={createElement:()=>({dataset:{},setAttribute(k,v){this[k]=v;},addEventListener(type,fn){click=fn;}})};
  const entry={id:'reply',status:'complete',text:'Response ready.'};const button=createSpeakerButton(doc,entry,f.playback);
  assert.equal(button.type,'button');assert.equal(button['aria-label'],'Read response aloud');assert.match(button.innerHTML,/<svg/);click();assert.equal(f.playback.activeId,'reply');
  assert.equal(createSpeakerButton(doc,{...entry,status:'pending'},f.playback),null);assert.equal(createSpeakerButton(doc,{...entry,status:'error'},f.playback),null);
  assert.equal(createSpeakerButton(doc,entry,{supported:false}),null);
});
test('app wiring uses the existing submit function and lifecycle hooks, and preserves Send',()=>{
  const app=readFileSync(new URL('./app.js',import.meta.url),'utf8'),html=readFileSync(new URL('./index.html',import.meta.url),'utf8');
  assert.match(app,/submit: text => submitMessage\(text, state.mode, \[\], \{ voice: true \}\)/);
  assert.match(app,/function newChat\(\) \{\s+stopVoice\(\)/);assert.match(app,/stopVoice\(\); interrupt\(\); clearDraft\(\); releaseUploads\(\); state.activeId/);
  assert.match(app,/pagehide.*stopVoice/);assert.match(html,/id="microphone"[^>]*type="button"[^>]*aria-label="Start voice input"/);assert.match(html,/id="send"[^>]*type="submit"/);
});
test('informational bullet explanations remain speakable; raw JSON and fenced payloads do not',()=>{
  assert.equal(speechText({text:'1. Cotton is breathable.\n2. Linen dries quickly.'}),'Cotton is breathable. Linen dries quickly.');
  assert.equal(speechText({text:'{"products":[{"product_id":"123"}]}'}),'');
  assert.equal(speechText({text:'Helpful answer.\n```json\n{"values":[0.1,0.2]}\n```'}),'Helpful answer.');
});
test('synchronous speech failure resets active state and reports a friendly error',()=>{
  let notice='';class Utterance {constructor(text){this.text=text;}}
  const p=createPlayback({platform:{SpeechSynthesisUtterance:Utterance,speechSynthesis:{cancel(){},speak(){throw Error('raw secret');}}},notice:t=>notice=t});
  p.toggle('a','Explanation');assert.equal(p.activeId,null);assert.match(notice,/unavailable/);assert.doesNotMatch(notice,/secret/);
});
