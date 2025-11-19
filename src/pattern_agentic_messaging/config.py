from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

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

@dataclass
class PASlimGroupConfig(PASlimConfigBase):
    channel_name: Optional[str] = None
    invites: list[str] = field(default_factory=list)
