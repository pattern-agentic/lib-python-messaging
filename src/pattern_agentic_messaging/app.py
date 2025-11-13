import slim_bindings
from typing import Union, AsyncIterator, Optional
from .config import PASlimConfigBase, PASlimP2PConfig, PASlimGroupConfig
from .session import PASlimSession, PASlimP2PSession, PASlimGroupSession
from .auth import create_shared_secret_auth
from .types import SessionMode, GroupMode
from .exceptions import AuthenticationError

class PASlimApp:
    def __init__(self, config: PASlimConfigBase):
        self.config = config
        self._app: Optional[slim_bindings.PyApp] = None

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

    async def create_session(self, config: Union[PASlimP2PConfig, PASlimGroupConfig]) -> Union[PASlimP2PSession, PASlimGroupSession]:
        if isinstance(config, PASlimP2PConfig):
            return await self._create_p2p_session(config)
        elif isinstance(config, PASlimGroupConfig):
            return await self._create_group_session(config)
        else:
            raise ValueError(f"Unsupported config type: {type(config)}")

    async def _create_p2p_session(self, config: PASlimP2PConfig) -> PASlimP2PSession:
        if config.mode == SessionMode.ACTIVE:
            if not config.peer_name:
                raise ValueError("peer_name required for active mode")

            parts = config.peer_name.split('/')
            if len(parts) >= 3:
                peer = slim_bindings.PyName(parts[0], parts[1], parts[2])
            else:
                raise ValueError(f"peer_name must be org/namespace/app or org/namespace/app/instance")

            await self._app.set_route(peer)

            session_config = slim_bindings.PySessionConfiguration.PointToPoint(
                peer_name=peer,
                max_retries=config.max_retries,
                timeout=config.timeout,
                mls_enabled=config.mls_enabled
            )
            slim_session = await self._app.create_session(session_config)
            return PASlimP2PSession(slim_session)
        else:
            slim_session = await self._app.listen_for_session()
            return PASlimP2PSession(slim_session)

    async def _create_group_session(self, config: PASlimGroupConfig) -> PASlimGroupSession:
        if config.mode == GroupMode.MODERATOR:
            parts = config.channel_name.split('/')
            if len(parts) >= 3:
                channel = slim_bindings.PyName(parts[0], parts[1], parts[2])
            else:
                raise ValueError(f"channel_name must be org/namespace/channel")

            session_config = slim_bindings.PySessionConfiguration.Group(
                channel_name=channel,
                max_retries=config.max_retries,
                timeout=config.timeout,
                mls_enabled=config.mls_enabled
            )
            slim_session = await self._app.create_session(session_config)
            session = PASlimGroupSession(slim_session)

            for invite in config.invites:
                parts = invite.split('/')
                if len(parts) >= 3:
                    participant = slim_bindings.PyName(parts[0], parts[1], parts[2])
                else:
                    raise ValueError(f"invite name must be org/namespace/app")
                await self._app.set_route(participant)
                await session.invite(invite)

            return session
        else:
            slim_session = await self._app.listen_for_session()
            return PASlimGroupSession(slim_session)

    async def listen(self) -> AsyncIterator[Union[PASlimP2PSession, PASlimGroupSession]]:
        while True:
            slim_session = await self._app.listen_for_session()
            yield PASlimSession(slim_session)
