import asyncio
import logging
import uuid
from typing import Optional, Callable, Any, Dict
from datetime import timedelta
from .types import MessagePayload
from .messages import encode_message, decode_message
from .exceptions import SessionClosedError, TimeoutError as PATimeoutError
from .utils import parse_name

logger = logging.getLogger(__name__)

class PASlimSession:
    def __init__(self, slim_session):
        self._session = slim_session
        self._session_id = str(uuid.uuid4())
        self.context: Dict[str, Any] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._read_task: Optional[asyncio.Task] = None
        self._callbacks: list[Callable] = []
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._closed = False

    @property
    def session_id(self) -> str:
        """Unique identifier for this session instance."""
        return self._session_id

    async def _read_loop(self):
        while not self._closed:
            try:
                msg_ctx, payload = await self._session.get_message()
                decoded = decode_message(payload)

                if isinstance(decoded, dict) and "_request_id" in decoded:
                    request_id = decoded["_request_id"]
                    if request_id in self._pending_requests:
                        self._pending_requests[request_id].set_result(decoded)
                        continue

                for callback in self._callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(decoded)
                        else:
                            callback(decoded)
                    except Exception as e:
                        callback_name = getattr(callback, '__name__', repr(callback))
                        logger.error(f"Error in callback '{callback_name}': {e}", exc_info=True)

                await self._queue.put((msg_ctx, decoded))
            except Exception as e:
                if not self._closed:
                    logger.error(f"Read loop error: {e}", exc_info=True)
                break

    async def __aenter__(self):
        self._read_task = asyncio.create_task(self._read_loop())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._closed = True
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._closed:
            raise StopAsyncIteration
        try:
            _, msg = await self._queue.get()
            return msg
        except asyncio.CancelledError:
            raise StopAsyncIteration

    async def send(self, payload: MessagePayload):
        if self._closed:
            raise SessionClosedError("Session is closed")
        data = encode_message(payload)
        handle = await self._session.publish(data)
        await handle

    def on_message(self, callback: Callable[[Any], None]):
        self._callbacks.append(callback)

    async def request(self, payload: MessagePayload, timeout: Optional[float] = None) -> Any:
        if self._closed:
            raise SessionClosedError("Session is closed")

        request_id = str(uuid.uuid4())
        future = asyncio.Future()
        self._pending_requests[request_id] = future

        if hasattr(payload, 'model_dump'):
            payload = payload.model_dump()

        if isinstance(payload, dict):
            payload["_request_id"] = request_id
        else:
            payload = {"_request_id": request_id, "data": payload}

        await self.send(payload)

        try:
            if timeout:
                return await asyncio.wait_for(future, timeout=timeout)
            else:
                return await future
        except asyncio.TimeoutError:
            raise PATimeoutError(f"Request timed out after {timeout}s")
        finally:
            self._pending_requests.pop(request_id, None)

class PASlimP2PSession(PASlimSession):
    pass

class PASlimGroupSession(PASlimSession):
    async def invite(self, participant_name: str):
        name = parse_name(participant_name)
        handle = await self._session.invite(name)
        await handle

    async def remove(self, participant_name: str):
        name = parse_name(participant_name)
        handle = await self._session.remove(name)
        await handle
