from enum import Enum
from typing import Union

MessagePayload = Union[bytes, str, dict]

class SessionMode(Enum):
    ACTIVE = "active"
    PASSIVE = "passive"

class GroupMode(Enum):
    MODERATOR = "moderator"
    PARTICIPANT = "participant"
