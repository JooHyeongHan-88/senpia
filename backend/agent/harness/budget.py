"""TurnBudget — 한 사용자 턴 단위 provider 호출 상한 + 연속 호출 가드.

오케스트레이터 + 모든 (재귀) 서브 에이전트 호출을 합산해 한 사용자 turn 의 provider
호출 총량을 제한한다. ``loop`` 와 양 디스패처(``dispatch.sequential``·
``dispatch.parallel``)가 공유한다.
"""

from dataclasses import dataclass
from typing import ClassVar


@dataclass
class TurnBudget:
    """한 사용자 turn 에서 허용하는 provider 호출 총량.

    오케스트레이터 + 모든 (재귀) 서브 에이전트 호출 합산. 상한 도달 시 ErrorEvent
    로 안전 종료. 같은 서브 에이전트 연속 호출 가드도 함께 관리한다.
    """

    max_calls: int
    used: int = 0
    last_dispatched_agent: str | None = None
    consecutive_count: int = 0

    MAX_CONSECUTIVE_SAME_AGENT: ClassVar[int] = 3

    def try_consume(self) -> bool:
        """provider 호출 1회 소비. False 면 상한 도달."""
        if self.used >= self.max_calls:
            return False
        self.used += 1
        return True

    def check_dispatch(self, agent_name: str) -> str | None:
        """같은 에이전트 연속 호출 가드. 차단 시 사유 문자열, 통과 시 None."""
        if agent_name == self.last_dispatched_agent:
            self.consecutive_count += 1
            if self.consecutive_count > self.MAX_CONSECUTIVE_SAME_AGENT:
                return (
                    f"[loop-guard] '{agent_name}' 가 "
                    f"{self.MAX_CONSECUTIVE_SAME_AGENT}회 연속 호출되어 차단됨"
                )
        else:
            self.last_dispatched_agent = agent_name
            self.consecutive_count = 1
        return None
