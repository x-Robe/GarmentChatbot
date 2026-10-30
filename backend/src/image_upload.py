"""Bounded upload decoding. No model loading or permanent image storage."""
from io import BytesIO

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_MULTIPART_BYTES = MAX_IMAGE_BYTES + 64 * 1024
MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP'}


class ImageUploadSizeLimit:
    """Bound the whole multipart stream before Starlette parses/spools it."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] != '/api/image-search':
            return await self.app(scope, receive, send)
        size = 0
        headers = dict(scope.get('headers', []))
        try:
            declared = int(headers.get(b'content-length', b'0'))
        except ValueError:
            declared = 0
        if declared > MAX_MULTIPART_BYTES:
            return await JSONResponse(status_code=413, content={'detail': 'Image upload exceeds the 10 MiB limit.'})(scope, receive, send)

        chunks = []
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size > MAX_MULTIPART_BYTES:
                return await JSONResponse(status_code=413, content={'detail': 'Image upload exceeds the 10 MiB limit.'})(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body', False):
                break

        async def bounded_receive():
            if chunks:
                return {'type': 'http.request', 'body': chunks.pop(0), 'more_body': bool(chunks)}
            return await receive()

        await self.app(scope, bounded_receive, send)



def decode_image(data: bytes, content_type: str | None) -> Image.Image:
    """Fully decode an allowed raster image; caller owns the returned image."""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(400, 'Upload a JPEG, PNG, or WebP image.')
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, 'Image upload exceeds the 10 MiB limit.')
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise HTTPException(400, 'Upload a JPEG, PNG, or WebP image.')
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise HTTPException(400, 'Image dimensions are too large (maximum 20 million pixels).')
            source.load()
            return source.convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(400, 'Image is invalid or could not be decoded.') from None
