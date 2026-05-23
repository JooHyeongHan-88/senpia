"""Agent harness 가 호출할 도구(Tool) 정의 및 레지스트리.

도구는 Protocol 로 추상화되어 있어 새 도구를 등록할 때는 Tool 구현체를 만들고
모듈 하단의 registry.register(...) 한 줄만 추가하면 된다.
"""

from datetime import datetime
from typing import Any, Protocol

from chat.models import ToolSpec


class Tool(Protocol):
    name: str
    description: str
    parameters: dict[str, Any]

    async def run(self, args: dict[str, Any]) -> str:
        """도구를 실행하고 문자열 결과를 반환한다.

        결과는 그대로 tool 메시지의 content 로 LLM 에게 전달되므로
        직렬화된 문자열(JSON 등)이어야 한다.
        """
        ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        """provider 에게 노출할 도구 스펙 목록."""
        return [
            ToolSpec(
                name=t.name,
                description=t.description,
                parameters=t.parameters,
            )
            for t in self._tools.values()
        ]


class NowTool:
    """현재 시각을 ISO 8601 문자열로 반환하는 데모 도구."""

    name = "now"
    description = "현재 시각(로컬 타임존)을 ISO 8601 문자열로 반환한다."
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    async def run(self, args: dict[str, Any]) -> str:
        return datetime.now().isoformat(timespec="seconds")


registry = ToolRegistry()
registry.register(NowTool())
