import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional, Literal, get_type_hints, get_origin, get_args
from .types import MessagePayload

logger = logging.getLogger(__name__)

try:
    from pydantic import BaseModel, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = None
    ValidationError = None


def _extract_literal_value(model: type, field_name: str) -> Optional[str]:
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


class PABaseApp(ABC):
    def __init__(self, config):
        self.config = config
        self._message_handlers = []
        self._session_connect_handler = None
        self._session_disconnect_handler = None
        self._init_handler = None
        self._running = True

    @abstractmethod
    async def __aenter__(self):
        ...

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        ...

    @abstractmethod
    def _message_source(self) -> AsyncIterator[tuple[Any, MessagePayload]]:
        ...

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

        if callable(discriminator):
            func = discriminator
            return _register_handler(func, None, None)

        if discriminator is not None and value is None:
            if not self.config.message_discriminator:
                raise ValueError(
                    f"Single-argument @on_message('{discriminator}') requires "
                    f"config.message_discriminator to be set"
                )
            return lambda func: _register_handler(func, self.config.message_discriminator, discriminator)

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
        self._running = False

    def run(self):
        """
        Run the application with automatic event loop and signal handling.

        Signal handling:
        - First SIGINT/SIGTERM: graceful shutdown
        - Second signal: forced shutdown
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
        if not self._message_handlers:
            raise ValueError("No message handlers registered. Use @app.on_message decorator.")

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

            async for session, msg in self._message_source():
                if not self._running:
                    break

                matched = False
                for handler_info in self._message_handlers:
                    disc = handler_info['discriminator']
                    val = handler_info['value']
                    handler = handler_info['handler']
                    model = handler_info.get('model')
                    model_disc_val = handler_info.get('discriminator_value')

                    if model and isinstance(msg, dict):
                        if model_disc_val is not None:
                            if msg.get(disc_field) != model_disc_val:
                                continue

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
                            try:
                                await session.send({
                                    "error": "validation_error",
                                    "details": e.errors()
                                })
                            except Exception as send_exc:
                                logger.error(f"Failed to send validation error response: {send_exc}", exc_info=True)
                            break

                    elif disc is not None:
                        if isinstance(msg, dict) and msg.get(disc) == val:
                            matched = True
                            try:
                                await handler(session, msg)
                            except Exception as exc:
                                logger.error(f"Error in handler '{handler.__name__}' for discriminator {disc}={val}: {exc}", exc_info=True)
                            break

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
                        try:
                            await session.send({
                                "error": "validation_error",
                                "details": e.errors()
                            })
                        except Exception as send_exc:
                            logger.error(f"Failed to send validation error response: {send_exc}", exc_info=True)
                    except Exception as exc:
                        logger.error(f"Error in fallback message handler '{handler.__name__}': {exc}", exc_info=True)
                elif not matched:
                    disc_val = msg.get(disc_field) if isinstance(msg, dict) and disc_field else type(msg).__name__
                    logger.warning(f"No handler matched for message (discriminator={disc_val!r})")
