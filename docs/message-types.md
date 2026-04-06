# Message Types

All messages carry a `metadata.__pa_type` discriminator field that identifies the payload structure.

## `a2a.message`

Standard A2A `Message`. Used for all conversation messages between users and agents.

```json
{
  "role": "ROLE_USER",
  "parts": [{"text": "hello", "mediaType": "text/plain"}],
  "contextId": "session-uuid",
  "messageId": "msg-uuid",
  "metadata": {"__pa_type": "a2a.message"}
}
```

Parsed with `pattern_agentic_messaging.a2a.Message`.

## `a2a.task_status`

A2A `TaskStatusUpdateEvent`. Used for task state transitions (working, completed, failed).

```json
{
  "taskId": "task-uuid",
  "contextId": "session-uuid",
  "status": {
    "state": "TASK_STATE_FAILED",
    "message": {"role": "ROLE_AGENT", "parts": [{"text": "error details"}]}
  },
  "metadata": {"__pa_type": "a2a.task_status"}
}
```

## `system_error`

Framework-level error. The message was rejected before reaching the agent (e.g. invalid session token, unauthorized).

```json
{
  "error": "invalid_session_token",
  "detail": "Missing x-pa-session-token in message metadata",
  "metadata": {"__pa_type": "system_error"}
}
```

Parsed with `pattern_agentic_messaging.PASystemError`.

## Utilities

```python
from pattern_agentic_messaging import (
    PAType,           # Constants: A2A_MESSAGE, A2A_TASK_STATUS, SYSTEM_ERROR
    PA_TYPE_KEY,      # "__pa_type"
    tag_a2a_message,  # Adds __pa_type to an A2A message dict
    get_pa_type,      # Reads __pa_type from a payload
    PASystemError,    # Pydantic model for system errors
)
```
