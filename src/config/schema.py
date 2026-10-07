from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class AgentConfig(BaseModel):
    id: str = Field(..., description="智能体唯一标识符，需与 turn_order 中的字符串匹配")
    name: str = Field(..., description="角色展示名称")
    role: str = Field(..., description="角色在游戏中的身份标签")
    system_prompt: str = Field(..., description="角色核心人设、已知秘密与行为指引")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="生成随机度")


class GameConfig(BaseModel):
    name: str = Field(..., description="游戏/剧本名称")
    description: str = Field(..., description="游戏背景简介")
    max_rounds: int = Field(default=5, ge=1, description="最大对局轮数")
    turn_order: List[str] = Field(
        ...,
        description="按顺序发言的 ID 列表。保留关键字 'player' 代表终端用户"
    )
    agents: List[AgentConfig] = Field(..., description="所有参与的 AI 角色配置")

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
