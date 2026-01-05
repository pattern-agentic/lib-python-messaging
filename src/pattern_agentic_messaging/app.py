import asyncio
import logging
import slim_bindings
from typing import AsyncIterator, Optional, Literal, get_type_hints, get_origin, get_args
from .config import PASlimConfig
from .session import PASlimSession, PASlimP2PSession, PASlimGroupSession
from .auth import create_shared_secret_auth
from .types import MessagePayload
from .exceptions import AuthenticationError
from .utils import parse_name

logger = logging.getLogger(__name__)

try:
    from pydantic import BaseModel, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = None
    ValidationError = None


def _extract_literal_value(model: type, field_name: str) -> Optional[str]:
    """Extract Literal value from a Pydantic model field."""
    try:
        hints = get_type_hints(model)
        field_type = hints.get(field_name)
        if get_origin(field_type) is Literal:
            args = get_args(field_type)
            if args:
                return args[0]
    except Exception:
        pass
    return None


def _get_pydantic_model_from_handler(func) -> Optional[type]:
    """Extract Pydantic model type from handler's msg parameter, if present."""
    if not PYDANTIC_AVAILABLE:
        return None
    try:
        hints = get_type_hints(func)
        msg_type = hints.get('msg')
        if msg_type and isinstance(msg_type, type) and issubclass(msg_type, BaseModel):
            return msg_type
    except Exception:
        pass
    return None


class PASlimApp:
    def __init__(self, config: PASlimConfig):
        self.config = config
        self._app: Optional[slim_bindings.Slim] = None
        self._message_handlers = []
        self._session_connect_handler = None
        self._session_disconnect_handler = None
        self._init_handler = None
        self._running = True

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

    def on_message(self, discriminator=None, value=None):
        """
        Decorator to register a message handler with optional filtering.

        Can be used as a direct decorator or with discriminator arguments.
        Supports Pydantic model type hints for automatic parsing.

        Examples:
            # Catch-all handler (no filter)
            @app.on_message
            async def handler(session, msg):
                await session.send(response)

            # Filtered by value (requires message_discriminator in config)
            @app.on_message('prompt')
            async def handler(session, msg):
                # Called when msg[config.message_discriminator] == 'prompt'
                await session.send(response)

            # Filtered by explicit field and value (legacy)
            @app.on_message('type', 'prompt')
            async def handler(session, msg):
                # Only called when msg['type'] == 'prompt'
                await session.send(response)

            # Pydantic model handler (requires message_discriminator in config)
            @app.on_message
            async def handler(session, msg: PromptMessage):
                # msg is automatically parsed as PromptMessage
                await session.send(response)
        """
        def _register_handler(func, disc_field, disc_value):
            model = _get_pydantic_model_from_handler(func)
            model_disc_value = None

            if model:
                if not self.config.message_discriminator:
                    raise ValueError(
                        f"Handler '{func.__name__}' uses Pydantic type hint, "
                        f"but config.message_discriminator is not set"
                    )
                model_disc_value = _extract_literal_value(
                    model, self.config.message_discriminator
                )

            self._message_handlers.append({
                'discriminator': disc_field,
                'value': disc_value,
                'handler': func,
                'model': model,
                'discriminator_value': model_disc_value,
            })
            return func

        # Direct decoration: @app.on_message
        if callable(discriminator):
            func = discriminator
            return _register_handler(func, None, None)

        # Single argument: @app.on_message('prompt') - uses config.message_discriminator
        if discriminator is not None and value is None:
            if not self.config.message_discriminator:
                raise ValueError(
                    f"Single-argument @on_message('{discriminator}') requires "
                    f"config.message_discriminator to be set"
                )
            return lambda func: _register_handler(func, self.config.message_discriminator, discriminator)

        # Two arguments: @app.on_message('type', 'prompt')
        return lambda func: _register_handler(func, discriminator, value)

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

    def on_init(self, func):
        """
        Decorator to register an async initialization handler.

        Called once at app startup, after connection but before message handling.
        If the handler raises an exception, the app will abort with error details.

        Example:
            @app.on_init
            async def init():
                await setup_database()
        """
        self._init_handler = func
        return func

    def stop(self):
        """Stop the application gracefully."""
        self._running = False

    def run(self):
        """
        Run the application with automatic event loop and signal handling.

        This is a synchronous method that sets up signal handlers,
        creates an event loop, and runs the async message handling loop.

        Signal handling:
        - First SIGINT/SIGTERM: graceful shutdown (waits for cleanup)
        - Second signal: forced shutdown (cancels immediately)

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

        self._running = True
        main_task = None
        shutdown_requested = False

        def signal_handler():
            nonlocal shutdown_requested
            if not shutdown_requested:
                shutdown_requested = True
                self.stop()
            elif main_task and not main_task.done():
                main_task.cancel()

        for s in (sig.SIGTERM, sig.SIGINT):
            loop.add_signal_handler(s, signal_handler)

        try:
            main_task = loop.create_task(self._run_async())
            loop.run_until_complete(main_task)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            for s in (sig.SIGTERM, sig.SIGINT):
                loop.remove_signal_handler(s)
            loop.close()

    async def _run_async(self):
        """Internal async runner for the decorator pattern."""
        if not self._message_handlers:
            raise ValueError("No message handlers registered. Use @app.on_message decorator.")

        # Find catch-all handler (no discriminator and no model discriminator_value)
        catch_all_info = None
        for handler_info in self._message_handlers:
            if handler_info['discriminator'] is None and handler_info.get('discriminator_value') is None:
                catch_all_info = handler_info
                break

        disc_field = self.config.message_discriminator

        async with self:
            if self._init_handler:
                try:
                    await self._init_handler()
                except Exception as e:
                    logger.error(f"App initialization failed: {e}", exc_info=True)
                    return

            async for session, msg in self:
                if not self._running:
                    break

                matched = False
                for handler_info in self._message_handlers:
                    disc = handler_info['discriminator']
                    val = handler_info['value']
                    handler = handler_info['handler']
                    model = handler_info.get('model')
                    model_disc_val = handler_info.get('discriminator_value')

                    # Pydantic model handler
                    if model and isinstance(msg, dict):
                        # Check discriminator match (fast path)
                        if model_disc_val is not None:
                            if msg.get(disc_field) != model_disc_val:
                                continue  # Fall through to next handler

                        # Try to parse
                        try:
                            parsed = model.model_validate(msg)
                            matched = True
                            try:
                                await handler(session, parsed)
                            except Exception as exc:
                                model_name = model.__name__ if model else "untyped"
                                logger.error(f"Error in handler '{handler.__name__}' for message type '{model_name}': {exc}", exc_info=True)
                            break
                        except ValidationError as e:
                            matched = True
                            await session.send({
                                "error": "validation_error",
                                "details": e.errors()
                            })
                            break

                    # Legacy dict-based handler (skip catch-all for now)
                    elif disc is not None:
                        if isinstance(msg, dict) and msg.get(disc) == val:
                            matched = True
                            try:
                                await handler(session, msg)
                            except Exception as exc:
                                logger.error(f"Error in handler '{handler.__name__}' for discriminator {disc}={val}: {exc}", exc_info=True)
                            break

                # Fall back to catch-all if no specific handler matched
                if not matched and catch_all_info:
                    handler = catch_all_info['handler']
                    model = catch_all_info.get('model')
                    try:
                        if model and isinstance(msg, dict):
                            parsed = model.model_validate(msg)
                            await handler(session, parsed)
                        else:
                            await handler(session, msg)
                    except ValidationError as e:
                        await session.send({
                            "error": "validation_error",
                            "details": e.errors()
                        })
                    except Exception as exc:
                        logger.error(f"Error in fallback message handler '{handler.__name__}': {exc}", exc_info=True)
                elif not matched:
                    logger.warning(f"No handler for message: {msg}")

    async def connect(self, peer_name: str) -> PASlimP2PSession:
        """
        Connect to a peer (P2P Active mode).

        Args:
            peer_name: Peer identifier (e.g., "org/namespace/app")

        Returns:
            PASlimP2PSession for communicating with the peer
        """
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
                # Call session disconnect handler if registered
                if self._session_disconnect_handler:
                    try:
                        await self._session_disconnect_handler(session)
                    except Exception as e:
                        logger.error(f"Error in session disconnect handler: {e}", exc_info=True)

        async def session_listener():
            """Listen for new sessions and spawn reader tasks."""
            async for session in self.listen():
                task = asyncio.create_task(session_reader(session))
                session_tasks.add(task)
                task.add_done_callback(session_tasks.discard)

        try:
            listener_task = asyncio.create_task(session_listener())

            while self._running:
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
            # Cleanup: cancel all tasks with timeout to avoid hanging
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
