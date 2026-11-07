"""Opt-in real API validation. Uses configured LLM and Qdrant; no dataset writes."""
import json
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
records=[]

def ask(client, history, active, query, mode='auto'):
    response=client.post('http://127.0.0.1:8001/api/chat',json={'query':query,'mode':mode,'context':history,'active_search':active})
    response.raise_for_status();body=response.json()
    records.append({'query':query,'response':body})
    (ROOT/'validation/pagination_api.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    history.extend([{'role':'user','text':query},{'role':'assistant','text':body['text']+'\n'+body['closing_text']}])
    print(query,body['relation_to_context'],body['search_strategy'],[p['product_id'] for p in body['products']],flush=True)
    return body

with httpx.Client(timeout=240) as client:
    history=[]
    r=ask(client,history,None,'show me black oversized t-shirts')
    seen=set(str(p['product_id']) for p in r['products'])
    for query in ['show me more','more please','any other designs?','show another 8','give me different ones','还有其他的吗？','再给我看看','有冇其他款？']:
        before=r['active_search'];r=ask(client,history,before,query)
        assert r['relation_to_context']=='more_results'
        assert r['resolved_query']==before['resolved_query']
        ids={str(p['product_id']) for p in r['products']}
        assert not ids & seen;seen.update(ids)
    for mode in ('exact','similar'):
        history=[];r=ask(client,history,None,'black t-shirts',mode)
        previous={str(p['product_id']) for p in r['products']}
        r=ask(client,history,r['active_search'],'show me more','auto')
        assert r['search_strategy']==mode
        assert not previous & {str(p['product_id']) for p in r['products']}
    history=[];r=ask(client,history,None,'black oversized t-shirts with Japanese streetwear inspiration')
    assert r['search_strategy']=='both'
    old=r['active_search'];r=ask(client,history,old,'more please')
    assert r['search_strategy']=='both'
    assert not set(old['shown_product_ids']) & {str(p['product_id']) for p in r['products']}
    r=ask(client,[],None,'show me more');assert r['intent']=='clarification' and not r['products']
    r=ask(client,[],{'search_type':'image'},'show me more');assert r['intent']=='clarification' and not r['products']
