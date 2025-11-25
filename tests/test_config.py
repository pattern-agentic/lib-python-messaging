from datetime import timedelta
from pattern_agentic_messaging import PASlimConfigP2P, PASlimConfigGroup, SessionMode, GroupMode

def test_p2p_config_defaults():
    config = PASlimConfigP2P(
        local_name="org/ns/app/inst",
        endpoint="https://example.com",
        auth_secret="secret123"
    )
    assert config.max_retries == 5
    assert config.timeout == timedelta(seconds=5)
    assert config.mls_enabled is True
    assert config.mode == SessionMode.ACTIVE

def test_group_config_defaults():
    config = PASlimConfigGroup(
        local_name="org/ns/app/inst",
        endpoint="https://example.com",
        auth_secret="secret123",
        channel_name="org/ns/channel"
    )
    assert config.mode == GroupMode.MODERATOR
    assert config.invites == []
