# Pattern Agentic Messaging

An async SLIM wrapper with FastAPI-like interface

## Installation

```bash
pip install pattern_agentic_messaging
```

## Usage


### Server

Route messages to decorated methods based on a _discriminator_ field
like `type`:

```
from pattern_agentic_messaging import PASlimApp, PASlimConfig

config = PASlimConfig(
    local_name="org/ns/server/instance1",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret"
)

app = PASlimApp(config)
agent = None

@app.on_session_connect
async def on_connect(session):
    agent = await create_agent(...)
    session.context = {
        "agent": agent
    }
    
@app.on_message('type', 'prompt')
async def handle_prompt(session, msg):
    agent = session.context.get("agent")
    response = await agent.ask(msg["prompt"])
    await session.send({"type": "response", "answer": response})

@app.on_message('type', 'status')
async def handle_status(session, msg):
    await session.send({"type": "status", "value": "ready"})

@app.on_message
async def handle_other(session, msg):
    await session.send({"error": f"Unknown message type: {msg.get('type')}"})

app.run()
```

Use `PASlimConfigGroup` to create a group channel. 

### Client

Connect to a specific peer:

```python
from pattern_agentic_messaging import PASlimApp, PASlimConfig

config = PASlimConfig(
    local_name="org/ns/client/instance1",
    endpoint="https://slim.example.com",
    auth_secret="shared-secret"
)

async with PASlimApp(config) as app:
    async with await app.connect("org/ns/server/instance1") as session:
        await session.send({"type": "prompt", "prompt": "Hello world!"})
        async for msg in session:
            print(f"RECEIVED: {msg}")
```


Alternatively to join a group channel:

```python
from pattern_agentic_messaging import PASlimApp, PASlimConfig

config = PASlimConfig(
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


## Low-level usage

The API behind the decorator pattern can be used directly:

```python
from pattern_agentic_messaging import PASlimApp, PASlimConfig

config = PASlimConfig(
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

