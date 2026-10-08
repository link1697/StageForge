from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator


class AgentConfig(BaseModel):
    id: str = Field(..., description="智能体唯一标识符，需与 turn_order 中的字符串匹配")
    name: str = Field(..., description="角色展示名称")
    role: str = Field(..., description="角色在游戏中的身份标签")
    avatar: Optional[str] = Field(default="👤", description="角色头像 Emoji 或图标")
    description: Optional[str] = Field(default="", description="角色背景简介与特征，用于侦探速报指引")
    system_prompt: str = Field(..., description="角色核心人设、已知秘密与行为指引")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="生成随机度")


class GameConfig(BaseModel):
    name: str = Field(..., description="游戏/剧本名称（案情名称）")
    case_name: Optional[str] = Field(None, description="案情别名/专属名称（若未填写则使用 name）")
    description: str = Field(..., description="游戏背景简介")
    case_brief: Optional[str] = Field(None, description="案情通报正文（显示在左侧档案通报栏，若未填写则使用 description）")
    max_rounds: int = Field(default=5, ge=1, description="最大对局轮数")
    turn_order: List[str] = Field(
        ...,
        description="按顺序发言的 ID 列表。保留关键字 'player' 代表终端用户"
    )
    agents: List[AgentConfig] = Field(..., description="所有参与的 AI 角色配置")
    min_accuse_round: int = Field(default=4, ge=1, description="最早允许指认凶手的轮次")
    culprit_id: Optional[str] = Field(None, description="真凶的角色ID")
    truth_revealed: Optional[str] = Field(None, description="真凶案情揭秘与真相说明")
    world_lore: Optional[List[str]] = Field(
        default_factory=list,
        description="万字世界设定集与地理建筑设定，由 Chroma+BM25 双路 RAG 检索动态管理",
    )
    clues: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="物证线索数据库（如金怀表、万能钥匙、毒药瓶），根据提问动态唤醒记忆",
    )

    @model_validator(mode="after")
    def validate_turn_order_and_agents(self) -> "GameConfig":
        if not self.turn_order:
            raise ValueError("turn_order 不能为空")

        agent_ids = [agent.id for agent in self.agents]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError(f"agents 中存在重复的 id: {agent_ids}")

        agent_id_set = set(agent_ids)
        for speaker_id in self.turn_order:
            if speaker_id != "player" and speaker_id not in agent_id_set:
                raise ValueError(
                    f"turn_order 中的角色 '{speaker_id}' 未在 agents 列表中定义"
                )

        if self.culprit_id and self.culprit_id not in agent_id_set:
            raise ValueError(f"culprit_id '{self.culprit_id}' 未在 agents 列表中定义")

        if self.min_accuse_round > self.max_rounds:
            raise ValueError(
                f"min_accuse_round ({self.min_accuse_round}) 不能大于 max_rounds ({self.max_rounds})"
            )

        return self

    def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        """根据 agent_id 查找对应的 AgentConfig"""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None


class Message(BaseModel):
    sender_id: str
    sender_name: str
    content: str
    role: Literal["system", "user", "assistant"]
    round_idx: int
