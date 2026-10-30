"""Real HTTP consistency checks, no collection writes. Requires local API :8001."""
import json
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
records=[]
with httpx.Client(timeout=240) as client:
    for name,query in [('646.jpg','make it black'),('635.jpg','short sleeve'),('442.jpg','make it black')]:
        pair={'image':name,'query':query}
        for kind,text in [('image_only',''),('image_text',query)]:
            with (ROOT.parent/'data/images/tshirt'/name).open('rb') as file:
                response=client.post('http://127.0.0.1:8001/api/image-search',files={'image':(name,file,'image/jpeg')},data={'query':text,'limit':'8'})
            response.raise_for_status();body=response.json();pair[kind]=body
            if text:
                assert body['text_analysis']['intent']=='modify'
                for key,values in body['text_analysis']['overrides'].items():
                    for product in body['products']:
                        actual=product['attributes'][key]
                        assert (actual==values if isinstance(values,bool) else
                                any(v in (actual if isinstance(actual,list) else [actual]) for v in values))
                scores=[p['similarity_score'] for p in body['products']]
                assert scores==sorted(scores,reverse=True)
            print(name,kind,len(body['products']),body.get('text_analysis'),flush=True)
        records.append(pair)
        (ROOT/'validation/image_text_results.json').write_text(json.dumps(records,indent=2,ensure_ascii=False))
    cases=[]
    for query,intent in [('make it black and short sleeve','modify'),('make it more futuristic','unsupported'),('make it black and more futuristic','modify'),('Who should I vote for?','unrelated'),('find similar ones','noop')]:
        with (ROOT.parent/'data/images/tshirt/646.jpg').open('rb') as file:
            response=client.post('http://127.0.0.1:8001/api/image-search',files={'image':('646.jpg',file,'image/jpeg')},data={'query':query})
        response.raise_for_status();body=response.json()
        assert body['text_analysis']['intent']==intent,(query,body['text_analysis'])
        if intent in ('unrelated','unsupported'):assert not body['products'] and body['image_analysis'] is None
        if 'futuristic' in query:assert any('futuristic' in part.lower() for part in body['text_analysis']['unsupported_text'])
        if query=='make it black and more futuristic':assert body['text_analysis']['overrides']=={'colors':['black']}
        cases.append({'query':query,'response':body})
        (ROOT/'validation/image_text_cases.json').write_text(json.dumps(cases,indent=2))
        print('case',query,intent,len(body['products']),flush=True)
    (ROOT/'validation/image_text_cases.json').write_text(json.dumps(cases,indent=2))
