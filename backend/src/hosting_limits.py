"""Single-process admission control; no client data or proxy/IP assumptions."""
import os
from collections import deque
from threading import Lock
from time import monotonic
from starlette.responses import JSONResponse


class HostingLimits:
    def __init__(self, app):
        self.app = app
        self.maximum = max(1, int(os.getenv("API_REQUESTS_PER_MINUTE", "30")))
        self.capacity = max(1, int(os.getenv("API_MAX_INFLIGHT", "2")))
        self.times = deque()
        self.inflight = 0
        self.lock = Lock()

    async def __call__(self, scope, receive, send):
        if (scope['type'] != 'http' or scope['method'] != 'POST'
                or not scope['path'].startswith('/api/')):
            return await self.app(scope, receive, send)
        with self.lock:
            now = monotonic()
            while self.times and self.times[0] <= now - 60:
                self.times.popleft()
            busy = self.inflight >= self.capacity
            limited = len(self.times) >= self.maximum
            if not busy and not limited:
                self.times.append(now)
                self.inflight += 1
        if busy or limited:
            response = JSONResponse(
                {'detail': 'Search is busy. Please try again shortly.'},
                status_code=429, headers={'Retry-After': '60' if limited else '5'})
            return await response(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            with self.lock:
                self.inflight -= 1
