"""LLM Translation Module for Game Configs.

Supports translating GameConfig content (name, description, case_brief, agent names/roles/descriptions,
lore, clues, truth_revealed) using LLMClient with fallback to deterministic local templates
if the LLM API is unavailable, throttled, or times out.
"""

from typing import Dict, Any, List, Optional
import copy
import json
import logging
from src.config.schema import GameConfig, AgentConfig
from src.llm.client import LLMClient

logger = logging.getLogger(__name__)


# Built-in offline fallback dictionaries for default scenario configs when API call is unavailable
OFFLINE_TRANSLATIONS: Dict[str, Dict[str, Dict[str, str]]] = {
    "en": {
        "庄园疑案：审讯室": {
            "name": "Manor Mystery: Interrogation Room",
            "case_name": "Blackstone Manor Murder Case",
            "description": "The old Earl was murdered in the study, and his pocket watch is missing. On a stormy night, you isolate and interrogate the two prime suspects: the Butler and the Gardener.",
            "case_brief": "The old Earl was brutally murdered in his locked study, and his heirloom pocket watch vanished. On this stormy night, you have sealed the gates and confined the two prime suspects—the butler and the gardener—to the interrogation room.",
            "truth_revealed": "The truth is revealed! Having discovered the old butler's years of embezzlement, the Earl intended to dismiss him. Bearing a deep grudge, the butler used his master keys to sneak into the study, struck the Earl with a brass candlestick causing his death, and concealed the bloody garments and ledger in a black cloth bag. Although the young gardener stole the pocket watch, the Earl was already dead when he entered. The butler attempted to frame the gardener, but the true culprit is the butler!",
            "agents": {
                "agent_butler": {
                    "name": "Richard",
                    "role": "Head Butler (Suspect)",
                    "description": "Served the manor for 40 years. Impeccable and composed, claims he was in the servants' quarters and had no key.",
                    "system_prompt": (
                        "You are the butler Richard, having served the manor for 40 years, but you are the true murderer of the Earl! "
                        "The Earl found out you embezzled money for years and planned to fire you. Bearing a grudge, you used your master key to enter the study last night, killed the Earl with a brass candlestick, and hid the bloody clothes and false ledger in a black cloth bag. "
                        "You happened to see the gardener sneak in to steal the golden pocket watch, so you vigorously pin the murder on the gardener to frame him. "
                        "【Guidelines】: 1. You MUST answer the detective's questions in fluent English! 2. Control length within 120 words. 3. Be polite, formal, but deceitful."
                    ),
                },
                "agent_gardener": {
                    "name": "Tom",
                    "role": "Gardener (Suspect)",
                    "description": "Hot-tempered and indebted with gambling debts, claims he was only passing by and accuses the butler.",
                    "system_prompt": (
                        "You are Tom the gardener. You owe gambling debts and sneaked into the study last night to steal the golden pocket watch, but the Earl was already dead in a pool of blood when you got in! You did NOT kill him! "
                        "【Guidelines】: 1. You MUST answer the detective's questions in fluent English! Address what the detective asked directly and do NOT introduce unrelated facts abruptly. 2. Control length within 120 words. 3. Be hot-tempered, fiercely deny murder, and accuse the butler."
                    ),
                },
            },
        },
    },
    "zh": {
        # Defaults are already Chinese
    }
}


from src.config.strings import register_story_strings


def extract_scenario_id(config: GameConfig) -> str:
    """Generate a clean scenario ID from config name or case_name."""
    name = config.case_name or config.name
    # Use name or sanitized ascii
    return "manor_mystery" if "庄园" in name or "Manor" in name else "scenario_default"


def register_config_story_strings(config: GameConfig, lang: Optional[str] = None) -> str:
    """Extract all story and narrative text from GameConfig and register into strings registry."""
    scenario_id = extract_scenario_id(config)
    target_lang = lang or getattr(config, "lang", "zh") or "zh"

    story_map: Dict[str, str] = {
        "name": config.name,
        "case_name": config.case_name or config.name,
        "description": config.description,
        "case_brief": config.case_brief or config.description,
        "truth_revealed": config.truth_revealed or "",
    }

    for agent in config.agents:
        story_map[f"agent.{agent.id}.name"] = agent.name
        story_map[f"agent.{agent.id}.role"] = agent.role
        story_map[f"agent.{agent.id}.description"] = agent.description or ""
        story_map[f"agent.{agent.id}.system_prompt"] = agent.system_prompt or ""

    register_story_strings(scenario_id, story_map, lang=target_lang)
    return scenario_id


def translate_game_config(
    config: GameConfig,
    target_lang: str,
    llm_client: Optional[LLMClient] = None,
) -> GameConfig:
    """Translates a GameConfig into the target language ('zh' or 'en').

    Checks config.default_language:
    - First registers original story strings into registry under default_language.
    - If target_lang matches default_language, returns original config.
    - If target_lang differs, translates and registers translated story strings.
    """
    default_lang = (getattr(config, "default_language", None) or "zh").lower()
    norm_target = target_lang.lower()

    # Always register original story strings in registry
    register_config_story_strings(config, lang=default_lang)

    if norm_target == default_lang or norm_target.startswith(default_lang):
        config_copy = config.model_copy(deep=True)
        config_copy.lang = norm_target
        return config_copy

    translated = config.model_copy(deep=True)

    # Prepare fields to translate
    source_payload = {
        "name": config.name,
        "case_name": config.case_name or config.name,
        "description": config.description,
        "case_brief": config.case_brief or config.description,
        "truth_revealed": config.truth_revealed or "",
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "role": a.role,
                "description": a.description or "",
            }
            for a in config.agents
        ],
    }

    translated_data = None

    # Try LLM Translation if client is provided and not in pure mock mode
    if llm_client and not getattr(llm_client, "mock_mode", False) and getattr(llm_client, "client", None):
        try:
            prompt = (
                "You are an expert game localization translator. "
                "Translate the following murder mystery game configuration JSON into English. "
                "Keep the JSON structure, keys, and agent IDs unchanged. Translate only the values. "
                "Output ONLY a valid JSON object without markdown formatting or code blocks:\n\n"
                f"{json.dumps(source_payload, ensure_ascii=False, indent=2)}"
            )
            # Use lower temperature for translation fidelity
            response = llm_client.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            clean_resp = response.strip()
            if clean_resp.startswith("```"):
                lines = clean_resp.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean_resp = "\n".join(lines).strip()
            translated_data = json.loads(clean_resp)
        except Exception as e:
            logger.warning("LLM translation failed or timed out (%s), applying offline fallback.", e)
            translated_data = None

    # Fallback to offline translation dictionary if LLM translation wasn't successful
    if not translated_data:
        translated_data = _apply_offline_fallback(source_payload, target_lang)

    # Apply translated fields
    if translated_data:
        if "name" in translated_data and translated_data["name"]:
            translated.name = translated_data["name"]
        if "case_name" in translated_data and translated_data["case_name"]:
            translated.case_name = translated_data["case_name"]
        if "description" in translated_data and translated_data["description"]:
            translated.description = translated_data["description"]
        if "case_brief" in translated_data and translated_data["case_brief"]:
            translated.case_brief = translated_data["case_brief"]
        if "truth_revealed" in translated_data and translated_data["truth_revealed"]:
            translated.truth_revealed = translated_data["truth_revealed"]

        # Agents
        agent_trans_map = {
            a["id"]: a for a in translated_data.get("agents", []) if isinstance(a, dict) and "id" in a
        }
        for agent in translated.agents:
            if agent.id in agent_trans_map:
                info = agent_trans_map[agent.id]
                if info.get("name"):
                    agent.name = info["name"]
                if info.get("role"):
                    agent.role = info["role"]
                if info.get("description"):
                    agent.description = info["description"]
                if info.get("system_prompt"):
                    agent.system_prompt = info["system_prompt"]

    translated.lang = target_lang
    # Register translated story strings into strings registry under target_lang
    register_config_story_strings(translated, lang=target_lang)
    return translated



def _apply_offline_fallback(payload: Dict[str, Any], lang: str) -> Dict[str, Any]:
    """Generates an offline fallback translation for known scenarios or heuristic defaults."""
    res = copy.deepcopy(payload)
    lang_dict = OFFLINE_TRANSLATIONS.get(lang, {})

    # Check matching scenario by name
    name = payload.get("name", "")
    if name in lang_dict:
        match = lang_dict[name]
        res["name"] = match.get("name", res["name"])
        res["case_name"] = match.get("case_name", res["case_name"])
        res["description"] = match.get("description", res["description"])
        res["case_brief"] = match.get("case_brief", res["case_brief"])
        res["truth_revealed"] = match.get("truth_revealed", res["truth_revealed"])
        agent_matches = match.get("agents", {})
        for agent in res.get("agents", []):
            aid = agent.get("id")
            if aid in agent_matches:
                agent.update(agent_matches[aid])
        return res

    # Heuristic fallback for other scenarios
    res["name"] = f"{payload.get('name', 'Mystery')} (EN)"
    res["case_name"] = f"{payload.get('case_name', payload.get('name', 'Mystery'))} (EN)"
    return res
