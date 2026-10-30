"""Opt-in REAL LLM/Qdrant HTTP checks; not browser automation. May incur API cost."""
import argparse
import json
from pathlib import Path
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--run-live',action='store_true')
args=parser.parse_args()
if not args.run_live: parser.error('Pass --run-live to authorize real API requests.')
root=Path(__file__).resolve().parents[1]
records=[]
with httpx.Client(base_url='http://127.0.0.1:8001',timeout=180) as client:
    cases=[('Give me two black T-shirt designs',2,'auto'),('找七件黑色T恤',7,'auto'),
           ('给我三件白色T恤',3,'auto'),('給我三張白色T恤圖片',3,'auto'),
           ('Show me size 10 T-shirts',None,'auto'),('Show me 2025 fashion trends',None,'auto'),
           ('Find shirts with the number 7 printed on them',None,'similar'),
           ('Show me 3/4 sleeve shirts',None,'auto'),('Find shirts under $20',None,'auto'),
           ('Show me a few minimalist shirts',None,'auto'),('Show me zero T-shirts',0,'auto'),
           ('Show me minus five shirts',-5,'auto'),('Show me a million designs',1000000,'auto'),
           ('Show me 3 black T-shirts',3,'exact'),('Show me 5 Japanese streetwear T-shirts',5,'similar'),
           ('Show me 3 black T-shirts with Japanese streetwear inspiration and alternatives',3,'auto')]
    for query,count,mode in cases:
        response=client.post('/api/chat',json={'query':query,'mode':mode});response.raise_for_status();r=response.json()
        record={k:r.get(k) for k in ('requested_count','effective_count','count_capped','intent','resolved_query','search_strategy','text','has_more')}
        record.update(query=query,mode=mode,actual=len(r['products']),ids=[str(p.get('product_id',p.get('point_id'))) for p in r['products']])
        record['passed']=r['requested_count']==count and len(r['products'])<=min(count if count and count>0 else 8,8)
        if count is not None and count<=0: record['passed'] &= r['intent']=='clarification' and not r['products']
        if count and count>8: record['passed'] &= r['count_capped'] and 'up to 8' in r['text']
        records.append(record)
        (root/'validation/dynamic_count_api.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(record,ensure_ascii=False),flush=True)
assert all(r['passed'] for r in records),'See dynamic_count_api.json for mismatches'

# Same real active search; Chinese/Cantonese pagination must not repeat IDs.
records=[]
with httpx.Client(base_url='http://127.0.0.1:8001',timeout=180) as client:
    state=None
    seen=set()
    for query,number in [('Show me 3 black shirts',3),('有冇兩件其他款？',2),('再給我五件',5)]:
        response=client.post('/api/chat',json={'query':query,'active_search':state})
        response.raise_for_status()
        result=response.json()
        ids=[str(p['product_id']) for p in result['products']]
        record={key:result.get(key) for key in ('requested_count','effective_count','resolved_query','relation_to_context','text')}
        record.update(query=query,actual=len(ids),ids=ids,
            passed=result['requested_count']==number and len(ids)<=number and not seen.intersection(ids))
        records.append(record)
        seen.update(ids)
        state=result['active_search']
    (root/'validation/dynamic_count_cantonese.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
assert all(r['passed'] for r in records),'See dynamic_count_cantonese.json for mismatches'

