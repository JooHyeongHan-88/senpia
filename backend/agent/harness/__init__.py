"""Agent harness 서브시스템 — provider ↔ 도구 turn 실행 루프.

run_turn 한 번 = 사용자 입력 1건에 대한 응답 1턴. 계층형 멀티 에이전트
(오케스트레이터 + 서브 에이전트) 실행을 담당한다.

구성 (책임별 모듈·서브패키지 — harness 는 복잡도상 의도적으로 ``agent/`` 의 최초
중첩 서브패키지다):
    - loop: run_turn 진입점 + _run_agent_turn 공통 provider→tool 루프.
    - lifecycle: 예산 임박 wind-down 주입(R7) + 반복 상한 fallback(F6).
    - compaction: summarize-then-drop 롤링 히스토리 요약(R10).
    - budget: TurnBudget — 한 턴 provider 호출 상한 + 연속 호출 가드.
    - tool_exec: 도구 실행(timeout/표준화) + tool 응답 메시지 누적.
    - dispatch/: 서브 에이전트 위임 + 도구 스펙 선별 (sequential·parallel·spec_filter·result_format).
    - state/: AgentState 변형(todo)·히스토리 정합성(balancing)·루프 가드(loop_guard)·실패 턴 영속(persistence).
    - prompt/: system prompt 동적 조립 (compose·sections·artifacts·api_refs·wind_down).

공개 API 는 backend/api/chat.py 가 ``from agent.harness import run_turn`` 으로 사용한다.
내부 헬퍼도 기존 테스트의 ``from agent.harness import _x`` 호출을 보존하기 위해 이
패키지 네임스페이스에서 그대로 접근 가능하게 각 거처에서 끌어와 노출한다.
"""

from agent.harness.budget import TurnBudget  # noqa: F401  (re-export — 하위호환)
from agent.harness.dispatch.parallel import (  # noqa: F401
    _dispatch_parallel_sub_agents,
)
from agent.harness.dispatch.result_format import (  # noqa: F401
    _format_sub_agent_result,
)
from agent.harness.dispatch.sequential import _dispatch_sub_agent  # noqa: F401
from agent.harness.compaction import (  # noqa: F401
    _COMPACTION_SYSTEM_PROMPT,
    _compact_history,
)
from agent.harness.dispatch.spec_filter import (  # noqa: F401
    _build_orchestrator_specs,
    _filter_specs_for_sub_agent,
    _inject_runtime_tools,
)
from agent.harness.lifecycle import (  # noqa: F401
    _emit_max_iterations_fallback,
    _maybe_inject_wind_down,
)
from agent.harness.loop import (  # noqa: F401
    ORCHESTRATOR_ID,
    _run_agent_turn,
    run_turn,
)
from agent.harness.prompt.api_refs import (  # noqa: F401
    _collect_agent_api_refs_section,
    _render_skills_api_refs,
)
from agent.harness.prompt.artifacts import (  # noqa: F401
    _render_session_artifacts_section,
)
from agent.harness.prompt.compose import (  # noqa: F401
    _compose_orchestrator_system_prompt,
    _compose_sub_agent_system_prompt,
    _compose_system_prompt,
)
from agent.harness.prompt.wind_down import _build_wind_down_message  # noqa: F401
from agent.harness.state.balancing import (  # noqa: F401
    _ERROR_TOOL_PLACEHOLDER,
    _balance_all_unresolved,
    _balance_unresolved_tool_calls,
)
from agent.harness.state.loop_guard import (  # noqa: F401
    _call_signature,
    _record_invalid_call,
)
from agent.harness.state.persistence import _persist_failed_turn  # noqa: F401
from agent.harness.tool_exec import _execute_tool  # noqa: F401

__all__ = ["run_turn", "TurnBudget", "ORCHESTRATOR_ID"]
