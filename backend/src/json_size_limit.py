"""Bound continuation JSON before parsing, including chunked request bodies."""
from fastapi.responses import JSONResponse

class ContinuationSizeLimit:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] != '/api/image-search/continue':
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect': return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size > 2 * 1024 * 1024:
                return await JSONResponse(status_code=413, content={'detail':'Image continuation request is too large.'})(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body', False): break
        async def bounded():
            if chunks:
                return {'type':'http.request','body':chunks.pop(0),'more_body':bool(chunks)}
            return await receive()
        await self.app(scope, bounded, send)
