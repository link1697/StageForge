from typing import List, Dict, Optional
from src.config.schema import Message


class MemoryBuffer:
    """全局共享对话历史与上下文窗口管理器"""

    def __init__(self):
        self._messages: List[Message] = []

    def append(self, msg: Message) -> None:
        """追加一条消息事件"""
        self._messages.append(msg)

    @property
    def messages(self) -> List[Message]:
        """返回所有消息历史副本"""
        return list(self._messages)

    def __len__(self) -> int:
        return len(self._messages)

    def get_context_for_agent(
        self,
        agent_id: str,
        system_prompt: Optional[str] = None,
        window_size: int = 10,
    ) -> List[Dict[str, str]]:
        """为特定 Agent 组装符合 OpenAI 规范的上下文消息列表

        规则：
        1. 第一条为 system 消息（若传入了 system_prompt）。
        2. 滑动窗口截取最近 window_size 条公开发言。
        3. Agent 自身的历史发言映射为 assistant，其余角色或玩家发言映射为带名字前缀的 user 消息。
        """
        context: List[Dict[str, str]] = []

        if system_prompt:
            context.append({"role": "system", "content": system_prompt})

        # 滑动窗口截取最近的发言
        recent_messages = (
            self._messages[-window_size:] if window_size > 0 else self._messages
        )

        for msg in recent_messages:
            if msg.sender_id == agent_id:
                context.append({
                    "role": "assistant",
                    "content": msg.content,
                })
            else:
                context.append({
                    "role": "user",
                    "content": f"[{msg.sender_name}]: {msg.content}",
                })

        return context

    def clear(self) -> None:
        """清空对话历史"""
        self._messages.clear()
