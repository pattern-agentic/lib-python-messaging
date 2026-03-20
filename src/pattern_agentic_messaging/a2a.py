from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Role(StrEnum):
    USER = "ROLE_USER"
    AGENT = "ROLE_AGENT"


class TaskState(StrEnum):
    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    COMPLETED = "TASK_STATE_COMPLETED"
    FAILED = "TASK_STATE_FAILED"
    CANCELED = "TASK_STATE_CANCELED"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    REJECTED = "TASK_STATE_REJECTED"
    AUTH_REQUIRED = "TASK_STATE_AUTH_REQUIRED"


class Part(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: Optional[str] = None
    raw: Optional[str] = None
    url: Optional[str] = None
    data: Optional[Any] = None
    metadata: Optional[dict[str, Any]] = None
    filename: Optional[str] = None
    media_type: Optional[str] = Field(None, alias="mediaType")

    @model_validator(mode="after")
    def _exactly_one_content(self) -> Part:
        set_fields = [f for f in ("text", "raw", "url", "data") if getattr(self, f) is not None]
        if len(set_fields) != 1:
            raise ValueError(f"Exactly one of text/raw/url/data must be set, got: {set_fields or 'none'}")
        return self

    @classmethod
    def from_text(cls, text: str, *, metadata: Optional[dict[str, Any]] = None) -> Part:
        return cls(text=text, media_type="text/plain", metadata=metadata)

    @classmethod
    def from_data(cls, data: Any, *, metadata: Optional[dict[str, Any]] = None) -> Part:
        return cls(data=data, media_type="application/json", metadata=metadata)

    @classmethod
    def from_file(
        cls,
        *,
        raw: Optional[str] = None,
        url: Optional[str] = None,
        media_type: str,
        filename: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Part:
        return cls(raw=raw, url=url, media_type=media_type, filename=filename, metadata=metadata)


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="messageId")
    role: Role
    parts: list[Part]
    context_id: Optional[str] = Field(None, alias="contextId")
    task_id: Optional[str] = Field(None, alias="taskId")
    reference_task_ids: Optional[list[str]] = Field(None, alias="referenceTaskIds")
    metadata: Optional[dict[str, Any]] = None
    extensions: Optional[list[str]] = None


class Artifact(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    artifact_id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="artifactId")
    parts: list[Part]
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    extensions: Optional[list[str]] = None


class TaskStatus(BaseModel):
    state: TaskState
    message: Optional[Message] = None
    timestamp: Optional[datetime] = None


class Task(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    context_id: Optional[str] = Field(None, alias="contextId")
    status: TaskStatus
    artifacts: Optional[list[Artifact]] = None
    history: Optional[list[Message]] = None
    metadata: Optional[dict[str, Any]] = None


class TaskStatusUpdateEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(alias="taskId")
    context_id: Optional[str] = Field(None, alias="contextId")
    status: TaskStatus
    metadata: Optional[dict[str, Any]] = None


class TaskArtifactUpdateEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(alias="taskId")
    context_id: Optional[str] = Field(None, alias="contextId")
    artifact: Artifact
    append: bool = False
    last_chunk: bool = Field(False, alias="lastChunk")
    metadata: Optional[dict[str, Any]] = None
