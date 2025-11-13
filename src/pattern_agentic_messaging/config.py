from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional
from .types import SessionMode, GroupMode

@dataclass
class PASlimConfigBase:
    local_name: str
    endpoint: str
    auth_secret: Optional[str] = None
    max_retries: int = 5
    timeout: timedelta = field(default_factory=lambda: timedelta(seconds=5))
    mls_enabled: bool = True

@dataclass
class PASlimP2PConfig(PASlimConfigBase):
    peer_name: Optional[str] = None
    mode: SessionMode = SessionMode.ACTIVE

@dataclass
class PASlimGroupConfig(PASlimConfigBase):
    channel_name: str = ""
    mode: GroupMode = GroupMode.MODERATOR
    invites: list[str] = field(default_factory=list)
