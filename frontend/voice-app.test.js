// Small DOM/event fixture exercises the real app wiring without browser hardware or paid calls.
import test from 'node:test';
import assert from 'node:assert/strict';

class Element {
  constructor() { this.children=[];this.dataset={};this.listeners={};this.style={};this.value='';this.hidden=false;this.disabled=false;this.scrollHeight=40;this.attrs={};this.className='';this.classes=new Set();this.classList={toggle:(c,on)=>on?this.classes.add(c):this.classes.delete(c),add:c=>this.classes.add(c),remove:c=>this.classes.delete(c)}; }
  set innerHTML(value) {this.markup=value;this.children=[];}
  get innerHTML() {return this.markup||'';}
  setAttribute(k,v) {this.attrs[k]=v;}
  addEventListener(k,fn) {(this.listeners[k]??=[]).push(fn);}
  fire(k,event={}) {for(const fn of this.listeners[k]||[])fn({preventDefault(){},...event});}
  append(child) {this.children.push(child);}
  replaceChildren(...children) {this.children=children;}
  focus() {}
  close() {this.fire('close');}
  showModal() {}
  querySelectorAll(selector) {
    const all=this.children.flatMap(c=>[c,...c.querySelectorAll('*')]);
    if(selector==='*')return all;
    if(selector==='[data-speech-id]')return all.filter(c=>c.dataset.speechId);
    if(selector==='.reply-action')return all.filter(c=>c.className==='reply-action');
    return [];
  }
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const final=(r,text)=>{const item=[{transcript:text}];item.isFinal=true;r.onresult({resultIndex:0,results:[item]});};

test('real app voice events reuse submission, drafts, attachments, persistence and conversation lifecycle',async t=>{
  const saved=Object.fromEntries(['document','window','localStorage','fetch'].map(k=>[k,globalThis[k]]));
  const elements=new Map();const get=s=>{if(!elements.has(s))elements.set(s,new Element());return elements.get(s);};
  const modes=['auto','exact','similar'].map(value=>Object.assign(new Element(),{value}));
  const recognition=[],spoken=[];let cancels=0;
  class Recognition {constructor(){recognition.push(this);}start(){this.onstart();}abort(){this.onend?.();}}
  class Utterance {constructor(text){this.text=text;}}
  const window=new Element();Object.assign(window,{SpeechRecognition:Recognition,SpeechSynthesisUtterance:Utterance,speechSynthesis:{speak:u=>spoken.push(u),cancel:()=>cancels++}});
  const storage=new Map();const requests=[];
  globalThis.window=window;
  globalThis.document=Object.assign(new Element(),{querySelector:s=>s.startsWith('[name="mode"]')?modes.find(m=>s.includes(m.value)):get(s),querySelectorAll:s=>s==='[name="mode"]'?modes:[],createElement:()=>new Element()});
  globalThis.localStorage={getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v)};
  globalThis.fetch=async(url,options)=>{requests.push(JSON.parse(options.body));return {ok:true,json:async()=>({text:'Here is a useful explanation.',closing_text:'',intent:'informational',response_id:'response',products:[],search_results:{exact:[],similar:[]}})};};
  try {
    await import('./app.js');
    assert.equal(get('#voice-mode').attrs['aria-pressed'], 'false');
    assert.equal(get('#voice-mode').textContent, 'Voice Mode: Off');
    await t.test('final end sends once through app, without clicking Send, and persists a normal turn',async()=>{
      get('#microphone').fire('click');const r=recognition.at(-1);final(r,'Show me five black oversized T-shirts.');r.onend();r.onend();await tick();
      assert.equal(requests.length,1);assert.equal(requests[0].query,'Show me five black oversized T-shirts.');assert.equal(requests[0].mode,'auto');
      const state=JSON.parse([...storage.values()][0]);assert.equal(state.conversations.at(-1).messages[0].text,requests[0].query);assert.deepEqual(state.conversations.at(-1).messages[0].attachments,[]);
    });
    await t.test('pending request disables microphone and draft text is preserved',async()=>{
      get('#query').value='Unsent draft';get('#query').fire('input');assert.equal(get('#microphone').disabled,true);get('#microphone').fire('click');assert.equal(recognition.length,1);assert.equal(get('#query').value,'Unsent draft');
      get('#query').value='';get('#query').fire('input');get('#microphone').fire('click');final(recognition.at(-1),'Show me three more.');recognition.at(-1).onend();assert.equal(get('#microphone').disabled,true);await tick();assert.equal(requests.at(-1).query,'Show me three more.');
    });
    await t.test('speaker controls stop old audio, and New Chat cancels recognition/playback',()=>{
      let buttons=get('#messages').querySelectorAll('[data-speech-id]');assert.equal(buttons.length,2);
      buttons[0].fire('click');assert.equal(spoken.length,1);assert.equal(buttons[0].attrs['aria-pressed'],'true');buttons[1].fire('click');assert.equal(spoken.length,2);assert.equal(cancels,1);
      buttons[1].fire('click');assert.equal(cancels,2);get('#microphone').fire('click');const r=recognition.at(-1);final(r,'must not submit');get('#new-chat').fire('click');r.onend();assert.equal(requests.length,2);assert.equal(get('#messages').children.length,0);
    });
    await t.test('pending image attachment blocks voice without upload or discarding it',()=>{
      get('#file-input').fire('change',{target:{files:[new File(['image'],'reference.jpg',{type:'image/jpeg'})],value:'reference.jpg'}});
      assert.equal(get('#microphone').disabled,true);assert.match(get('#draft-attachments').innerHTML,/reference.jpg/);const count=recognition.length;get('#microphone').fire('click');assert.equal(recognition.length,count);assert.equal(requests.length,2);get('#new-chat').fire('click');
    });
    await t.test('switching existing conversations stops playback and recognition',()=>{
      get('#open-history').fire('click');const item=get('#history-list').children.find(c=>c.className==='history-item');assert.ok(item);item.fire('click');
      const button=get('#messages').querySelectorAll('[data-speech-id]')[0];button.fire('click');const before=cancels;get('#open-history').fire('click');get('#history-list').children.find(c=>c.className==='history-item').fire('click');assert.equal(cancels,before+1);
      get('#microphone').fire('click');const r=recognition.at(-1);final(r,'do not send');get('#open-history').fire('click');get('#history-list').children.find(c=>c.className==='history-item').fire('click');r.onend();assert.equal(requests.length,2);
    });
    await t.test('pagehide cancels a final transcript without submitting',()=>{
      get('#microphone').fire('click');const r=recognition.at(-1);final(r,'do not send');window.fire('pagehide');r.onend();assert.equal(requests.length,2);
    });
    const submitVoice = text => { get('#microphone').fire('click'); const r=recognition.at(-1); final(r,text); r.onend(); return r; };
    const normalFetch=globalThis.fetch;
    const response=()=>({ok:true,json:async()=>({text:'A clean assistant reply.',response_id:'r',intent:'informational',products:[],search_results:{exact:[],similar:[]}})});
    await t.test('mode defaults OFF and historical renders never auto-play',()=>{
      assert.equal(get('#voice-mode').attrs['aria-pressed'],'false');const n=spoken.length;window.fire('pageshow',{persisted:true});assert.equal(spoken.length,n);
    });
    await t.test('enabled voice reply auto-speaks exactly once after render and blocks microphone',async()=>{
      get('#voice-mode').fire('click');assert.equal(get('#voice-mode').attrs['aria-pressed'],'true');
      const before=spoken.length, listening=recognition.length;const r=submitVoice('Show me five black T-shirts.');r.onend();await tick();
      assert.equal(spoken.length,before+1);assert.equal(get('#messages').querySelectorAll('[data-speech-id]').at(-1).attrs['aria-pressed'],'true');
      assert.equal(get('#microphone').disabled,true);get('#microphone').fire('click');assert.equal(recognition.length,listening+1);
      const data=JSON.parse([...storage.values()][0]);assert.ok(!JSON.stringify(data).includes('autoSpeak'));assert.ok(!JSON.stringify(data).includes('speechRevision'));assert.ok(!JSON.stringify(data).includes('voiceMode'));
    });
    await t.test('completion restores mic but never automatically re-listens; next voice turn speaks',async()=>{
      const n=recognition.length;spoken.at(-1).onend();assert.equal(get('#microphone').disabled,false);assert.equal(recognition.length,n);
      const before=spoken.length;submitVoice('Show me three more.');await tick();assert.equal(spoken.length,before+1);assert.equal(requests.at(-1).query,'Show me three more.');spoken.at(-1).onend();
    });
    await t.test('typed reply with mode ON does not auto-speak',async()=>{
      const n=spoken.length;get('#query').value='A manually typed question';get('#query').fire('input');get('#message-form').fire('submit');await tick();assert.equal(spoken.length,n);
    });
    await t.test('mode OFF stops automatic speech and later voice replies stay manual',async()=>{
      submitVoice('A voice question');await tick();const n=spoken.length,before=cancels;
      get('#voice-mode').fire('click');assert.equal(get('#voice-mode').attrs['aria-pressed'],'false');assert.equal(cancels,before+1);assert.equal(get('#microphone').disabled,false);
      submitVoice('Normal microphone query');await tick();assert.equal(spoken.length,n);
      get('#messages').querySelectorAll('[data-speech-id]').at(-1).fire('click');assert.equal(spoken.length,n+1);spoken.at(-1).onend();
    });
    await t.test('OFF then ON cannot revive an in-flight auto-speech entitlement',async()=>{
      get('#voice-mode').fire('click');let finish;globalThis.fetch=()=>new Promise(resolve=>finish=resolve);const n=spoken.length;
      submitVoice('Slow voice request');get('#voice-mode').fire('click');get('#voice-mode').fire('click');finish(response());await tick();assert.equal(spoken.length,n);globalThis.fetch=normalFetch;
    });
    await t.test('typing a draft suppresses delayed auto-speech and preserves the draft',async()=>{
      let finish;globalThis.fetch=()=>new Promise(resolve=>finish=resolve);const n=spoken.length;submitVoice('Another slow request');
      get('#query').value='A new draft';get('#query').fire('input');finish(response());await tick();assert.equal(spoken.length,n);assert.equal(get('#query').value,'A new draft');
      get('#query').value='';get('#query').fire('input');globalThis.fetch=normalFetch;
    });
    await t.test('failed API request never auto-speaks or repeats the request',async()=>{
      let count=0;globalThis.fetch=async()=>{count++;return {ok:false,status:500};};const n=spoken.length;submitVoice('A failed request');await tick();assert.equal(spoken.length,n);assert.equal(count,1);globalThis.fetch=normalFetch;
    });
    await t.test('switching chats prevents a late response from speaking',async()=>{
      let finish;globalThis.fetch=()=>new Promise(resolve=>finish=resolve);const n=spoken.length;submitVoice('A request before switching');
      get('#open-history').fire('click');get('#history-list').children.find(c=>c.className==='history-item').fire('click');finish(response());await tick();assert.equal(spoken.length,n);globalThis.fetch=normalFetch;
    });
    await t.test('automatic speech errors leave rendered response available and do not resubmit',async()=>{
      submitVoice('A reply to test playback failure');await tick();const n=requests.length;
      const button=get('#messages').querySelectorAll('[data-speech-id]').at(-1);assert.equal(button.attrs['aria-pressed'],'true');spoken.at(-1).onerror();
      assert.equal(button.attrs['aria-pressed'],'false');assert.equal(get('#microphone').disabled,false);assert.equal(requests.length,n);assert.ok(get('#messages').children.length);
    });
    await t.test('active automatic speaker button stops playback; stale events cannot restart listening',async()=>{
      submitVoice('One final reply');await tick();const old=spoken.at(-1),n=recognition.length;get('#messages').querySelectorAll('[data-speech-id]').at(-1).fire('click');
      assert.equal(get('#microphone').disabled,false);old.onend();old.onstart();assert.equal(recognition.length,n);
    });
    await t.test('unified image modes remain selectable and voice refinement carries mode plus original reference',async()=>{
      const ref={version:1,dimension:512,model:'fixture',embedding:[1,...Array(511).fill(0)],image_analysis:{}};
      let captured,upload=true;
      globalThis.fetch=async(url,options)=>{
        if(options.body instanceof FormData) {
          captured={url:String(url),mode:options.body.get('mode'),query:options.body.get('query'),file:options.body.get('image')};
          return {ok:true,json:async()=>({text:'Image results.',closing_text:'',search_type:'image',intent:'search',products:[],image_reference:ref,
            active_search:{search_type:'image',mode:captured.mode,effective_image_strategy:'pure_image_similarity',text_overrides:{},effective_filters:{},shown_product_ids:[],shown_point_ids:[]}})};
        }
        captured={url:String(url),...JSON.parse(options.body)};
        return {ok:true,json:async()=>({text:'Refined image results.',closing_text:'',response_id:'r',search_type:'image',intent:'search',search_strategy:'exact',products:[],search_results:{exact:[],similar:[]},
          effective_mode:'exact',effective_image_strategy:'strict_attributes',active_search:{search_type:'image',mode:'exact',effective_image_strategy:'strict_attributes',text_overrides:{colors:['black']},effective_filters:{colors:['black']},shown_product_ids:[],shown_point_ids:[]}})};
      };
      modes.find(m=>m.value==='similar').fire('change');
      get('#file-input').fire('change',{target:{files:[new File(['image'],'reference.jpg',{type:'image/jpeg'})],value:'reference.jpg'}});
      assert.equal(get('.modes').disabled,false);
      get('#message-form').fire('submit');await tick();assert.equal(captured.mode,'similar');assert.match(captured.url,/api\/image-search$/);
      let markup=get('#messages').children.at(-1).innerHTML;assert.match(markup,/reference.jpg/);assert.doesNotMatch(markup,/<p>|Image search:/);assert.equal(captured.file.name,'reference.jpg');
      modes.find(m=>m.value==='exact').fire('change');submitVoice('Make it black.');await tick();
      assert.equal(captured.mode,'exact');assert.equal(captured.active_search.mode,'similar');assert.deepEqual(captured.reference_image,ref);assert.match(captured.url,/image-search\/continue$/);
      spoken.at(-1).onend();
      const stored=JSON.parse([...storage.values()][0]);assert.equal(stored.conversations.find(c=>c.id===stored.activeId).active_search.mode,'exact');
      modes.find(m=>m.value==='auto').fire('change');
      get('#file-input').fire('change',{target:{files:[new File(['image'],'new.jpg',{type:'image/jpeg'})],value:'new.jpg'}});get('#query').value='get me some short-sleeves version';get('#message-form').fire('submit');await tick();assert.equal(captured.mode,'auto');assert.equal(captured.query,'get me some short-sleeves version');
      markup=get('#messages').children.at(-1).innerHTML;assert.match(markup,/<p>get me some short-sleeves version<\/p>/);assert.doesNotMatch(markup,/Image search:/);assert.match(markup,/new.jpg/);
      const newState=JSON.parse([...storage.values()][0]);assert.deepEqual(newState.conversations.find(c=>c.id===newState.activeId).active_search.text_overrides,{});
      globalThis.fetch=normalFetch;
    });
    await t.test('unsupported synthesis disables Voice Mode without disabling speech input',async()=>{
      delete window.speechSynthesis;delete window.SpeechSynthesisUtterance;
      await import('./app.js?unsupported-voice-mode');assert.equal(get('#voice-mode').disabled,true);assert.equal(get('#voice-mode').attrs['aria-pressed'],'false');assert.equal(get('#microphone').disabled,false);
    });
  } finally {for(const [k,v]of Object.entries(saved)){if(v===undefined)delete globalThis[k];else globalThis[k]=v;}}
});
