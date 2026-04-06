# Pattern Agentic Messaging

An async SLIM wrapper with a FastAPI-like interface

## Installation

```bash
pip install pattern_agentic_messaging
```

## Server

Route messages to decorated handlers based on a discriminator field:

```python
from pattern_agentic_messaging import PASlimApp, PASlimConfig
from .models import QuestionRequest, StatusRequest, AnswerResponse

config = PASlimConfig(
    local_name="org/ns/server",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret-at-least-32-bytes!",
    message_discriminator="type",
)

app = PASlimApp(config)

@app.on_session_connect
async def on_connect(session):
    session.context["agent"] = await create_agent(...)

@app.on_message
async def handle_prompt(session, msg: QuestionRequest):
    agent = session.context["agent"]
    response = await agent.ask(msg.question)
    await session.send(AnswerResponse(answer=response))

@app.on_message
async def handle_status(session, msg: StatusRequest):
    await session.send({"type": "status", "value": "ready"})

@app.on_message
async def handle_other(session, msg):
    await session.send({"error": f"Unknown message type: {msg}"})

app.run()
```

Discriminator models are Pydantic models with a `Literal` field matching the discriminator:

```python
from pydantic import BaseModel
from typing import Literal

class QuestionRequest(BaseModel):
    type: Literal["question"] = "question"
    prompt: str

class AnswerResponse(BaseModel):
    type: Literal["answer"] = "answer"
    answer: str
```

## Authentication

Fluent configuration for three auth modes:

```python
from pattern_agentic_messaging import PASlimConfig

# No auth (for local dev / data planes configured with auth: none)
config = PASlimConfig(local_name="org/ns/app", endpoint="...").with_no_auth()

# Shared secret
config = PASlimConfig(local_name="org/ns/app", endpoint="...").with_shared_secret("my-secret-key-at-least-32-bytes!")

# JWT with JWKS verification
config = PASlimConfig(
    local_name="org/ns/app", endpoint="...",
).with_jwt_auth(
    "path/to/service.token",
    jwks_url="https://auth.example.com/.well-known/jwks.json",
    issuer="my-issuer",
    audience=["svc-b"],
)
```

Passing `auth_secret=` directly still works for backward compatibility with shared secret auth.

### MessageContext

Handlers can optionally receive SLIM message context (sender identity, metadata, etc.) by adding a typed parameter:

```python
from pattern_agentic_messaging import MessageContext

@app.on_message
async def handle(session, msg, msg_context: MessageContext):
    print(msg_context.source_name)       # sender identity
    print(msg_context.destination_name)   # destination
    print(msg_context.metadata)           # sender-supplied k/v pairs
```

Handlers without this parameter work as before.

## Client

Connect to a specific peer:

```python
config = PASlimConfig(
    local_name="org/ns/client",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret-at-least-32-bytes!",
)

async with PASlimApp(config) as app:
    async with await app.connect("org/ns/server") as session:
        await session.send({"type": "prompt", "prompt": "Hello world!"})
        async for msg in session:
            print(f"RECEIVED: {msg}")
```

Join a group channel:

```python
async with PASlimApp(config) as app:
    async with await app.join_channel() as session:
        async for msg in session:
            await session.send({"type": "response", "msg": "received"})
```

## A2A Message Models

Lightweight Pydantic models for the [A2A protocol](https://a2a-protocol.org/) message types, useful for constructing A2A-compliant payloads from clients:

```python
from pattern_agentic_messaging.a2a import Message, Part, Role

msg = Message(role=Role.USER, parts=[Part.from_text("What time is it?")])
await session.send(msg.model_dump(by_alias=True, exclude_none=True))
```

## Low-level usage

The decorator pattern's underlying API can be used directly:

```python
async with PASlimApp(config) as app:
    async for session, msg in app:
        result = await process(msg["prompt"])
        await session.send({"result": result})
```

## Message Types

All messages carry a `metadata.__pa_type` discriminator. See [docs/message-types.md](docs/message-types.md).

