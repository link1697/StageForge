import pytest
from pathlib import Path
from src.config.loader import load_game_config
from src.config.translator import translate_game_config


def test_translate_game_config_en():
    cfg_path = Path("configs/detective_mystery.yaml")
    config = load_game_config(cfg_path)

    # 1. 默认 zh 应保持原样
    zh_config = translate_game_config(config, target_lang="zh")
    assert zh_config.name == "庄园疑案：审讯室"
    assert zh_config.agents[0].name == "理查德"

    # 2. 翻译为 en (包含离线高质量兜底机制与字段映射)
    en_config = translate_game_config(config, target_lang="en")
    assert en_config.name == "Manor Mystery: Interrogation Room"
    assert en_config.case_name == "Blackstone Manor Murder Case"
    assert "Earl" in en_config.description or "Manor" in en_config.description
    assert en_config.agents[0].name == "Richard"
    assert "Butler" in en_config.agents[0].role
    assert en_config.agents[1].name == "Tom"
    assert "Gardener" in en_config.agents[1].role
    assert en_config.culprit_id == config.culprit_id


def test_story_strings_separation():
    """验证故事背景、案情描述与角色档案被完全抽离并注册到本地化字串仓库中"""
    from src.config.strings import get_story_text, get_text

    cfg_path = Path("configs/detective_mystery.yaml")
    config = load_game_config(cfg_path)

    # 验证中文抽取注册
    zh_brief = get_story_text("manor_mystery", "case_brief", lang="zh")
    assert "紧锁的书房" in zh_brief
    zh_butler_role = get_story_text("manor_mystery", "agent.agent_butler.role", lang="zh")
    assert "总管" in zh_butler_role

    # 翻译为英文后，英文仓库中也完成了对应的分离注册
    translate_game_config(config, target_lang="en")
    en_brief = get_story_text("manor_mystery", "case_brief", lang="en")
    assert "stormy night" in en_brief or "locked study" in en_brief
    en_butler_role = get_story_text("manor_mystery", "agent.agent_butler.role", lang="en")
    assert "Butler" in en_butler_role

