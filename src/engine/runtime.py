import sys
from typing import Optional
from src.config.schema import GameConfig, Message, AgentConfig
from src.engine.scheduler import TurnScheduler
from src.memory.buffer import MemoryBuffer
from src.llm.client import LLMClient


class GameRuntime:
    """游戏运行时主控引擎：驱动状态机、输入处理与 LLM 交互"""

    def __init__(
        self,
        config: GameConfig,
        llm_client: Optional[LLMClient] = None,
        scheduler: Optional[TurnScheduler] = None,
        memory: Optional[MemoryBuffer] = None,
        window_size: int = 10,
    ):
        self.config = config
        self.llm_client = llm_client or LLMClient()
        self.scheduler = scheduler or TurnScheduler(
            turn_order=config.turn_order,
            max_rounds=config.max_rounds,
        )
        self.memory = memory or MemoryBuffer()
        self.window_size = window_size

    def _print_prologue(self) -> None:
        """打印开场介绍与角色信息"""
        print("\n" + "=" * 60)
        print(f" 🎮 剧本名称: {self.config.name}")
        print("=" * 60)
        print(f"【剧情简介】: {self.config.description}\n")
        print(f"【对局设置】: 共 {self.config.max_rounds} 轮，发言顺序: {' -> '.join(self.config.turn_order)}")
        print("【出场角色】:")
        for agent in self.config.agents:
            print(f"  • {agent.name} (ID: {agent.id})")
        print("=" * 60 + "\n")

    def _print_epilogue(self) -> None:
        """打印游戏结束总结"""
        print("\n" + "=" * 60)
        print(" 🏁 对局已达到最大轮次，审讯结束！")
        print("=" * 60)

    def run(self) -> None:
        """运行游戏主循环"""
        self._print_prologue()
        last_round = 0

        while not self.scheduler.is_terminated():
            round_num = self.scheduler.current_round
            current_id = self.scheduler.get_current_speaker()

            if round_num != last_round:
                print(f"\n─────────── [ 第 {round_num} / {self.config.max_rounds} 轮 ] ───────────")
                last_round = round_num

            if current_id == "player":
                self._handle_player_turn(round_num)
            else:
                agent = self.config.get_agent(current_id)
                if not agent:
                    raise RuntimeError(f"未找到发言角色配置: {current_id}")
                self._handle_agent_turn(agent, round_num)

            self.scheduler.advance()

        self._print_epilogue()

    def _handle_player_turn(self, round_num: int) -> None:
        """处理玩家输入"""
        while True:
            try:
                user_text = input(f"\n[你 (侦探)] > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\n[游戏被用户中断，退出运行时]")
                sys.exit(0)

            if user_text:
                break
            print("（发言内容不能为空，请输入你的问话）")

        self.memory.append(
            Message(
                sender_id="player",
                sender_name="侦探(你)",
                content=user_text,
                role="user",
                round_idx=round_num,
            )
        )

    def _handle_agent_turn(self, agent: AgentConfig, round_num: int) -> None:
        """处理 AI 智能体发言"""
        print(f"\n[{agent.name} 正在思考...]")

        context = self.memory.get_context_for_agent(
            agent_id=agent.id,
            system_prompt=agent.system_prompt,
            window_size=self.window_size,
        )

        reply = self.llm_client.generate_response(
            messages=context,
            temperature=agent.temperature,
        )

        print(f"[{agent.name}]: {reply}")

        self.memory.append(
            Message(
                sender_id=agent.id,
                sender_name=agent.name,
                content=reply,
                role="assistant",
                round_idx=round_num,
            )
        )
