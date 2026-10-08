import pytest
from pydantic import ValidationError
from src.config.schema import GameConfig, AgentConfig
from src.config.loader import load_game_config, ConfigLoadError


def test_load_valid_config():
    config = load_game_config("configs/detective_mystery.yaml")
    assert config.name == "庄园疑案：审讯室"
    assert config.max_rounds == 7
    assert config.min_accuse_round == 4
    assert config.culprit_id == "agent_butler"
    assert config.truth_revealed is not None
    assert config.turn_order == ["player", "agent_butler", "agent_gardener"]
    assert len(config.agents) == 2
    assert config.get_agent("agent_butler") is not None
    assert config.get_agent("agent_butler").name in ("理查德", "老管家")
    assert config.get_agent("non_existent") is None


def test_invalid_culprit_id():
    data = {
        "name": "测试",
        "description": "描述",
        "max_rounds": 5,
        "turn_order": ["player", "a1"],
        "agents": [
            {"id": "a1", "name": "角色1", "role": "身份", "system_prompt": "提示"}
        ],
        "culprit_id": "ghost_culprit",
    }
    with pytest.raises(ValidationError, match="culprit_id 'ghost_culprit' 未在 agents 列表中定义"):
        GameConfig.model_validate(data)


def test_min_accuse_round_exceeds_max():
    data = {
        "name": "测试",
        "description": "描述",
        "max_rounds": 3,
        "min_accuse_round": 5,
        "turn_order": ["player", "a1"],
        "agents": [
            {"id": "a1", "name": "角色1", "role": "身份", "system_prompt": "提示"}
        ],
    }
    with pytest.raises(ValidationError, match="min_accuse_round.*不能大于 max_rounds"):
        GameConfig.model_validate(data)



def test_config_missing_file():
    with pytest.raises(ConfigLoadError, match="配置文件不存在"):
        load_game_config("configs/not_exist.yaml")


def test_duplicate_agent_ids():
    data = {
        "name": "测试游戏",
        "description": "描述",
        "max_rounds": 3,
        "turn_order": ["player", "a1"],
        "agents": [
            {
                "id": "a1",
                "name": "角色1",
                "role": "身份1",
                "system_prompt": "提示词1",
            },
            {
                "id": "a1",
                "name": "角色2",
                "role": "身份2",
                "system_prompt": "提示词2",
            },
        ],
    }
    with pytest.raises(ValidationError, match="存在重复的 id"):
        GameConfig.model_validate(data)


def test_turn_order_undefined_agent():
    data = {
        "name": "测试游戏",
        "description": "描述",
        "max_rounds": 3,
        "turn_order": ["player", "agent_unknown"],
        "agents": [
            {
                "id": "agent_butler",
                "name": "管家",
                "role": "管家",
                "system_prompt": "提示",
            }
        ],
    }
    with pytest.raises(ValidationError, match="未在 agents 列表中定义"):
        GameConfig.model_validate(data)


def test_empty_turn_order():
    data = {
        "name": "测试游戏",
        "description": "描述",
        "max_rounds": 3,
        "turn_order": [],
        "agents": [],
    }
    with pytest.raises(ValidationError):
        GameConfig.model_validate(data)
