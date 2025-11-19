# Pattern Agentic Messaging

Pythonic async wrapper for SLIM messaging.

## Installation

```bash
pip install pattern_agentic_messaging
```

## Usage

### Point-to-Point (Active)

Connect to a specific peer:

```python
from pattern_agentic_messaging import PASlimApp, PASlimConfigBase

config = PASlimConfigBase(
    local_name="org/ns/client/instance1",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret"
)

async with PASlimApp(config) as app:
    async with await app.connect("org/ns/server/instance1") as session:
        async for msg in session:
            if msg.get("type") == "ping":
                await session.send({"type": "pong"})
```

### Multi-Session Server

Handle multiple concurrent clients with automatic lifecycle management:

```python
from pattern_agentic_messaging import PASlimApp, PASlimConfigBase

config = PASlimConfigBase(
    local_name="org/ns/server/instance1",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret"
)

async with PASlimApp(config) as app:
    async for session, msg in app:
        if not isinstance(msg, dict) or "prompt" not in msg:
            await session.send({"error": "Invalid format"})
            continue

        result = await process(msg["prompt"])
        await session.send({"result": result})
```

#### Session Context Storage

Each session has a unique `session_id` and a `context` dict for storing per-session state:

```python
# Pattern 1: Using session.context dict
async with PASlimApp(config) as app:
    async for session, msg in app:
        if not session.context:
            session.context["agent"] = await create_agent()
            session.context["user"] = msg.get("user_id")

        agent = session.context["agent"]
        response = await agent.process(msg)
        await session.send(response)

# Pattern 2: External storage with session_id
sessions = {}

async with PASlimApp(config) as app:
    async for session, msg in app:
        if session.session_id not in sessions:
            sessions[session.session_id] = {
                "created": datetime.now(),
                "state": "active"
            }

        # Use session.session_id for logging
        logger.info(f"Session {session.session_id}: {msg}")
```

### Decorator Pattern (Simplified)

For the simplest usage, use the decorator pattern with automatic event loop and signal handling:

```python
from pattern_agentic_messaging import PASlimApp, PASlimConfigBase

config = PASlimConfigBase(
    local_name="org/ns/server/instance1",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret"
)

app = PASlimApp(config)

@app.on_message('type', 'prompt')
async def handle_prompt(session, msg):
    """Handle prompt messages."""
    agent = session.context.get("agent")
    response = await agent.ask(msg["prompt"])
    await session.send({"type": "response", "answer": response})

@app.on_message('type', 'status')
async def handle_status(session, msg):
    """Handle status requests."""
    await session.send({"type": "status", "value": "ready"})

@app.on_message
async def handle_other(session, msg):
    """Catch-all for unhandled message types."""
    await session.send({"error": f"Unknown message type: {msg.get('type')}"})

app.run()
```

**Note:** If a message doesn't match any filtered handler and no catch-all is defined, a warning is logged.


### Group (Moderator)

Create a channel and invite participants:

```python
from pattern_agentic_messaging import PASlimApp, PASlimConfigBase

config = PASlimConfigBase(
    local_name="org/ns/moderator/inst",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret"
)

async with PASlimApp(config) as app:
    async with await app.create_channel(
        "org/ns/channel/main",
        invites=["org/ns/participant/p1", "org/ns/participant/p2"]
    ) as session:
        await session.send({"type": "broadcast", "msg": "hello all"})
        async for msg in session:
            print(f"Received: {msg}")
```

### Group (Participant)

Join a channel by accepting an invite:

```python
from pattern_agentic_messaging import PASlimApp, PASlimConfigBase

config = PASlimConfigBase(
    local_name="org/ns/participant/p1",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret"
)

async with PASlimApp(config) as app:
    async with await app.join_channel() as session:
        async for msg in session:
            print(f"Channel message: {msg}")
            await session.send({"type": "response", "msg": "received"})
```
