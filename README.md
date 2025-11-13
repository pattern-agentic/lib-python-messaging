# Pattern Agentic Messaging

Pythonic async wrapper for SLIM messaging.

## Installation

```bash
pip install pattern_agentic_messaging
```

## Usage

### Point-to-Point (Active)

```python
from pattern_agentic_messaging import PASlimApp, PASlimP2PConfig, SessionMode

config = PASlimP2PConfig(
    local_name="org/ns/client/instance1",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret",
    peer_name="org/ns/server/instance1",
    mode=SessionMode.ACTIVE
)

async with PASlimApp(config) as app:
    async with await app.create_session(config) as session:
        async for msg in session:
            if msg.get("type") == "ping":
                await session.send({"type": "pong"})
```

### Point-to-Point (Passive)

```python
config = PASlimP2PConfig(
    local_name="org/ns/server/instance1",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret",
    mode=SessionMode.PASSIVE
)

async with PASlimApp(config) as app:
    async with await app.create_session(config) as session:
        async for msg in session:
            await session.send({"status": "received"})
```

### Group (Moderator)

```python
from pattern_agentic_messaging import PASlimGroupConfig, GroupMode

config = PASlimGroupConfig(
    local_name="org/ns/moderator/inst",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret",
    channel_name="org/ns/channel/main",
    mode=GroupMode.MODERATOR,
    invites=["org/ns/participant/p1", "org/ns/participant/p2"]
)

async with PASlimApp(config) as app:
    async with await app.create_session(config) as session:
        await session.send({"type": "broadcast", "msg": "hello all"})
        async for msg in session:
            print(f"Received: {msg}")
```

### Request-Response

```python
async with session:
    response = await session.request({"query": "status"}, timeout=5.0)
    print(response)
```

### Callbacks

```python
async def handle_message(msg):
    print(f"Got: {msg}")

async with session:
    session.on_message(handle_message)
    await session.send({"type": "init"})
```

