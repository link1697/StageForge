import os
import sys
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from src.config.schema import GameConfig, Message, AgentConfig
from src.engine.scheduler import TurnScheduler
from src.memory.buffer import MemoryBuffer
from src.memory.rag import HybridRAGEngine
from src.llm.client import LLMClient, LLMClientError


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

        # 初始化双路 RAG 知识检索系统 (Chroma + BM25)
        self.rag = HybridRAGEngine(collection_name=f"lore_{abs(hash(config.name)) % 10000}")
        self._index_world_knowledge()

    def _index_world_knowledge(self) -> None:
        """预热并索引世界设定集（World Lore）与物证库（Clues）"""
        docs = []
        # 1. 索引剧本世界设定
        if hasattr(self.config, "world_lore") and self.config.world_lore:
            for idx, item in enumerate(self.config.world_lore):
                docs.append({
                    "id": f"lore_{idx}",
                    "content": item,
                    "metadata": {"type": "world_lore", "index": idx},
                })
        # 2. 索引案情线索数据库
        if hasattr(self.config, "clues") and self.config.clues:
            for idx, clue in enumerate(self.config.clues):
                clue_text = f"【物证档案】{clue.get('name', '')}：{clue.get('detail', '')} 发现地点：{clue.get('location', '未知')}"
                docs.append({
                    "id": f"clue_{clue.get('id', idx)}",
                    "content": clue_text,
                    "metadata": {"type": "clue", "name": clue.get("name", "")},
                })
        if docs:
            self.rag.add_documents(docs)

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

    def player_speak(self, text: str) -> List[TurnResult]:
        """玩家提交问话，存入记忆，推进游标，并自动连续推进后续 AI 的回合，直至下一次轮到玩家或游戏结束"""
        if self.scheduler.is_terminated():
            raise RuntimeError("游戏已结束，无法继续发言")

        curr_speaker = self.scheduler.get_current_speaker()
        if curr_speaker != "player":
            raise RuntimeError(f"当前不是玩家发言回合，当前发言者为: {curr_speaker}")

        round_num = self.scheduler.current_round
        player_turn = TurnResult(
            speaker_id="player",
            speaker_name="侦探(你)",
            content=text,
            round_idx=round_num,
            is_player=True,
        )
        self.memory.append(
            Message(
                sender_id="player",
                sender_name="侦探(你)",
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

            # 2. 组装增强提示词（包含基础人设 + RAG 知识增强）
            augmented_system_prompt = agent.system_prompt + lore_prompt_addon

            # 3. 构造滑动窗口上下文
            context = self.memory.get_context_for_agent(
                agent_id=agent.id,
                system_prompt=augmented_system_prompt,
                window_size=self.window_size,
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

            results.append(
                TurnResult(
                    speaker_id=agent.id,
                    speaker_name=agent.name,
                    content=reply,
                    round_idx=round_num,
                    is_player=False,
                )
            )

            self.scheduler.advance()

        return results

    def accuse(self, target_agent_id: str) -> Dict[str, Any]:
        """玩家指认真凶做出裁决"""
        target = self.config.get_agent(target_agent_id)
        if not target:
            raise ValueError(f"未找到指定的嫌疑人: {target_agent_id}")

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
