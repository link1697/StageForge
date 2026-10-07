from unittest.mock import patch
from src.config.loader import load_game_config
from src.engine.runtime import GameRuntime
from src.llm.client import LLMClient


def test_runtime_accusation_victory():
    config = load_game_config("configs/detective_mystery.yaml")
    llm = LLMClient(mock_mode=True)
    runtime = GameRuntime(config=config, llm_client=llm)

    # 模拟用户在指认环节选择 1 (老管家，即真凶)
    with patch("builtins.input", return_value="1"):
        success = runtime._handle_accusation(mandatory=False)

    assert success is True
    assert runtime.accused is True
    assert runtime.result == "victory"
    assert runtime.scheduler.is_terminated() is True


def test_runtime_accusation_defeat():
    config = load_game_config("configs/detective_mystery.yaml")
    llm = LLMClient(mock_mode=True)
    runtime = GameRuntime(config=config, llm_client=llm)

    # 模拟用户在指认环节选择 2 (年轻园丁，即错误指认)
    with patch("builtins.input", return_value="2"):
        success = runtime._handle_accusation(mandatory=False)

    assert success is True
    assert runtime.accused is True
    assert runtime.result == "defeat"
    assert runtime.scheduler.is_terminated() is True


def test_runtime_accusation_cancel():
    config = load_game_config("configs/detective_mystery.yaml")
    llm = LLMClient(mock_mode=True)
    runtime = GameRuntime(config=config, llm_client=llm)

    # 模拟用户输入 0 取消指认
    with patch("builtins.input", return_value="0"):
        success = runtime._handle_accusation(mandatory=False)

    assert success is False
    assert runtime.accused is False
    assert runtime.result is None
    assert runtime.scheduler.is_terminated() is False
