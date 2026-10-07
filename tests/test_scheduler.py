import pytest
from src.engine.scheduler import TurnScheduler


def test_scheduler_lifecycle():
    turn_order = ["player", "agent_butler", "agent_gardener"]
    scheduler = TurnScheduler(turn_order=turn_order, max_rounds=2)

    assert not scheduler.is_terminated()
    assert scheduler.current_round == 1
    assert scheduler.get_current_speaker() == "player"

    # Turn 1 -> agent_butler
    scheduler.advance()
    assert scheduler.current_round == 1
    assert scheduler.get_current_speaker() == "agent_butler"

    # Turn 2 -> agent_gardener
    scheduler.advance()
    assert scheduler.current_round == 1
    assert scheduler.get_current_speaker() == "agent_gardener"

    # Turn 3 -> round 2, player
    scheduler.advance()
    assert scheduler.current_round == 2
    assert scheduler.get_current_speaker() == "player"

    # Round 2: agent_butler
    scheduler.advance()
    assert scheduler.current_round == 2
    assert scheduler.get_current_speaker() == "agent_butler"

    # Round 2: agent_gardener
    scheduler.advance()
    assert scheduler.current_round == 2
    assert scheduler.get_current_speaker() == "agent_gardener"

    # End of round 2 -> should terminate
    scheduler.advance()
    assert scheduler.current_round == 3
    assert scheduler.is_terminated()
    assert scheduler.get_current_speaker() is None


def test_invalid_scheduler_init():
    with pytest.raises(ValueError, match="turn_order 不能为空"):
        TurnScheduler(turn_order=[], max_rounds=3)

    with pytest.raises(ValueError, match="max_rounds 必须大于或等于 1"):
        TurnScheduler(turn_order=["player"], max_rounds=0)
