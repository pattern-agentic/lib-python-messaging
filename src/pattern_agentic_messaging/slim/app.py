import asyncio
import logging
from typing import AsyncIterator, Optional
from ..base_app import PABaseApp
from .config import PASlimConfig
from .session import PASlimSession, PASlimP2PSession, PASlimGroupSession
from .auth import create_shared_secret_auth
from ..types import MessagePayload
from ..exceptions import AuthenticationError
from .utils import parse_name
import slim_bindings

logger = logging.getLogger(__name__)


class PASlimApp(PABaseApp):
    def __init__(self, config: PASlimConfig):
        super().__init__(config)
        self._app: Optional[slim_bindings.Slim] = None

    async def __aenter__(self):
        if not self.config.auth_secret:
            raise AuthenticationError("auth_secret is required")
        if len(self.config.auth_secret) < 32:
            raise AuthenticationError("auth_secret must be at least 32 bytes")

        auth_provider, auth_verifier = create_shared_secret_auth(
            self.config.local_name,
            self.config.auth_secret
        )

        local_name = parse_name(self.config.local_name)
        self._app = slim_bindings.Slim(local_name, auth_provider, auth_verifier)

        slim_config = {"endpoint": self.config.endpoint}
        if self.config.custom_headers:
            slim_config["headers"] = self.config.custom_headers
        await self._app.connect(slim_config)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def __aiter__(self):
        return self.messages()

    async def connect(self, peer_name: str) -> PASlimP2PSession:
        peer = parse_name(peer_name)
        await self._app.set_route(peer)

        session_config = slim_bindings.SessionConfiguration.PointToPoint(
            max_retries=self.config.max_retries,
            timeout=self.config.timeout,
            mls_enabled=self.config.mls_enabled
        )
        slim_session, handle = await self._app.create_session(peer, session_config)
        await handle
        return PASlimP2PSession(slim_session)

    async def accept(self) -> PASlimP2PSession:
        slim_session = await self._app.listen_for_session()
        return PASlimP2PSession(slim_session)

    async def create_channel(self, channel_name: str, invites: list[str] = None) -> PASlimGroupSession:
        if invites is None:
            invites = []

        channel = parse_name(channel_name)
        session_config = slim_bindings.SessionConfiguration.Group(
            max_retries=self.config.max_retries,
            timeout=self.config.timeout,
            mls_enabled=self.config.mls_enabled
        )
        slim_session, handle = await self._app.create_session(channel, session_config)
        await handle
        session = PASlimGroupSession(slim_session)

        for invite in invites:
            participant = parse_name(invite)
            await self._app.set_route(participant)
            await session.invite(invite)

        return session

    async def join_channel(self) -> PASlimGroupSession:
        slim_session = await self._app.listen_for_session()
        return PASlimGroupSession(slim_session)

    async def listen(self) -> AsyncIterator[PASlimP2PSession]:
        while True:
            slim_session = await self._app.listen_for_session()
            yield PASlimP2PSession(slim_session)

    async def _message_source(self) -> AsyncIterator[tuple[PASlimSession, MessagePayload]]:
        async for item in self.messages():
            yield item

    async def messages(self) -> AsyncIterator[tuple[PASlimSession, MessagePayload]]:
        """
        Iterate over messages from all incoming sessions.

        Yields (session, message) tuples from all active sessions.
        Automatically manages session lifecycle.
        """
        message_queue: asyncio.Queue = asyncio.Queue()
        session_tasks: set[asyncio.Task] = set()
        listener_task: Optional[asyncio.Task] = None

        async def session_reader(session: PASlimSession):
            try:
                if self._session_connect_handler:
                    try:
                        await self._session_connect_handler(session)
                    except Exception as e:
                        logger.error(f"Error in session connect handler: {e}", exc_info=True)

                async with session:
                    async for msg in session:
                        await message_queue.put((session, msg))
            except (StopAsyncIteration, asyncio.CancelledError):
                pass
            except Exception as e:
                logger.error(f"Session reader error: {e}", exc_info=True)
            finally:
                if self._session_disconnect_handler:
                    try:
                        await self._session_disconnect_handler(session)
                    except Exception as e:
                        logger.error(f"Error in session disconnect handler: {e}", exc_info=True)

        async def session_listener():
            async for session in self.listen():
                task = asyncio.create_task(session_reader(session))
                session_tasks.add(task)
                task.add_done_callback(session_tasks.discard)

        try:
            listener_task = asyncio.create_task(session_listener())

            while self._running:
                if listener_task.done():
                    exc = listener_task.exception()
                    if exc:
                        raise exc
                    break

                try:
                    session, msg = await asyncio.wait_for(
                        message_queue.get(),
                        timeout=0.1
                    )
                    yield (session, msg)
                except asyncio.TimeoutError:
                    continue

        finally:
            if listener_task and not listener_task.done():
                listener_task.cancel()
                try:
                    await asyncio.wait_for(listener_task, timeout=0.5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            for task in list(session_tasks):
                task.cancel()

            if session_tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*session_tasks, return_exceptions=True),
                        timeout=0.5
                    )
                except asyncio.TimeoutError:
                    pass
