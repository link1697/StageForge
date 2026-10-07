import pytest
from src.config.schema import GameConfig, AgentConfig
from src.llm.client import LLMClient
from src.engine.session import GameSession


@pytest.fixture
def sample_config():
    return GameConfig(
        name="测试庄园",
        description="测试描述",
        max_rounds=5,
        min_accuse_round=3,
        culprit_id="agent_butler",
        truth_revealed="真相是管家干的！",
        turn_order=["player", "agent_butler", "agent_gardener"],
        agents=[
            AgentConfig(
                id="agent_butler",
                name="老管家",
                role="管家",
                system_prompt="你是管家",
            ),
            AgentConfig(
                id="agent_gardener",
                name="年轻园丁",
                role="园丁",
                system_prompt="你是园丁",
            ),
        ],
    )


def test_session_flow_mock(sample_config):
    llm = LLMClient(mock_mode=True)
    session = GameSession(config=sample_config, llm_client=llm)

    state = session.get_state()
    assert state["current_round"] == 1
    assert state["current_speaker"] == "player"
    assert not state["can_accuse"]

    # 玩家发言
    turns = session.player_speak("你们昨晚在哪里？")
    # 期望产生 3 条消息：player, agent_butler, agent_gardener
    assert len(turns) == 3
    assert turns[0].speaker_id == "player"
    assert turns[1].speaker_id == "agent_butler"
    assert turns[2].speaker_id == "agent_gardener"

    # 进入第 2 轮
    state = session.get_state()
    assert state["current_round"] == 2
    assert state["current_speaker"] == "player"


def test_session_accuse_victory(sample_config):
    llm = LLMClient(mock_mode=True)
    session = GameSession(config=sample_config, llm_client=llm)

    res = session.accuse("agent_butler")
    assert res["result"] == "victory"
    assert res["is_correct"] is True
    assert session.result == "victory"


def test_session_accuse_defeat(sample_config):
    llm = LLMClient(mock_mode=True)
    session = GameSession(config=sample_config, llm_client=llm)

    res = session.accuse("agent_gardener")
    assert res["result"] == "defeat"
    assert res["is_correct"] is False
    assert session.result == "defeat"
