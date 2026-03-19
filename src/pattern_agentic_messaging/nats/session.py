import logging
from typing import Optional
from ..messages import encode_message, decode_message

logger = logging.getLogger(__name__)


class PANatsSession:
    def __init__(self, nc, msg):
        self._nc = nc
        self._msg = msg
        self.request_id: Optional[str] = None

        headers = msg.headers or {}
        self.session_id: str = headers.get("PA-Session-Id", "")
        self.request_id = headers.get("PA-Request-Id")

        if not self.session_id:
            logger.warning("Received NATS message without PA-Session-Id header")

    async def send(self, payload) -> None:
        if not self._msg.reply:
            raise RuntimeError(
                "Cannot send reply: incoming message has no reply subject. "
                "The sender must use request() for request-reply."
            )
        data = encode_message(payload)
        headers = {"PA-Session-Id": self.session_id}
        if self.request_id:
            headers["PA-Request-Id"] = self.request_id
        await self._nc.publish(self._msg.reply, data, headers=headers)

    async def request(self, subject: str, payload, timeout: float = 5.0):
        data = encode_message(payload)
        headers = {"PA-Session-Id": self.session_id}
        if self.request_id:
            headers["PA-Request-Id"] = self.request_id
        response = await self._nc.request(subject, data, timeout=timeout, headers=headers)
        return decode_message(response.data)
