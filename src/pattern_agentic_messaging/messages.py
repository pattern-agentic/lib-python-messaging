import json
from typing import Union
from .types import MessagePayload
from .exceptions import SerializationError

try:
    from pydantic import BaseModel
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = None

def encode_message(payload: MessagePayload) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode('utf-8')
    if PYDANTIC_AVAILABLE and isinstance(payload, BaseModel):
        try:
            return json.dumps(payload.model_dump()).encode('utf-8')
        except (TypeError, ValueError) as e:
            raise SerializationError(f"Failed to encode Pydantic model: {e}")
    if isinstance(payload, dict):
        try:
            return json.dumps(payload).encode('utf-8')
        except (TypeError, ValueError) as e:
            raise SerializationError(f"Failed to encode dict: {e}")
    raise SerializationError(f"Unsupported payload type: {type(payload)}")

def decode_message(data: bytes) -> Union[dict, str, bytes]:
    try:
        text = data.decode('utf-8', errors='strict')
        if '\x00' in text:
            return data
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    except UnicodeDecodeError:
        return data
