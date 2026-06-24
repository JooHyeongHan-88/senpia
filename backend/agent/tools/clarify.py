"""Clarify sentinel — LLM 이 능동적으로 사용자에게 보완 질문을 던질 때 사용.

harness 의 tool_call 분기에서 가로채 AskUserEvent 로 변환한다. fn body 는 실행되지
않으며, spec 만 LLM 에 노출된다.

사용 시점 가이드 (orchestrator.md Case 0 참고):
    - 요청 대상이 다의적이다 ("데이터 보여줘", "그거 처리해줘")
    - 핵심 파라미터를 선택지로 분해 가능 (기간 / 부서 / 카테고리)
    - 두 가지 행동을 모두 의도할 수 있어 어느 쪽인지 단정 불가

복수 선택이 자연스러운 질문(여러 항목을 동시에 고르는 게 타당)이면 multi_select=True 로 호출한다.

도구 인자 검증 실패는 슬롯 가드가 자동 처리하므로 그 경우엔 호출하지 말 것.
"""

from typing import Annotated

from agent.registries.tools import ASK_USER, register_tool


@register_tool(
    name=ASK_USER,
    description=(
        "사용자의 요청이 모호하거나 핵심 정보가 빠져 있을 때 호출한다. "
        "When to use: 대상·범위·기간 등 핵심 인자가 다의적이라 추정으로 진행하기 어려울 때, "
        "또는 두 가지 행동을 모두 의도할 수 있어 한쪽으로 단정 불가능할 때. "
        "When NOT to use: 도구 인자 형식 오류(슬롯 가드가 자동 처리), "
        "합리적 추정이 가능한 경우(추정 후 진행 + 결과 보고에서 가정 명시), "
        "또는 같은 질문을 직전 턴에 이미 던졌을 때(반복 금지 — 가장 합리적 해석으로 진행). "
        "input_type='choice' 이면 사용자는 options 중에서만 고를 수 있고, "
        "'text' 이면 자유 입력만 받으며, 'both' 이면 옵션도 보여주고 자유 입력도 허용한다. "
        "options 가 비어 있으면 input_type 은 자동으로 'text' 로 강제된다. "
        "multi_select=True 이면 사용자가 options 중 여러 개를 동시에 고른 뒤 한 번에 제출할 수 있다 "
        "— 복수 선택이 자연스러운 질문에만 사용한다 (예: '포함할 차트를 모두 고르세요', "
        "'관심 있는 부서를 전부 선택'). 하나만 골라야 하면 False(기본). "
        "options 가 없으면(자유 입력 전용) multi_select 는 무시된다."
    ),
    sentinel=True,
)
async def ask_user(
    question: Annotated[str, "사용자에게 던질 자연어 질문 (한 문장, 한국어)"],
    options: Annotated[
        list[str] | None,
        "선택지 후보 (3~5개 권장). input_type='text' 이거나 자유 입력만 받을 땐 null.",
    ] = None,
    input_type: Annotated[
        str,
        "choice | text | both (기본 both). options 가 없으면 'text' 로 강제됨.",
    ] = "both",
    multi_select: Annotated[
        bool,
        "True 면 options 중 여러 개를 동시에 선택 후 제출 가능. 복수 선택이 타당할 때만 True. "
        "options 가 없으면 무시됨. 기본 False(단일 선택).",
    ] = False,
) -> str:
    raise RuntimeError("sentinel tool — handled by harness, never executed")
