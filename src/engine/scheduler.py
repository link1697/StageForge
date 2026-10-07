from typing import List, Optional


class TurnScheduler:
    """轮次调度器：管理 Round 步进与发言游标状态机"""

    def __init__(
        self,
        turn_order: List[str],
        max_rounds: int = 5,
        current_round: int = 1,
        cursor: int = 0,
    ):
        if not turn_order:
            raise ValueError("turn_order 不能为空")
        if max_rounds < 1:
            raise ValueError("max_rounds 必须大于或等于 1")

        self.turn_order = list(turn_order)
        self.max_rounds = max_rounds
        self.current_round = current_round
        self.cursor = cursor

    def is_terminated(self) -> bool:
        """当当前轮数超出最大轮数时判定为结束"""
        return self.current_round > self.max_rounds

    def get_current_speaker(self) -> Optional[str]:
        """获取当前发言者 ID；若已终止则返回 None"""
        if self.is_terminated():
            return None
        return self.turn_order[self.cursor]

    def advance(self) -> None:
        """推进发言游标；一轮所有角色发言完毕后进入下一大轮"""
        if self.is_terminated():
            return

        self.cursor += 1
        if self.cursor >= len(self.turn_order):
            self.cursor = 0
            self.current_round += 1

    def __repr__(self) -> str:
        return (
            f"TurnScheduler(round={self.current_round}/{self.max_rounds}, "
            f"cursor={self.cursor}/{len(self.turn_order)}, "
            f"speaker={self.get_current_speaker()})"
        )
