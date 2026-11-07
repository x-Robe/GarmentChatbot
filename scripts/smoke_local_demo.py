"""Real public-tunnel acceptance checks. Requires a live credentialed demo.

Sends paid-provider requests, reads Qdrant via existing API; never writes Qdrant.
Outputs counts/timing only, no prompts, private environment or provider responses.
"""
import argparse
import json
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import uuid

from local_demo import ROOT, RUNTIME, ask


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-live', action='store_true', help='Run real requests consuming approved provider points')
    parser.add_argument('--origin', help='Explicit HTTPS cloud backend; leaves the Mac supervisor untouched')
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error('--confirm-live is required; these are real integrations, not mocks')
    if args.origin:
        parsed = urlparse(args.origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise ValueError('--origin must be a plain HTTPS API origin')
        state = {'tunnel': args.origin.rstrip('/')}
        output = RUNTIME / 'cloudrun/live-tests.json'
    else:
        state = ask('status')
        if not state or state.get('transport_only') or not state.get('tunnel'):
            raise ValueError('Start the normal credentialed demo first; transport-only cannot pass live tests')
        output = RUNTIME / 'live-tests.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    origin = state['tunnel']
    results, checked_images = [], set()

    def rss():
        if not state.get('backend_pid'): return None
        try:
            return int(subprocess.check_output(['ps', '-o', 'rss=', '-p', str(state['backend_pid'])],text=True).strip()) * 1024
        except Exception:
            return None

    def call(label, path, payload=None, image=False):
        started = time.monotonic()
        if image:
            boundary = uuid.uuid4().hex
            data = bytearray()
            for key, value in payload.items():
                data.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            data.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="941.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode())
            data.extend((ROOT / 'data/images/tshirt/941.jpg').read_bytes())
            data.extend(f'\r\n--{boundary}--\r\n'.encode())
            content_type = 'multipart/form-data; boundary=' + boundary
        else:
            data = json.dumps(payload).encode() if payload is not None else None
            content_type = 'application/json'
        request = Request(origin + path, data=data, headers={'Content-Type': content_type, 'Origin': 'https://garmentchatbot.web.app'})
        row = {'test': label, 'before_rss_bytes': rss()}
        try:
            with urlopen(request, timeout=180) as response:
                body = json.load(response)
                row.update(status=response.status, cors=response.headers.get('Access-Control-Allow-Origin') == 'https://garmentchatbot.web.app')
            products = body.get('products', [])
            row['products'] = len(products)
            for product in products:
                path = product.get('image_url')
                if not path: raise ValueError('Returned product has no mapped image URL')
                url = urljoin(origin + '/', path)
                if urlparse(url).netloc != urlparse(origin).netloc:
                    raise ValueError('Returned product points outside current tunnel origin')
                if url not in checked_images:
                    with urlopen(url, timeout=30) as image_response:
                        if image_response.status != 200 or not image_response.headers.get('Content-Type', '').startswith('image/'):
                            raise ValueError('Returned product image unavailable')
                        image_response.read()
                    checked_images.add(url)
            row['passed'] = row['cors'] and isinstance(body, dict)
            if not row['passed']: raise ValueError('Unexpected CORS or response')
            return body
        except HTTPError as error:
            row.update(status=error.code, passed=False)
            raise ValueError(label + ': HTTP ' + str(error.code)) from None
        except Exception as error:
            row.update(passed=False, error_type=type(error).__name__)
            raise
        finally:
            row.update(seconds=round(time.monotonic()-started,3), after_rss_bytes=rss())
            results.append(row)
            output.write_text(json.dumps({'origin':origin,'results':results,'unique_images_verified':len(checked_images)},indent=2)+'\n')
            print(json.dumps(row),flush=True)

    first = None
    for mode in ('auto','exact','similar'):
        response = call('text-'+mode, '/api/chat', {'query':'show me 4 black short sleeve t-shirts','mode':mode})
        if mode == 'auto': first = response
    if not any(row.get('products',0) for row in results):
        raise ValueError('No real text products returned; relevance/integration needs diagnosis')
    context=[{'role':'user','text':'show me 4 black short sleeve t-shirts'}, {'role':'assistant','text':first['text']}]
    refined=call('multi-turn-refinement','/api/chat',{'query':'make them white','mode':'auto','context':context,'active_search':first.get('active_search')})
    more=call('pagination','/api/chat',{'query':'show me more','mode':'auto','context':context,'active_search':refined.get('active_search')})
    old={str(p.get('product_id')) for p in refined['products']}
    if old & {str(p.get('product_id')) for p in more['products']}:
        raise ValueError('Pagination repeated products')
    for mode in ('auto','exact','similar'):
        call('image-'+mode,'/api/image-search',{'mode':mode,'limit':'4'},image=True)
        call('mixed-'+mode,'/api/image-search',{'mode':mode,'limit':'4','query':'make it black'},image=True)
    ready=call('readiness','/api/ready')
    if ready.get('status') != 'ready': raise ValueError('Backend not ready')
    print('PASS real API matrix and returned image loading. Human relevance, browser refresh and voice acceptance still required.')


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        # Never expose underlying provider/HTTP response bodies.
        print('FAIL: '+(str(error) if isinstance(error,ValueError) else type(error).__name__))
        raise SystemExit(1)
