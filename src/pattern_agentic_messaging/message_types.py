from typing import Any, Optional
from pydantic import BaseModel

PA_TYPE_KEY = "__pa_type"


class PAType:
    A2A_MESSAGE = "a2a.message"
    A2A_TASK_STATUS = "a2a.task_status"
    A2A_TASK_ARTIFACT = "a2a.task_artifact"
    SYSTEM_ERROR = "system_error"


class PASystemError(BaseModel):
    error: str
    detail: str
    metadata: dict[str, Any] = {}

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": self.error,
            "detail": self.detail,
            "metadata": {**self.metadata, PA_TYPE_KEY: PAType.SYSTEM_ERROR},
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PASystemError":
        return cls(
            error=payload.get("error", "unknown"),
            detail=payload.get("detail", ""),
            metadata={k: v for k, v in payload.get("metadata", {}).items() if k != PA_TYPE_KEY},
        )


def tag_a2a_message(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("metadata") or {}
    meta[PA_TYPE_KEY] = PAType.A2A_MESSAGE
    payload["metadata"] = meta
    return payload


def tag_a2a_task_status(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("metadata") or {}
    meta[PA_TYPE_KEY] = PAType.A2A_TASK_STATUS
    payload["metadata"] = meta
    return payload


def get_pa_type(payload: dict[str, Any]) -> Optional[str]:
    meta = payload.get("metadata") or {}
    return meta.get(PA_TYPE_KEY)
