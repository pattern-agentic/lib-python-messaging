import pytest
from pattern_agentic_messaging.messages import encode_message, decode_message
from pattern_agentic_messaging.exceptions import SerializationError

def test_encode_bytes():
    data = b"raw bytes"
    assert encode_message(data) == data

def test_encode_str():
    assert encode_message("hello") == b"hello"

def test_encode_dict():
    result = encode_message({"type": "ping"})
    assert result == b'{"type": "ping"}'

def test_encode_invalid():
    with pytest.raises(SerializationError):
        encode_message(123)

def test_decode_json():
    data = b'{"type": "pong"}'
    result = decode_message(data)
    assert result == {"type": "pong"}

def test_decode_string():
    data = b"plain text"
    result = decode_message(data)
    assert result == "plain text"

def test_decode_binary():
    data = b"\x00\x01\x02"
    result = decode_message(data)
    assert result == data

def test_encode_pydantic_model():
    from pydantic import BaseModel

    class TestMessage(BaseModel):
        type: str
        value: int

    msg = TestMessage(type="test", value=42)
    result = encode_message(msg)
    assert result == b'{"type": "test", "value": 42}'
