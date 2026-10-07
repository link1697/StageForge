import sys
from typing import Optional, List
from src.config.schema import GameConfig, Message, AgentConfig
from src.engine.scheduler import TurnScheduler
from src.memory.buffer import MemoryBuffer
from src.llm.client import LLMClient


class GameRuntime:
    """游戏运行时主控引擎：驱动状态机、输入处理、投票裁决与 LLM 交互"""

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
        self.accused = False
        self.result: Optional[str] = None  # "victory" 或 "defeat"

    def _print_prologue(self) -> None:
        """打印开场介绍与角色信息"""
        print("\n" + "=" * 60)
        print(f" 🎮 剧本名称: {self.config.name}")
        print("=" * 60)
        print(f"【剧情简介】: {self.config.description}\n")
        print(
            f"【对局规则】: 最多进行 {self.config.max_rounds} 轮。\n"
            f"  • 从第 {self.config.min_accuse_round} 轮起，可在你的回合输入「/vote」随时指认真凶结案；\n"
            f"  • 若到达第 {self.config.max_rounds} 轮结束，则必须强制指认最终凶手！"
        )
        print(f"【发言顺序】: {' -> '.join(self.config.turn_order)}")
        print("【出场角色】:")
        for agent in self.config.agents:
            print(f"  • {agent.name} (ID: {agent.id})")
        print("=" * 60 + "\n")

    def _print_epilogue(self) -> None:
        """打印游戏结束总结"""
        print("\n" + "=" * 60)
        print(" 🏁 游戏运行结束")
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

        # 如果对局达到最大轮次结束，且之前未进行过指认，强制进入最终指控环节
        if not self.accused:
            print(f"\n⚠️  第 {self.config.max_rounds} 轮审讯已全部结束！审讯期终止，你必须立即做出最终裁决！")
            self._handle_accusation(mandatory=True)

        self._print_epilogue()

    def _handle_player_turn(self, round_num: int) -> None:
        """处理玩家输入"""
        can_accuse = round_num >= self.config.min_accuse_round

        while True:
            if can_accuse:
                print(f"\n💡 [提示] 当前已进入指证期！输入问话继续审讯，或输入「/vote」指认真凶做出裁决。")

            try:
                user_text = input(f"[你 (侦探)] > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\n[游戏被用户中断，退出运行时]")
                sys.exit(0)

            if not user_text:
                print("（发言内容不能为空，请输入你的问话）")
                continue

            # 检查是否触发指认凶手指令
            if can_accuse and user_text.lower() in ("/vote", "/accuse", "指认", "投票", "结案"):
                accused = self._handle_accusation(mandatory=False)
                if accused:
                    # 已做出指认，直接结束当前回合（调度器已终止）
                    return
                # 取消了指认，继续回到输入循环
                continue

            break

        self.memory.append(
            Message(
                sender_id="player",
                sender_name="侦探(你)",
                content=user_text,
                role="user",
                round_idx=round_num,
            )
        )

    def _handle_accusation(self, mandatory: bool = False) -> bool:
        """指认凶手裁决流程。返回 True 表示完成指认，False 表示取消"""
        print("\n" + "=" * 60)
        print(" ⚖️  【指认真凶 · 最终裁决】")
        print("=" * 60)
        print("请指认杀害老伯爵的真正凶手：")
        for idx, agent in enumerate(self.config.agents, 1):
            print(f"  [{idx}] {agent.name} (ID: {agent.id})")

        chosen_agent: Optional[AgentConfig] = None
        while True:
            try:
                prompt_text = (
                    "\n请输入你认定的凶手序号或名称: "
                    if mandatory
                    else "\n请输入凶手序号或名称（输入 0 取消指认继续审问）: "
                )
                choice = input(prompt_text).strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\n[游戏被用户中断]")
                sys.exit(0)

            if not mandatory and choice in ("0", "cancel", "q", "取消", "返回"):
                print("已取消指认，继续进行审问。\n")
                return False

            # 按数字序号匹配
            if choice.isdigit():
                num = int(choice)
                if 1 <= num <= len(self.config.agents):
                    chosen_agent = self.config.agents[num - 1]
                    break

            # 按名称或 ID 匹配
            for agent in self.config.agents:
                if choice.lower() in (agent.name.lower(), agent.id.lower()):
                    chosen_agent = agent
                    break

            if chosen_agent:
                break

            print("（输入无效，请输入列表中对应的序号或角色名字）")

        self.accused = True
        self.scheduler.terminate()

        # 校验凶手
        is_correct = bool(self.config.culprit_id and chosen_agent.id == self.config.culprit_id)

        print("\n" + "=" * 60)
        if is_correct:
            self.result = "victory"
            print(" 🎉 指控正确！真相大白，侦探大获全胜！(VICTORY)")
            print("=" * 60)
            print(f"你成功指认了真凶：【{chosen_agent.name}】！\n")
        else:
            self.result = "defeat"
            real_culprit = self.config.get_agent(self.config.culprit_id) if self.config.culprit_id else None
            real_name = real_culprit.name if real_culprit else "未知"
            print(" ❌ 冤假错案！指控错误，游戏失败！(DEFEAT)")
            print("=" * 60)
            print(f"你指认了【{chosen_agent.name}】，但真凶其实是【{real_name}】！\n")

        if self.config.truth_revealed:
            print("【案情真相】:")
            print(f"  {self.config.truth_revealed.strip()}")
        print("=" * 60)

        return True

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
