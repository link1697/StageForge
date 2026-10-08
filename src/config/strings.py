"""Localization Strings & Constants Management (i18n).

Centralizes all user-facing strings (API responses, errors, UI prompts, scenario descriptions).
Usage:
    from src.config.strings import get_text, ERROR_GAME_NOT_INIT, MSG_GAME_STARTED
    msg = get_text(ERROR_GAME_NOT_INIT, lang="en")
"""

from typing import Dict, Any, Optional

# ==============================================================================
# String Keys / Constants
# ==============================================================================

# API & Server Messages
MSG_GAME_STARTED = "MSG_GAME_STARTED"
MSG_LANGUAGE_UPDATED = "MSG_LANGUAGE_UPDATED"
MSG_INDEX_NOT_FOUND = "MSG_INDEX_NOT_FOUND"
ERROR_CONFIG_NOT_FOUND = "ERROR_CONFIG_NOT_FOUND"
ERROR_CONFIG_PARSE = "ERROR_CONFIG_PARSE"
ERROR_GAME_NOT_INIT = "ERROR_GAME_NOT_INIT"
ERROR_SPEECH_EMPTY = "ERROR_SPEECH_EMPTY"
ERROR_GAME_TERMINATED = "ERROR_GAME_TERMINATED"
ERROR_NOT_PLAYER_TURN = "ERROR_NOT_PLAYER_TURN"
ERROR_SUSPECT_NOT_FOUND = "ERROR_SUSPECT_NOT_FOUND"
ERROR_EXECUTION_FAILED = "ERROR_EXECUTION_FAILED"
ERROR_LLM_FAILED = "ERROR_LLM_FAILED"

# Role & UI Labels
LABEL_DETECTIVE_ME = "LABEL_DETECTIVE_ME"
LABEL_UNKNOWN_CULPRIT = "LABEL_UNKNOWN_CULPRIT"
LABEL_WAITING_FOR_DETECTIVE = "LABEL_WAITING_FOR_DETECTIVE"
LABEL_INTERROGATION_BUSY = "LABEL_INTERROGATION_BUSY"

# Dictionaries of localized strings
STRINGS_REGISTRY: Dict[str, Dict[str, str]] = {
    "zh": {
        MSG_GAME_STARTED: "游戏已启动",
        MSG_LANGUAGE_UPDATED: "语言已更新",
        MSG_INDEX_NOT_FOUND: "前端 index.html 尚未创建",
        ERROR_CONFIG_NOT_FOUND: "配置文件不存在: {path}",
        ERROR_CONFIG_PARSE: "配置文件解析错误: {error}",
        ERROR_GAME_NOT_INIT: "游戏尚未初始化，请先启动对局",
        ERROR_SPEECH_EMPTY: "发言内容不能为空",
        ERROR_GAME_TERMINATED: "游戏已结束，无法继续发言",
        ERROR_NOT_PLAYER_TURN: "当前不是玩家发言回合，当前发言者为: {speaker}",
        ERROR_SUSPECT_NOT_FOUND: "未找到指定的嫌疑人: {id}",
        ERROR_EXECUTION_FAILED: "执行异常: {error}",
        ERROR_LLM_FAILED: "LLM 调用异常: {error}",
        LABEL_DETECTIVE_ME: "侦探(你)",
        LABEL_UNKNOWN_CULPRIT: "未知真凶",
        LABEL_WAITING_FOR_DETECTIVE: "等待侦探发言...",
        LABEL_INTERROGATION_BUSY: "审讯进行中...",
    },
    "en": {
        MSG_GAME_STARTED: "Game started successfully",
        MSG_LANGUAGE_UPDATED: "Language updated successfully",
        MSG_INDEX_NOT_FOUND: "Frontend index.html has not been created yet",
        ERROR_CONFIG_NOT_FOUND: "Configuration file does not exist: {path}",
        ERROR_CONFIG_PARSE: "Failed to parse configuration: {error}",
        ERROR_GAME_NOT_INIT: "Game is not initialized. Please start a new game first.",
        ERROR_SPEECH_EMPTY: "Speech content cannot be empty",
        ERROR_GAME_TERMINATED: "The game has already concluded. Cannot speak further.",

        ERROR_NOT_PLAYER_TURN: "It is not currently the player's turn to speak. Current speaker: {speaker}",
        ERROR_SUSPECT_NOT_FOUND: "Specified suspect not found: {id}",
        ERROR_EXECUTION_FAILED: "Execution exception: {error}",
        ERROR_LLM_FAILED: "LLM call failed: {error}",
        LABEL_DETECTIVE_ME: "Detective (You)",
        LABEL_UNKNOWN_CULPRIT: "Unknown Culprit",
        LABEL_WAITING_FOR_DETECTIVE: "Waiting for detective...",
        LABEL_INTERROGATION_BUSY: "Interrogation in progress...",
    },
}



# Scenario & Story Text Keys Template
STORY_KEY_NAME = "story.{scenario_id}.name"
STORY_KEY_CASE_NAME = "story.{scenario_id}.case_name"
STORY_KEY_DESCRIPTION = "story.{scenario_id}.description"
STORY_KEY_CASE_BRIEF = "story.{scenario_id}.case_brief"
STORY_KEY_TRUTH_REVEALED = "story.{scenario_id}.truth_revealed"
STORY_KEY_AGENT_NAME = "story.{scenario_id}.agent.{agent_id}.name"
STORY_KEY_AGENT_ROLE = "story.{scenario_id}.agent.{agent_id}.role"
STORY_KEY_AGENT_DESC = "story.{scenario_id}.agent.{agent_id}.description"
STORY_KEY_AGENT_SYSTEM_PROMPT = "story.{scenario_id}.agent.{agent_id}.system_prompt"


def get_text(key: str, lang: Optional[str] = "zh", **kwargs: Any) -> str:
    """Retrieve localized string by key and language with format arguments."""
    normalized_lang = "en" if (lang and str(lang).lower().startswith("en")) else "zh"
    table = STRINGS_REGISTRY.get(normalized_lang, STRINGS_REGISTRY["zh"])
    template = table.get(key) or STRINGS_REGISTRY["zh"].get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template


def register_story_strings(scenario_id: str, strings_dict: Dict[str, str], lang: str = "zh") -> None:
    """Register story/narrative text paragraphs into the central registry under a language namespace.

    Args:
        scenario_id: Identifier for the scenario (e.g. 'manor_mystery' or hash/name).
        strings_dict: Mapping of relative keys (e.g. 'name', 'case_brief', 'agent.agent_butler.role') -> text
        lang: Target language ('zh' or 'en')
    """
    normalized_lang = "en" if lang.lower().startswith("en") else "zh"
    if normalized_lang not in STRINGS_REGISTRY:
        STRINGS_REGISTRY[normalized_lang] = {}

    table = STRINGS_REGISTRY[normalized_lang]
    for key, text in strings_dict.items():
        if text is not None:
            full_key = f"story.{scenario_id}.{key}"
            table[full_key] = str(text)


def get_story_text(scenario_id: str, sub_key: str, lang: Optional[str] = "zh", fallback: str = "") -> str:
    """Retrieve a scenario-specific narrative string by scenario_id and sub_key."""
    full_key = f"story.{scenario_id}.{sub_key}"
    val = get_text(full_key, lang=lang)
    if val == full_key:
        return fallback
    return val

