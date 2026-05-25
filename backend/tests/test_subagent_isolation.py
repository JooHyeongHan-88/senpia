"""서브 에이전트 중첩 위임 차단 회귀 테스트.

다음 세 가지 방어선을 독립적으로 검증한다:

  L1 — _filter_specs_for_sub_agent 가 SUB_AGENT_DISPATCH 를 제거하는가
  L2 — MAX_AGENT_DEPTH=1 일 때 depth=2 진입 시 depth-guard 가 거부하는가
  L3 — LLM 이 sub-agent context 에서 call_sub_agent 를 hallucinate 하면
       sentinel guard 가 [error] 를 반환하는가
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock


# backend 를 sys.path 에 추가 (pytest 가 backend/ 루트를 모를 때 대비)
sys.path.insert(0, str(Path(__file__).parent.parent))

import agent.tools  # noqa: F401 — 데코레이터 자기 등록 트리거

from agent.config import MAX_AGENT_DEPTH
from agent.harness import _execute_tool, _filter_specs_for_sub_agent
from agent.models import ToolCall, ToolSpec
from agent.registries.agents import Agent, AgentMeta
from agent.registries.tools import (
    SUB_AGENT_DISPATCH,
    ToolRegistry,
    _reset_registry_for_tests,
)


# ---------------------------------------------------------------------------
# L1 — _filter_specs_for_sub_agent 도구 필터링
# ---------------------------------------------------------------------------


class TestFilterSpecsForSubAgent:
    """L1: _filter_specs_for_sub_agent 가 SUB_AGENT_DISPATCH 를 항상 제거하는지."""

    def setup_method(self):
        _reset_registry_for_tests()

    def teardown_method(self):
        _reset_registry_for_tests()

    def test_removes_sub_agent_dispatch(self):
        """SUB_AGENT_DISPATCH 는 서브 에이전트에게 절대 노출되지 않아야 한다."""
        # 일반 도구와 sentinel 도구를 혼합해 스펙 목록 생성
        specs = [
            ToolSpec(name="some_tool", description="일반 도구", parameters={}),
            ToolSpec(
                name=SUB_AGENT_DISPATCH,
                description="서브 에이전트 디스패치",
                parameters={},
            ),
            ToolSpec(name="another_tool", description="또 다른 도구", parameters={}),
        ]
        agent = Agent(
            meta=AgentMeta(name="test_agent", description="테스트 에이전트", tools=[]),
            source_path="",
        )

        result = _filter_specs_for_sub_agent(specs, agent)
        result_names = {s.name for s in result}

        assert SUB_AGENT_DISPATCH not in result_names
        assert "some_tool" in result_names
        assert "another_tool" in result_names

    def test_whitelist_respected_and_dispatch_still_excluded(self):
        """도구 화이트리스트가 있을 때도 SUB_AGENT_DISPATCH 는 제외된다."""
        specs = [
            ToolSpec(name="allowed_tool", description="허용", parameters={}),
            ToolSpec(name=SUB_AGENT_DISPATCH, description="디스패치", parameters={}),
            ToolSpec(name="blocked_tool", description="화이트리스트 외", parameters={}),
        ]
        agent = Agent(
            meta=AgentMeta(
                name="strict_agent",
                description="화이트리스트 에이전트",
                tools=["allowed_tool", SUB_AGENT_DISPATCH],  # 명시 포함 시도
            ),
            source_path="",
        )

        result = _filter_specs_for_sub_agent(specs, agent)
        result_names = {s.name for s in result}

        # forbidden 이 whitelist 보다 우선: SUB_AGENT_DISPATCH 는 여전히 제외
        assert SUB_AGENT_DISPATCH not in result_names
        assert "allowed_tool" in result_names
        assert "blocked_tool" not in result_names


# ---------------------------------------------------------------------------
# L2 — MAX_AGENT_DEPTH depth-guard
# ---------------------------------------------------------------------------


class TestDepthGuard:
    """L2: _dispatch_sub_agent 가 depth > MAX_AGENT_DEPTH 시 즉시 거부하는가."""

    def test_max_agent_depth_is_1(self):
        """권장 상한값이 유지되는지 확인."""
        assert MAX_AGENT_DEPTH == 1, (
            f"MAX_AGENT_DEPTH 가 {MAX_AGENT_DEPTH} 으로 변경됨. "
            "중첩 sub-agent 를 허용할 의도가 아니라면 1 로 되돌리세요."
        )

    def test_depth_guard_blocks_nested_dispatch(self):
        """depth=2 진입 시 AgentReturnEvent 에 '[depth-guard]' 가 포함돼야 한다."""
        from agent.harness import _dispatch_sub_agent
        from agent.models import AgentReturnEvent
        from agent.registries.agents import AgentRegistry, AgentMeta, Agent

        # 최소한의 mock 준비
        registry = MagicMock()
        agent_registry = MagicMock(spec=AgentRegistry)
        agent_registry.get_by_name.return_value = Agent(
            meta=AgentMeta(name="nested_agent", description="중첩 에이전트"),
            source_path="",
        )

        call = ToolCall(
            id="tc-001",
            name=SUB_AGENT_DISPATCH,
            arguments={"agent_name": "nested_agent", "task": "nested task"},
        )
        budget = MagicMock()
        budget.check_dispatch.return_value = None

        # depth=2 로 직접 진입 (MAX_AGENT_DEPTH=1 초과)
        events = asyncio.run(
            _collect_async(
                _dispatch_sub_agent(
                    call=call,
                    parent_agent_id="sub_agent",
                    agent_registry=agent_registry,
                    skill_registry=MagicMock(),
                    prompt_registry=MagicMock(),
                    registry=registry,
                    provider=MagicMock(),
                    budget=budget,
                    depth=2,
                    max_iterations=5,
                )
            )
        )

        return_events = [e for e in events if isinstance(e, AgentReturnEvent)]
        assert len(return_events) == 1
        assert "[depth-guard]" in return_events[0].summary


# ---------------------------------------------------------------------------
# L3 — sentinel guard in _execute_tool
# ---------------------------------------------------------------------------


class TestSentinelGuard:
    """L3: _execute_tool 이 sentinel 도구를 명시적 오류로 거부하는가."""

    def setup_method(self):
        # L1 테스트가 전역 registry 를 초기화할 수 있으므로 sentinel 도구를 재등록한다.
        # 각 submodule 을 reload 해야 @register_tool 데코레이터가 다시 실행된다.
        import importlib

        import agent.tools.builtin
        import agent.tools.clarify
        import agent.tools.dispatch
        import agent.tools.planner

        for mod in (
            agent.tools.builtin,
            agent.tools.planner,
            agent.tools.dispatch,
            agent.tools.clarify,
        ):
            importlib.reload(mod)

    def test_execute_tool_rejects_sub_agent_dispatch_sentinel(self):
        """call_sub_agent 가 _execute_tool 까지 흘러오면 [error] sentinel ... 반환."""
        registry = ToolRegistry()
        call = ToolCall(
            id="tc-002",
            name=SUB_AGENT_DISPATCH,
            arguments={"agent_name": "some_agent", "task": "some task"},
        )

        result = asyncio.run(_execute_tool(call, registry))

        assert result.is_error is True
        assert "sentinel" in result.content


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------


async def _collect_async(agen):
    """AsyncIterator 를 리스트로 수집."""
    return [item async for item in agen]
