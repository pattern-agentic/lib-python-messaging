import json
from typing import Union
from .types import MessagePayload
from .exceptions import SerializationError

def encode_message(payload: MessagePayload) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode('utf-8')
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
