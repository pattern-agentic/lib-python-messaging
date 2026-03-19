from dataclasses import dataclass
from typing import Optional


@dataclass
class PANatsConfig:
    nats_url: str
    subject: str
    credentials: Optional[str] = None
    message_discriminator: Optional[str] = None
