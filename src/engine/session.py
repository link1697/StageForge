import os
import sys
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from src.config.schema import GameConfig, Message, AgentConfig
from src.engine.scheduler import TurnScheduler
from src.memory.buffer import MemoryBuffer
from src.memory.rag import HybridRAGEngine
from src.llm.client import LLMClient, LLMClientError
from src.config.strings import (
    get_text,
    LABEL_DETECTIVE_ME,
    LABEL_UNKNOWN_CULPRIT,
    ERROR_GAME_TERMINATED,
    ERROR_NOT_PLAYER_TURN,
    ERROR_SUSPECT_NOT_FOUND,
)



class TurnResult(BaseModel):
    speaker_id: str
    speaker_name: str
    content: str
    round_idx: int
    is_player: bool


class StepResponse(BaseModel):
    current_round: int
    max_rounds: int
    min_accuse_round: int
    can_accuse: bool
    is_terminated: bool
    current_speaker: Optional[str] = None
    messages_produced: List[TurnResult] = []
    status: str  # "in_progress", "awaiting_player", "victory", "defeat"
    game_result: Optional[str] = None  # "victory", "defeat"
    truth_revealed: Optional[str] = None
    error: Optional[str] = None


class GameSession:
    """可步进交互的游戏会话，用于 Web 前端 / API 交互（已集成双路 RAG 记忆检索与 SGLang 加速支持）"""

    def __init__(
        self,
        config: GameConfig,
        llm_client: Optional[LLMClient] = None,
        window_size: int = 10,
    ):
        self.config = config
        self.llm_client = llm_client or LLMClient()
        self.scheduler = TurnScheduler(
            turn_order=config.turn_order,
            max_rounds=config.max_rounds,
        )
        self.memory = MemoryBuffer()
        self.window_size = window_size
        self.accused = False
        self.result: Optional[str] = None
        self.chosen_culprit_id: Optional[str] = None

        # 动态物证状态跟踪 (locked -> available_for_search -> discovered)
        self.clues_state: Dict[str, Dict[str, Any]] = {}
        for c in (getattr(config, "clues", []) or []):
            cid = c.get("id")
            if cid:
                self.clues_state[cid] = {
                    "id": cid,
                    "name": c.get("name", ""),
                    "location": c.get("location", ""),
                    "detail": c.get("detail", ""),
                    "status": c.get("status", "locked"),
                    "action_prompt": c.get("action_prompt", f"搜查并检验 {c.get('name')}"),
                    "unlock_condition": c.get("unlock_condition", {}),
                    "discovered_at_round": None,
                }

        # 初始化双路 RAG 知识检索系统 (Chroma + BM25)
        self.rag = HybridRAGEngine(collection_name=f"lore_{abs(hash(config.name)) % 10000}")
        self._index_world_knowledge()

        # 初始化基于行业标准 Model Context Protocol (MCP) 的环境服务器与客户端
        from src.mcp_server.server import create_game_mcp_server
        from src.mcp_server.client import GameMCPClient
        self.mcp_server = create_game_mcp_server(config=self.config, session_ref=self)
        self.mcp_client = GameMCPClient(mcp_server=self.mcp_server)

    def _index_world_knowledge(self) -> None:
        """预热并索引世界设定集（World Lore）与已公开物证"""
        docs = []
        # 1. 索引剧本世界设定
        if hasattr(self.config, "world_lore") and self.config.world_lore:
            for idx, item in enumerate(self.config.world_lore):
                docs.append({
                    "id": f"lore_{idx}",
                    "content": item,
                    "metadata": {"type": "world_lore", "index": idx},
                })
        # 2. 仅索引已经公开（discovered）的案情线索，严防未发现证据全局泄露
        for cid, clue in self.clues_state.items():
            if clue.get("status") == "discovered":
                clue_text = f"【已确凿物证档案】{clue.get('name', '')}：{clue.get('detail', '')} 发现地点：{clue.get('location', '未知')}"
                docs.append({
                    "id": f"clue_{cid}",
                    "content": clue_text,
                    "metadata": {"type": "clue", "name": clue.get("name", "")},
                })
        if docs:
            self.rag.add_documents(docs)

    def check_clue_triggers(self, speaker_id: str, content: str) -> List[str]:
        """检查当轮发言是否触发隐蔽物证的搜查权限解锁"""
        unlocked_ids = []
        lower_content = content.lower()
        for cid, clue in self.clues_state.items():
            if clue.get("status") != "locked":
                continue

            cond = clue.get("unlock_condition") or {}
            min_round = cond.get("min_round", 1)
            if self.scheduler.current_round < min_round:
                continue

            trigger_spk = cond.get("trigger_speaker", "any")
            if trigger_spk != "any" and trigger_spk != speaker_id:
                continue

            keywords = cond.get("keywords", [])
            if any(kw.lower() in lower_content for kw in keywords):
                clue["status"] = "available_for_search"
                unlocked_ids.append(cid)
        return unlocked_ids

    def search_clue(self, clue_id: str) -> Optional[Dict[str, Any]]:
        """侦探执行搜查指令，将物证正式起获为确凿证据 (discovered) 并同步注入 RAG 与公屏"""
        clue = self.clues_state.get(clue_id)
        if not clue:
            return None

        clue["status"] = "discovered"
        clue["discovered_at_round"] = self.scheduler.current_round

        # 动态将刚起获的物证写入双路 RAG，全场所有人后续将不可抵赖此项证据
        clue_text = f"【已确凿物证档案】{clue.get('name', '')}：{clue.get('detail', '')} 发现地点：{clue.get('location', '未知')}"
        self.rag.add_documents([{
            "id": f"clue_{clue_id}",
            "content": clue_text,
            "metadata": {"type": "clue", "name": clue.get("name", "")},
        }])
        return clue


    def get_state(self) -> Dict[str, Any]:
        """获取当前游戏状态摘要"""
        curr_speaker = self.scheduler.get_current_speaker()
        can_accuse = (
            not self.scheduler.is_terminated()
            and self.scheduler.current_round >= self.config.min_accuse_round
        )
        # 判断是否到达轮次上限需强制指认
        mandatory_accuse = (
            not self.accused
            and (self.scheduler.current_round > self.config.max_rounds or self.scheduler.is_terminated())
            and self.result is None
        )

        status = "in_progress"
        if self.result:
            status = self.result
        elif mandatory_accuse:
            status = "mandatory_accuse"
        elif curr_speaker == "player":
            status = "awaiting_player"

        real_culprit = (
            self.config.get_agent(self.config.culprit_id)
            if self.config.culprit_id
            else None
        )
        chosen_agent = (
            self.config.get_agent(self.chosen_culprit_id)
            if self.chosen_culprit_id
            else None
        )

        return {
            "name": self.config.name,
            "case_name": self.config.case_name or self.config.name,
            "lang": getattr(self.config, "lang", "zh"),
            "default_language": getattr(self.config, "default_language", "zh"),
            "description": self.config.description,
            "case_brief": self.config.case_brief or self.config.description,
            "current_round": min(self.scheduler.current_round, self.config.max_rounds),
            "max_rounds": self.config.max_rounds,
            "min_accuse_round": self.config.min_accuse_round,
            "current_speaker": curr_speaker,
            "can_accuse": can_accuse,
            "is_terminated": self.scheduler.is_terminated(),
            "status": status,
            "game_result": self.result,
            "chosen_name": chosen_agent.name if chosen_agent else None,
            "real_culprit_name": real_culprit.name if real_culprit else None,
            "culprit_revealed": self.config.culprit_id if self.result else None,
            "truth_revealed": self.config.truth_revealed if self.result else None,
            "agents": [
                {
                    "id": a.id,
                    "name": a.name,
                    "role": a.role,
                    "avatar": a.avatar or "👤",
                    "description": a.description or "",
                }
                for a in self.config.agents
            ],
            "turn_order": self.config.turn_order,
            "clues": [
                {
                    "id": c["id"],
                    "name": c["name"] if c["status"] == "discovered" else "未知线索",
                    "location": c["location"] if c["status"] == "discovered" else "未知位置",
                    "detail": c["detail"] if c["status"] == "discovered" else "",
                    "status": c["status"],
                    "action_prompt": c.get("action_prompt", "") if c["status"] == "available_for_search" else "",
                    "discovered_at_round": c.get("discovered_at_round"),
                }
                for c in self.clues_state.values()
            ],
            "messages": [
                {
                    "sender_id": m.sender_id,
                    "sender_name": m.sender_name,
                    "content": m.content,
                    "role": m.role,
                    "round_idx": m.round_idx,
                }
                for m in self.memory.messages
            ],
        }


    def update_language(self, new_lang: str) -> None:
        """热切换游戏运行语言，保留已有回合与记忆，动态更新角色设定与配置"""
        norm_lang = "en" if new_lang.lower().startswith("en") else "zh"
        if getattr(self.config, "lang", "zh") == norm_lang:
            return

        from src.config.translator import translate_game_config
        # 翻译或还原配置，保持当前进度
        self.config = translate_game_config(self.config, target_lang=norm_lang, llm_client=self.llm_client)

        # 同步更新 MCP 服务端的语言数据源
        from src.mcp_server.server import create_game_mcp_server
        from src.mcp_server.client import GameMCPClient
        self.mcp_server = create_game_mcp_server(config=self.config, session_ref=self)
        self.mcp_client = GameMCPClient(mcp_server=self.mcp_server)



    def player_speak(self, text: str) -> List[TurnResult]:
        """玩家提交问话，存入记忆，推进游标，并自动连续推进后续 AI 的回合，直至下一次轮到玩家或游戏结束"""
        lang = getattr(self.config, "lang", "zh")
        if self.scheduler.is_terminated():
            raise RuntimeError(get_text(ERROR_GAME_TERMINATED, lang=lang))

        curr_speaker = self.scheduler.get_current_speaker()
        if curr_speaker != "player":
            raise RuntimeError(get_text(ERROR_NOT_PLAYER_TURN, lang=lang, speaker=curr_speaker))

        round_num = self.scheduler.current_round
        detective_name = get_text(LABEL_DETECTIVE_ME, lang=lang)
        player_turn = TurnResult(
            speaker_id="player",
            speaker_name=detective_name,
            content=text,
            round_idx=round_num,
            is_player=True,
        )
        self.memory.append(
            Message(
                sender_id="player",
                sender_name=detective_name,
                content=text,
                role="user",
                round_idx=round_num,
            )
        )
        self.scheduler.advance()

        results = [player_turn]
        # 持续推进后续 AI
        results.extend(self._run_ai_turns_until_player())
        return results

    def _run_ai_turns_until_player(self) -> List[TurnResult]:
        """自动运行后续所有的 AI 智能体发言，直到再次轮到 player 或游戏轮次结束"""
        results: List[TurnResult] = []

        while not self.scheduler.is_terminated():
            speaker_id = self.scheduler.get_current_speaker()
            if speaker_id == "player":
                # 等待玩家操作
                break

            round_num = self.scheduler.current_round
            agent = self.config.get_agent(speaker_id)
            if not agent:
                raise RuntimeError(f"未找到发言角色配置: {speaker_id}")

            # 1. 获取最新玩家提问或案情焦点，触发双路 RAG 知识召回 (Chroma + BM25)
            last_query = ""
            for msg in reversed(self.memory.messages):
                if msg.role == "user":
                    last_query = msg.content
                    break

            retrieved_lore = self.rag.retrieve(query=last_query, top_k=2) if last_query else []
            lore_prompt_addon = ""
            if retrieved_lore:
                lore_snippets = [f"- {item['content']}" for item in retrieved_lore]
                lore_prompt_addon = (
                    "\n\n【相关世界设定与案发现场记忆（由 RAG 动态召回，回答时保持一致，不可自相矛盾）】:\n"
                    + "\n".join(lore_snippets)
                )

            # 2. 组装增强提示词（包含基础人设 + RAG 知识增强 + MCP 环境工具定义 + 语言约束）
            lang = getattr(self.config, "lang", "zh")
            lang_instruction = ""
            if lang == "en":
                lang_instruction = (
                    "\n\n【Language Requirement】: You MUST speak and respond strictly in English! "
                    "All your dialogue, reactions, and inner defenses MUST be in English only."
                )

            # MCP 协议环境描述（声明 Agent 可交互的 MCP 资产标准）
            mcp_instruction = (
                "\n\n【Model Context Protocol (MCP) Environment】:\n"
                "This scenario is backed by an active MCP Server exposing case tools (`inspect_clue`, `query_manor_lore`, `check_alibi_timeline`). "
                "Base your statements strictly on factual evidence and verified alibis in the manor."
            ) if lang == "en" else (
                "\n\n【Model Context Protocol (MCP) 环境规范】:\n"
                "本案已接入标准 MCP 服务端，提供环境物证与线索工具（`inspect_clue`, `query_manor_lore`, `check_alibi_timeline`）。"
                "你的发言与辩解必须严格符合真实的物证检验结果与时间线事实，不得捏造不存在的证据。"
            )

            # 引擎级多智能体对话对齐底座协议（严格防止任何角色脱离历史对话产生幻觉或凭空树靶）
            grounding_protocol = (
                f"\n\n【审讯对齐与现实锚定协议（引擎级强制守则）】:\n"
                f"1. 当前进度：第 {round_num} 轮审讯（共 {self.config.max_rounds} 轮）。\n"
                f"2. 【严禁凭空树靶与虚构指控】：你所处的场景是现场审讯室。仔细阅读上方对话记录——"
                f"你【只能且必须】针对侦探和同案角色【真实说过的话】做出反应！"
                f"如果对方在上方历史记录中从未提及某件事（例如从未指控你“游荡”、“偷窃”或“杀人”），你【绝对不能】跳出来声称对方说过或在污蔑你，否则视为严重逻辑幻觉与违规！\n"
                f"3. 紧扣侦探本轮的最新提问进行作答与周旋，展现符合你身份的真实心理活动与应激反应。"
            ) if lang != "en" else (
                f"\n\n【Engine Dialogue Grounding Protocol (Strict Rule)】:\n"
                f"1. Current Progress: Round {round_num} of {self.config.max_rounds}.\n"
                f"2. 【Zero Hallucination / No Ghost Arguments】: Closely examine the dialogue history above. "
                f"You MUST ONLY react to what the detective and suspects ACTUALLY stated. "
                f"If an opponent has NOT yet made a specific accusation against you in the transcript above, "
                f"you MUST NEVER claim that they accused or slandered you! Reacting to unsaid words is strictly prohibited.\n"
                f"3. Address the detective's latest question directly within your character role."
            )

            augmented_system_prompt = (
                agent.system_prompt
                + grounding_protocol
                + lore_prompt_addon
                + mcp_instruction
                + lang_instruction
            )

            # 3. 构造滑动窗口上下文（启用显式轮次分界标，隔离跨轮次时间线倒错）
            context = self.memory.get_context_for_agent(
                agent_id=agent.id,
                system_prompt=augmented_system_prompt,
                window_size=self.window_size,
                include_round_headers=True,
            )

            # 4. 执行大模型生成
            reply = self.llm_client.generate_response(
                messages=context,
                temperature=agent.temperature,
            )

            self.memory.append(
                Message(
                    sender_id=agent.id,
                    sender_name=agent.name,
                    content=reply,
                    role="assistant",
                    round_idx=round_num,
                )
            )

            # 5. 实时检测当前角色发言是否透露破绽，从而解锁新的物证搜查权限
            unlocked_clues = self.check_clue_triggers(speaker_id=agent.id, content=reply)

            results.append(
                TurnResult(
                    speaker_id=agent.id,
                    speaker_name=agent.name,
                    content=reply,
                    round_idx=round_num,
                    is_player=False,
                )
            )

            # 如果触发解锁了新的物证，向记忆中广播系统线索提示，让现场气氛进一步升级
            for ucid in unlocked_clues:
                clue_item = self.clues_state.get(ucid)
                if clue_item:
                    notice_text = f"【侦探直觉 / 破绽捕捉】根据 {agent.name} 的证言，已解锁可搜查验证疑点：{clue_item.get('action_prompt')}"
                    self.memory.append(
                        Message(
                            sender_id="system",
                            sender_name="案情系统",
                            content=notice_text,
                            role="system",
                            round_idx=round_num,
                        )
                    )


            self.scheduler.advance()

        return results

    def accuse(self, target_agent_id: str) -> Dict[str, Any]:
        """玩家指认真凶做出裁决"""
        lang = getattr(self.config, "lang", "zh")
        target = self.config.get_agent(target_agent_id)
        if not target:
            raise ValueError(get_text(ERROR_SUSPECT_NOT_FOUND, lang=lang, id=target_agent_id))

        self.accused = True
        self.chosen_culprit_id = target_agent_id
        self.scheduler.terminate()

        is_correct = bool(self.config.culprit_id and target_agent_id == self.config.culprit_id)
        self.result = "victory" if is_correct else "defeat"

        real_culprit = (
            self.config.get_agent(self.config.culprit_id)
            if self.config.culprit_id
            else None
        )

        return {
            "result": self.result,
            "is_correct": is_correct,
            "chosen_name": target.name,
            "real_culprit_name": real_culprit.name if real_culprit else "未知",
            "truth_revealed": self.config.truth_revealed,
        }
