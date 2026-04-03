from __future__ import annotations

import base64
import json

from pydantic import BaseModel
from typing import Optional

SESSION_TOKEN_METADATA_KEY = "x-pa-session-token"


class PatternAgentSessionToken(BaseModel):
    session_id: str
    tenant_id: str
    user_id: str
    agents: list[str]
    exp: int
    iat: int
    raw_token: str

    @classmethod
    def from_jwt(cls, token: str) -> PatternAgentSessionToken:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return cls(
            session_id=payload["sub"],
            tenant_id=payload["tenant_id"],
            user_id=payload["user_id"],
            agents=payload.get("agents", []),
            exp=payload["exp"],
            iat=payload["iat"],
            raw_token=token,
        )

    @classmethod
    def from_metadata(cls, metadata: dict[str, str]) -> PatternAgentSessionToken:
        token = metadata.get(SESSION_TOKEN_METADATA_KEY)
        if not token:
            raise ValueError(f"Missing {SESSION_TOKEN_METADATA_KEY} in message metadata")
        return cls.from_jwt(token)
