import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class AuditPublisher:
    def __init__(self, nats_url: str, subject_prefix: str = "pa.audit.messages", creds_file: Optional[str] = None):
        self._nats_url = nats_url
        self._subject_prefix = subject_prefix
        self._creds_file = creds_file
        self._nc = None
        self._js = None
        self._connect_lock = asyncio.Lock()

    async def connect(self):
        try:
            from nats.aio.client import Client as NATS
        except ImportError:
            raise ImportError("nats-py is required for audit publishing. Install with: pip install pattern-agentic-messaging[audit]")

        async with self._connect_lock:
            if self._nc and self._nc.is_connected:
                return
            self._nc = NATS()
            connect_opts = {"servers": [self._nats_url]}
            if self._creds_file:
                connect_opts["user_credentials"] = self._creds_file
            try:
                await self._nc.connect(**connect_opts)
            except Exception as e:
                self._nc = None
                raise ConnectionError(f"Audit publisher failed to connect to NATS at {self._nats_url}: {e}") from e
            self._js = self._nc.jetstream()
            logger.info(f"Audit publisher connected to {self._nats_url}")

    async def close(self):
        if self._nc and self._nc.is_connected:
            await self._nc.drain()
            await self._nc.close()
            self._nc = None
            self._js = None
            logger.info("Audit publisher closed")

    async def publish(
        self,
        payload,
        *,
        sender: str,
        recipient: str,
        tenant_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        if not self._nc or not self._nc.is_connected:
            try:
                await self.connect()
            except ConnectionError as e:
                logger.warning(str(e))
                return

        if isinstance(payload, bytes):
            try:
                message = json.loads(payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                message = {"raw": payload.hex()}
        elif isinstance(payload, str):
            message = {"text": payload}
        elif hasattr(payload, "model_dump"):
            message = payload.model_dump(by_alias=True, exclude_none=True)
        elif isinstance(payload, dict):
            message = payload
        else:
            message = {"data": str(payload)}

        envelope = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "sender": sender,
            "recipient": recipient,
            "direction": "outgoing",
            "message": message,
        }
        if tenant_id:
            envelope["tenant_id"] = tenant_id
        if session_id:
            envelope["session_id"] = session_id
        if user_id:
            envelope["user_id"] = user_id
        if task_id:
            envelope["task_id"] = task_id
        if metadata:
            envelope["metadata"] = metadata

        subject_parts = [self._subject_prefix]
        if tenant_id:
            subject_parts.append(tenant_id)
        if session_id:
            subject_parts.append(session_id)
        subject = ".".join(subject_parts)

        try:
            data = json.dumps(envelope).encode()
            if self._js:
                await self._js.publish(subject, data)
            else:
                await self._nc.publish(subject, data)
        except Exception:
            logger.warning(f"Audit publish failed for {subject}", exc_info=True)
