from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional


@dataclass
class PASlimConfig:
    local_name: str
    endpoint: str
    auth_secret: Optional[str] = None
    max_retries: int = 5
    timeout: timedelta = field(default_factory=lambda: timedelta(seconds=5))
    mls_enabled: bool = True
    message_discriminator: Optional[str] = None
    custom_headers: Optional[dict[str, str]] = None


@dataclass
class PASlimConfigP2P(PASlimConfig):
    peer_name: Optional[str] = None


@dataclass
class PASlimConfigGroup(PASlimConfig):
    channel_name: Optional[str] = None
    invites: list[str] = field(default_factory=list)
