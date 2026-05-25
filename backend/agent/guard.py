"""슬롯 필링 가드 — Pydantic 시그니처 기반 도구 인자 검증.

LLM 이 환각/오해로 만들어낸 호출이 도구 함수에 닿기 전에 가로채고, 사용자에게
되묻기 위한 missing 슬롯 목록을 돌려준다. 단순한 `required` 키 존재 여부뿐 아니라
타입·형식·enum 위반도 동일한 흐름(AskUserEvent)으로 처리해 LLM 의 자유 형식
응답으로 인한 ValueError 폭주를 방지한다.

Pydantic ValidationError → MissingSlot 변환 규칙:
    - type=="missing"          → "<설명> 값을 알려 주세요." (또는 slot_prompts override)
    - type=="literal_error"    → "다음 중 하나를 선택해 주세요: <enum>"
    - type.startswith("date")  → "날짜를 YYYY-MM-DD 형식으로 알려 주세요"
    - 그 외                    → "<key> 값이 올바르지 않습니다. 다시 알려 주세요"

slot_prompts 에 키별 override 가 있으면 위 자동 메시지 대신 그것을 우선 사용한다.
"""

from typing import Annotated, Any

from pydantic import BaseModel, Field, ValidationError

from agent.registries.tools import RegisteredTool


class MissingSlot(BaseModel):
    key: Annotated[str, "도구 파라미터 키"]
    question: Annotated[str, "사용자에게 보일 자연어 질문"]
    options: Annotated[list[str] | None, "JSON Schema enum 이 있을 때 UI 보기"] = None


class SlotCheckResult(BaseModel):
    ok: bool
    missing: list[MissingSlot] = Field(default_factory=list)


def validate_tool_args(
    call_arguments: dict[str, Any], tool: RegisteredTool | None
) -> SlotCheckResult:
    """도구의 Pydantic 입력 모델로 인자를 검증한다.

    Args:
        call_arguments: LLM 이 보낸 raw arguments dict.
        tool: ToolRegistry 에서 조회한 RegisteredTool. None 이면 가드 통과
            (실행 단계에서 "unknown tool" 응답으로 흐름).

    Returns:
        SlotCheckResult — ok=True 면 호출 진행, False 면 missing[0] 으로 AskUser.
    """
    if tool is None:
        return SlotCheckResult(ok=True)

    try:
        tool.input_adapter.validate_python(call_arguments or {})
    except ValidationError as exc:
        missing = _errors_to_missing_slots(exc, tool)
        if missing:
            return SlotCheckResult(ok=False, missing=missing)
        # 알 수 없는 에러여도 통과시키면 fn 에서 다시 터질 것 — 안전을 위해 통과 시킴.
        return SlotCheckResult(ok=True)

    return SlotCheckResult(ok=True)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _errors_to_missing_slots(
    exc: ValidationError, tool: RegisteredTool
) -> list[MissingSlot]:
    """Pydantic ValidationError 각 항목을 MissingSlot 으로 변환한다.

    동일 키에 여러 에러가 있으면 첫 번째만 채택해 UI 가 같은 질문을 두 번 묻지
    않도록 한다.
    """
    seen: set[str] = set()
    out: list[MissingSlot] = []

    for err in exc.errors():
        loc = err.get("loc") or ()
        if not loc:
            continue
        key = str(loc[0])
        if key in seen:
            continue
        seen.add(key)

        question = _question_for(key, err, tool)
        options = _enum_options(key, tool)
        out.append(MissingSlot(key=key, question=question, options=options))

    return out


def _question_for(key: str, err: dict[str, Any], tool: RegisteredTool) -> str:
    """slot_prompts override 우선, 없으면 에러 type 별 친근한 한국어 메시지 생성."""
    override = tool.slot_prompts.get(key)
    if override:
        return override

    err_type = err.get("type", "")
    prop = tool.properties.get(key, {})
    label = prop.get("description") or key

    if err_type == "missing":
        return f"'{label}' 값을 알려 주세요."
    if err_type == "literal_error":
        ctx = err.get("ctx") or {}
        expected = ctx.get("expected")
        if expected:
            return f"'{label}' 은 다음 중 하나여야 합니다: {expected}"
        return f"'{label}' 값이 허용 범위를 벗어났습니다. 다시 알려 주세요."
    if err_type.startswith("date") or err_type.startswith("datetime"):
        return f"'{label}' 을 YYYY-MM-DD 형식으로 알려 주세요."
    if err_type.startswith("int") or err_type.startswith("float"):
        return f"'{label}' 을 숫자로 알려 주세요."
    if err_type.startswith("bool"):
        return f"'{label}' 을 예/아니오로 알려 주세요."

    return f"'{label}' 값이 올바르지 않습니다. 다시 알려 주세요."


def _enum_options(key: str, tool: RegisteredTool) -> list[str] | None:
    """JSON Schema 의 enum 정의에서 UI 버튼 후보를 추출 (Literal 타입 등).

    Pydantic 이 Literal 을 enum 으로 변환하는 경로와, 직접 enum 을 둔 경로 둘 다 커버.
    """
    prop = tool.properties.get(key, {})
    enum = prop.get("enum")
    if isinstance(enum, list) and enum:
        return [str(v) for v in enum]
    return None
