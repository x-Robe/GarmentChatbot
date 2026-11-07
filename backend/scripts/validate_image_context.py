"""Opt-in real API validation. Saves metadata/IDs only, never raw vectors."""
import json
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
records=[]
client=httpx.Client(base_url='http://127.0.0.1:8001',timeout=240)

def upload(name,query=''):
    with (ROOT.parent/f'data/images/tshirt/{name}.jpg').open('rb') as image:
        response=client.post('/api/image-search',files={'image':(f'{name}.jpg',image,'image/jpeg')},data={'query':query})
    response.raise_for_status();return response.json()

def record(query,result):
    ids=[str(p['product_id']) for p in result['products']]
    records.append({'query':query,'ids':ids,'text':result['text'],'relation':result.get('relation_to_context'),
        'active_search':result.get('active_search'),'image_analysis':result.get('image_analysis')})
    (ROOT/'validation/image_context_api.json').write_text(json.dumps(records,indent=2,ensure_ascii=False))
    print(query,result.get('relation_to_context'),ids,flush=True)
    return ids

r=upload('646');ref=r['image_reference'];state=r['active_search'];context=[]
assert len(ref['embedding'])==512
assert [str(p['product_id']) for p in r['products']]==['646','411','516','816','175','631','745','941']
record('image-only 646',r)
print('reference JSON bytes',len(json.dumps(ref).encode()),flush=True)
original=json.dumps(ref,sort_keys=True)

def ask(query):
    global state
    response=client.post('/api/image-search/continue',json={'query':query,'mode':'auto','context':context,'active_search':state,'reference_image':ref})
    response.raise_for_status();result=response.json();state=result['active_search']
    context.extend([{'role':'user','text':query},{'role':'assistant','text':result['text']}])
    assert json.dumps(ref,sort_keys=True)==original
    record(query,result);return result

seen=set(state['shown_product_ids'])
for _ in range(2):
    r=ask('show me more');ids=set(str(p['product_id']) for p in r['products'])
    assert not ids&seen;seen|=ids
r=ask('make it black');assert state['text_overrides']=={'colors':['black']}
seen=set(state['shown_product_ids']);r=ask('show me more');assert not seen&set(str(p['product_id']) for p in r['products'])
r=ask('make it long sleeve');assert state['text_overrides']=={'colors':['black'],'sleeve':['long sleeve']}
r=ask('actually make it white again');assert state['text_overrides']=={'colors':['white'],'sleeve':['long sleeve']}
r=ask('remove the color requirement');assert state['text_overrides']=={'sleeve':['long sleeve']}
r=ask('make it more futuristic');assert r['intent']=='clarification';assert state['text_overrides']=={'sleeve':['long sleeve']}
r=ask('what is a mock neck?');assert r['intent']=='informational' and not r['products']
r=ask('Who should I vote for?');assert r['intent']=='unrelated' and not r['products']
r=ask('show me Japanese streetwear T-shirts');assert state['search_type']=='text'
r=ask('make them darker');assert state['search_type']=='text'
seen=set(state['shown_product_ids']);r=ask('show me more');assert not seen&set(str(p['product_id']) for p in r['products'])
print('All real API assertions passed.',flush=True)
