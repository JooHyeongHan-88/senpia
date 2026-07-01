"""summarize-then-drop 롤링 히스토리 압축 (R10).

LLM 컨텍스트가 ``MAX_HISTORY_MESSAGES`` 슬라이딩 윈도우를 넘겨 앞에서 버려질 때, 잘린
턴을 기존 요약에 접어 ``state.progress_summary`` 로 보존한다(망각 방지). happy path 전용
— 예외 경로(``state/persistence.py``)엔 LLM 콜을 추가하지 않는다.

구 ``harness/loop.py`` 에서 분리 — 압축은 provider 호출 + 히스토리 요약이라 프롬프트
조립(``prompt/``)도 상태 변형(``state/``)도 아닌 독립 관심사다.
"""

import logging

from agent.models import Message
from agent.providers.factory import LLMProvider

logger = logging.getLogger(__name__)

_COMPACTION_SYSTEM_PROMPT: str = (
    "당신은 대화 압축기다. 아래 '기존 요약'에 '새로 잘린 대화'를 통합해 갱신된 진행 "
    "요약 하나를 만들어라. 원래 목표·내려진 결정·제약 조건·핵심 수치 결과·산출물 "
    "경로(result/...)를 반드시 보존하라. 한국어 200단어 이내로 간결하게, 요약 본문만 출력하라."
)
_COMPACTION_MAX_CHARS: int = 2000


async def _compact_history(
    provider: LLMProvider, prior_summary: str | None, dropped: list[Message]
) -> str | None:
    """슬라이딩 윈도우가 버린 메시지를 기존 요약에 접어 갱신 요약을 만든다 (summarize-then-drop).

    best-effort: 요약 콜이 어떤 이유로든 실패하면 ``prior_summary`` 를 그대로 돌려준다
    (graceful degrade — content_sync 와 동일 철학). 턴은 막지 않는다.

    Args:
        provider: 현재 세션 LLM provider (요약도 같은 모델로).
        prior_summary: 직전까지 누적된 롤링 요약. 없으면 None.
        dropped: 이번 트림에서 버려진 메시지(시간순, tool 은 절단본).

    Returns:
        갱신된 요약 문자열. 잘린 내용이 비었거나 실패 시 ``prior_summary``.
    """
    rendered = "\n".join(
        f"[{m.role}] {m.content}".strip() for m in dropped if m.content
    )
    if not rendered:
        return prior_summary

    payload = (
        f"## 기존 요약\n{prior_summary or '(없음)'}\n\n## 새로 잘린 대화\n{rendered}"
    )
    messages = [
        Message(role="system", content=_COMPACTION_SYSTEM_PROMPT),
        Message(role="user", content=payload),
    ]
    try:
        buffer: list[str] = []
        async for event in provider.astream(messages, []):
            if event.type == "delta":
                buffer.append(event.content)
            elif event.type == "done":
                break
        summary = "".join(buffer).strip()
        return summary[:_COMPACTION_MAX_CHARS] if summary else prior_summary
    except Exception:  # noqa: BLE001 — best-effort, 실패해도 직전 요약 유지
        logger.warning("history compaction failed — keeping prior summary")
        return prior_summary
