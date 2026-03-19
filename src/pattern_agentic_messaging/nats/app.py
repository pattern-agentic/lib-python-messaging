import logging
from typing import AsyncIterator
from ..base_app import PABaseApp
from ..types import MessagePayload
from ..messages import decode_message
from ..exceptions import ConnectionError
from .config import PANatsConfig
from .session import PANatsSession

logger = logging.getLogger(__name__)


class PANatsApp(PABaseApp):
    def __init__(self, config: PANatsConfig):
        super().__init__(config)
        self._nc = None

    def on_session_connect(self, func):
        raise NotImplementedError(
            "on_session_connect is not supported for NATS apps. "
            "NATS is stateless — there is no session lifecycle."
        )

    def on_session_disconnect(self, func):
        raise NotImplementedError(
            "on_session_disconnect is not supported for NATS apps. "
            "NATS is stateless — there is no session lifecycle."
        )

    async def __aenter__(self):
        try:
            import nats as nats_client
        except ImportError:
            raise ImportError(
                "nats-py is required for PANatsApp. "
                "Install it with: pip install pattern_agentic_messaging[nats]"
            )
        connect_opts = {}
        if self.config.credentials:
            connect_opts["user_credentials"] = self.config.credentials
        try:
            self._nc = await nats_client.connect(self.config.nats_url, **connect_opts)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to NATS at {self.config.nats_url}: {e}") from e
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._nc:
            try:
                await self._nc.drain()
            except Exception as e:
                logger.error(f"Error draining NATS connection: {e}", exc_info=True)

    async def _message_source(self) -> AsyncIterator[tuple[PANatsSession, MessagePayload]]:
        sub = await self._nc.subscribe(self.config.subject)
        try:
            async for msg in sub.messages:
                if not self._running:
                    break
                try:
                    decoded = decode_message(msg.data)
                except Exception as e:
                    logger.error(f"Failed to decode NATS message on {self.config.subject}: {e}", exc_info=True)
                    continue
                session = PANatsSession(self._nc, msg)
                yield (session, decoded)
        finally:
            try:
                await sub.unsubscribe()
            except Exception as e:
                logger.error(f"Error unsubscribing from {self.config.subject}: {e}", exc_info=True)
