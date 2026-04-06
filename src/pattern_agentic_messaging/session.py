import asyncio
import logging
import uuid
from typing import Optional, Callable, Any, Dict
from datetime import timedelta
from .types import MessagePayload
from .messages import encode_message, decode_message
from .exceptions import SessionClosedError, TimeoutError as PATimeoutError
from .session_token import SESSION_TOKEN_METADATA_KEY
from .message_types import tag_a2a_message
from .utils import parse_name

logger = logging.getLogger(__name__)

class PASlimSession:
    def __init__(self, slim_session, *, audit_publisher=None, local_name: str = "", peer_name: str = ""):
        self._session = slim_session
        self._session_id = str(uuid.uuid4())
        self.context: Dict[str, Any] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._read_task: Optional[asyncio.Task] = None
        self._callbacks: list[Callable] = []
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._closed = False
        self._outgoing_metadata: dict[str, str] = {}
        self._audit_publisher = audit_publisher
        self._local_name = local_name
        self._peer_name = peer_name

    @property
    def session_id(self) -> str:
        return self._session_id

    async def _read_loop(self):
        while not self._closed:
            try:
                received = await self._session.get_message_async(None)
                msg_ctx = received.context
                payload = received.payload
                decoded = decode_message(payload)

                incoming_metadata = getattr(msg_ctx, 'metadata', None) or {}
                if SESSION_TOKEN_METADATA_KEY in incoming_metadata:
                    self._outgoing_metadata[SESSION_TOKEN_METADATA_KEY] = incoming_metadata[SESSION_TOKEN_METADATA_KEY]

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

    async def _next_with_context(self):
        if self._closed:
            raise StopAsyncIteration
        try:
            return await self._queue.get()
        except asyncio.CancelledError:
            raise StopAsyncIteration

    async def __anext__(self):
        _, msg = await self._next_with_context()
        return msg

    def set_metadata(self, metadata: dict[str, str]):
        self._outgoing_metadata = metadata

    async def send(self, payload: MessagePayload, metadata: Optional[dict[str, str]] = None):
        if self._closed:
            raise SessionClosedError("Session is closed")
        data = encode_message(payload)
        merged = {**self._outgoing_metadata, **(metadata or {})}
        await self._session.publish_and_wait_async(data, None, merged or None)
        if self._audit_publisher:
            try:
                from .session_token import PatternAgentSessionToken
                token = PatternAgentSessionToken.from_metadata(merged) if merged else None
                audit_payload = tag_a2a_message(dict(payload)) if isinstance(payload, dict) else payload
                await self._audit_publisher.publish(
                    audit_payload,
                    sender=self._local_name,
                    recipient=self._peer_name,
                    tenant_id=token.tenant_id if token else None,
                    session_id=token.session_id if token else None,
                    user_id=token.user_id if token else None,
                    task_id=payload.get("taskId") if isinstance(payload, dict) else None,
                )
            except Exception:
                logger.debug("Audit publish failed", exc_info=True)

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
        await self._session.invite_and_wait_async(name)

    async def remove(self, participant_name: str):
        name = parse_name(participant_name)
        await self._session.remove_and_wait_async(name)
