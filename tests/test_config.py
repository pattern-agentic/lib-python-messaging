from datetime import timedelta
from pattern_agentic_messaging import PASlimP2PConfig, PASlimGroupConfig, SessionMode, GroupMode

def test_p2p_config_defaults():
    config = PASlimP2PConfig(
        local_name="org/ns/app/inst",
        endpoint="https://example.com",
        auth_secret="secret123"
    )
    assert config.max_retries == 5
    assert config.timeout == timedelta(seconds=5)
    assert config.mls_enabled is True
    assert config.mode == SessionMode.ACTIVE

def test_group_config_defaults():
    config = PASlimGroupConfig(
        local_name="org/ns/app/inst",
        endpoint="https://example.com",
        auth_secret="secret123",
        channel_name="org/ns/channel"
    )
    assert config.mode == GroupMode.MODERATOR
    assert config.invites == []
