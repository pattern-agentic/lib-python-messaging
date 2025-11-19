import asyncio
import slim_bindings
from typing import AsyncIterator, Optional
from .config import PASlimConfigBase
from .session import PASlimSession, PASlimP2PSession, PASlimGroupSession
from .auth import create_shared_secret_auth
from .types import MessagePayload
from .exceptions import AuthenticationError

class PASlimApp:
    def __init__(self, config: PASlimConfigBase):
        self.config = config
        self._app: Optional[slim_bindings.PyApp] = None
        self._message_handlers = []
        self._session_connect_handler = None
        self._session_disconnect_handler = None
        self._running = True

    async def __aenter__(self):
        if not self.config.auth_secret:
            raise AuthenticationError("auth_secret is required")

        auth_provider, auth_verifier = create_shared_secret_auth(
            self.config.local_name,
            self.config.auth_secret
        )

        parts = self.config.local_name.split('/')
        if len(parts) == 3:
            local_name = slim_bindings.PyName(*parts)
        elif len(parts) == 4:
            local_name = slim_bindings.PyName(parts[0], parts[1], parts[2])
        else:
            raise ValueError(f"local_name must be org/namespace/app or org/namespace/app/instance")

        self._app = await slim_bindings.Slim.new(local_name, auth_provider, auth_verifier)

        slim_config = {"endpoint": self.config.endpoint}
        await self._app.connect(slim_config)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def __aiter__(self):
        return self.messages()

    def on_message(self, discriminator=None, value=None):
        """
        Decorator to register a message handler with optional filtering.

        Can be used as a direct decorator or with discriminator arguments.

        Examples:
            # Catch-all handler (no filter)
            @app.on_message
            async def handler(session, msg):
                await session.send(response)

            # Filtered handler
            @app.on_message('type', 'prompt')
            async def handler(session, msg):
                # Only called when msg['type'] == 'prompt'
                await session.send(response)
        """
        def decorator(func):
            self._message_handlers.append({
                'discriminator': discriminator,
                'value': value,
                'handler': func
            })
            return func

        # Direct decoration: @app.on_message
        if callable(discriminator):
            func = discriminator
            self._message_handlers.append({
                'discriminator': None,
                'value': None,
                'handler': func
            })
            return func

        # Decorator factory: @app.on_message('key', 'val')
        return decorator

    def on_session_connect(self, func):
        """
        Decorator to register a session connect handler.

        The handler will be called when a new session is established.

        Example:
            @app.on_session_connect
            async def handler(session):
                logger.info(f"Session {session.session_id} connected")
        """
        self._session_connect_handler = func
        return func

    def on_session_disconnect(self, func):
        """
        Decorator to register a session disconnect handler.

        The handler will be called when a session ends.

        Example:
            @app.on_session_disconnect
            async def handler(session):
                logger.info(f"Session {session.session_id} disconnected")
        """
        self._session_disconnect_handler = func
        return func

    def stop(self):
        """Stop the application gracefully."""
        self._running = False

    def run(self):
        """
        Run the application with automatic event loop and signal handling.

        This is a synchronous method that sets up signal handlers,
        creates an event loop, and runs the async message handling loop.

        Example:
            app = PASlimApp(config)

            @app.on_message
            async def handler(session, msg):
                await session.send(response)

            app.run()  # Blocks until stopped
        """
        import signal as sig

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def signal_handler(signum, frame):
            self.stop()

        sig.signal(sig.SIGTERM, signal_handler)
        sig.signal(sig.SIGINT, signal_handler)

        try:
            loop.run_until_complete(self._run_async())
        except KeyboardInterrupt:
            pass
        finally:
            loop.close()

    async def _run_async(self):
        """Internal async runner for the decorator pattern."""
        import logging

        if not self._message_handlers:
            raise ValueError("No message handlers registered. Use @app.on_message decorator.")

        # Find catch-all handler
        catch_all = None
        for handler_info in self._message_handlers:
            if handler_info['discriminator'] is None:
                catch_all = handler_info['handler']
                break

        logger = logging.getLogger(__name__)

        async with self:
            async for session, msg in self:
                if not self._running:
                    break

                # Try filtered handlers first
                matched = False
                for handler_info in self._message_handlers:
                    disc = handler_info['discriminator']
                    val = handler_info['value']
                    handler = handler_info['handler']

                    # Skip catch-all handlers
                    if disc is None:
                        continue

                    # Check if message matches filter
                    if isinstance(msg, dict) and msg.get(disc) == val:
                        matched = True
                        try:
                            await handler(session, msg)
                        except Exception as exc:
                            logger.error(
                                f"Error in message handler: {exc}",
                                exc_info=True
                            )
                        break  # First match wins

                # Fall back to catch-all if no specific handler matched
                if not matched:
                    if catch_all:
                        try:
                            await catch_all(session, msg)
                        except Exception as exc:
                            logger.error(
                                f"Error in catch-all handler: {exc}",
                                exc_info=True
                            )
                    else:
                        # No handler matched and no catch-all
                        logger.warning(
                            f"No handler for message: {msg}"
                        )

    async def connect(self, peer_name: str) -> PASlimP2PSession:
        """
        Connect to a peer (P2P Active mode).

        Args:
            peer_name: Peer identifier (e.g., "org/namespace/app")

        Returns:
            PASlimP2PSession for communicating with the peer
        """
        parts = peer_name.split('/')
        if len(parts) >= 3:
            peer = slim_bindings.PyName(parts[0], parts[1], parts[2])
        else:
            raise ValueError(f"peer_name must be org/namespace/app or org/namespace/app/instance")

        await self._app.set_route(peer)

        session_config = slim_bindings.PySessionConfiguration.PointToPoint(
            peer_name=peer,
            max_retries=self.config.max_retries,
            timeout=self.config.timeout,
            mls_enabled=self.config.mls_enabled
        )
        slim_session = await self._app.create_session(session_config)
        return PASlimP2PSession(slim_session)

    async def accept(self) -> PASlimP2PSession:
        """
        Accept a single incoming P2P session (P2P Passive mode).

        Returns:
            PASlimP2PSession for the incoming connection
        """
        slim_session = await self._app.listen_for_session()
        return PASlimP2PSession(slim_session)

    async def create_channel(self, channel_name: str, invites: list[str] = None) -> PASlimGroupSession:
        """
        Create a group channel and invite participants (Group Moderator mode).

        Args:
            channel_name: Channel identifier (e.g., "org/namespace/channel")
            invites: List of participant names to invite

        Returns:
            PASlimGroupSession for the channel
        """
        if invites is None:
            invites = []

        parts = channel_name.split('/')
        if len(parts) >= 3:
            channel = slim_bindings.PyName(parts[0], parts[1], parts[2])
        else:
            raise ValueError(f"channel_name must be org/namespace/channel")

        session_config = slim_bindings.PySessionConfiguration.Group(
            channel_name=channel,
            max_retries=self.config.max_retries,
            timeout=self.config.timeout,
            mls_enabled=self.config.mls_enabled
        )
        slim_session = await self._app.create_session(session_config)
        session = PASlimGroupSession(slim_session)

        for invite in invites:
            parts = invite.split('/')
            if len(parts) >= 3:
                participant = slim_bindings.PyName(parts[0], parts[1], parts[2])
            else:
                raise ValueError(f"invite name must be org/namespace/app")
            await self._app.set_route(participant)
            await session.invite(invite)

        return session

    async def join_channel(self) -> PASlimGroupSession:
        """
        Join a group channel by accepting an invite (Group Participant mode).

        Returns:
            PASlimGroupSession for the channel
        """
        slim_session = await self._app.listen_for_session()
        return PASlimGroupSession(slim_session)

    async def listen(self) -> AsyncIterator[PASlimP2PSession]:
        """
        Listen for incoming P2P sessions (P2P Passive mode).

        Yields:
            PASlimP2PSession for each incoming connection
        """
        while True:
            slim_session = await self._app.listen_for_session()
            yield PASlimP2PSession(slim_session)

    async def messages(self) -> AsyncIterator[tuple[PASlimSession, MessagePayload]]:
        """
        Iterate over messages from all incoming sessions.

        Yields (session, message) tuples from all active sessions.
        Automatically manages session lifecycle - listens for new sessions,
        starts their message loops, and multiplexes messages into a single stream.

        Designed for servers handling multiple concurrent clients.

        Example:
            async with PASlimApp(config) as app:
                async for session, msg in app:
                    await session.send(response)
        """
        message_queue: asyncio.Queue = asyncio.Queue()
        session_tasks: set[asyncio.Task] = set()
        listener_task: Optional[asyncio.Task] = None

        async def session_reader(session: PASlimSession):
            """Read messages from a session and forward to queue."""
            try:
                # Call session connect handler if registered
                if self._session_connect_handler:
                    try:
                        await self._session_connect_handler(session)
                    except Exception:
                        pass  # Don't let handler errors prevent session

                async with session:
                    async for msg in session:
                        await message_queue.put((session, msg))
            except Exception:
                pass  # Session ended or errored - normal behavior
            finally:
                # Call session disconnect handler if registered
                if self._session_disconnect_handler:
                    try:
                        await self._session_disconnect_handler(session)
                    except Exception:
                        pass  # Don't let handler errors prevent cleanup

        async def session_listener():
            """Listen for new sessions and spawn reader tasks."""
            async for session in self.listen():
                task = asyncio.create_task(session_reader(session))
                session_tasks.add(task)
                task.add_done_callback(session_tasks.discard)

        try:
            listener_task = asyncio.create_task(session_listener())

            while True:
                # Check if listener crashed
                if listener_task.done():
                    exc = listener_task.exception()
                    if exc:
                        raise exc
                    break  # Listener ended (shouldn't happen)

                # Get next message with timeout to periodically check listener health
                try:
                    session, msg = await asyncio.wait_for(
                        message_queue.get(),
                        timeout=0.1
                    )
                    yield (session, msg)
                except asyncio.TimeoutError:
                    continue  # No message yet, loop back

        finally:
            # Cleanup: cancel all tasks
            if listener_task and not listener_task.done():
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    pass

            for task in list(session_tasks):
                task.cancel()

            if session_tasks:
                await asyncio.gather(*session_tasks, return_exceptions=True)
