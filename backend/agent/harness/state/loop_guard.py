"""루프 가드 — 동일 호출 반복을 감지하기 위한 호출 시그니처 계산 (R4).

인자뿐 아니라 인자가 참조하는 ``result/...`` 파일의 fingerprint 까지 시그니처에
포함해, "spec 파일을 고쳐 쓴 뒤 같은 경로로 재호출"(정당한 재시도)을 루프로 오인하지
않게 한다. 구 ``harness/state.py`` 의 루프 가드 섹션 + ``harness/core.py`` 의 루프
차단 메시지를 한곳에 모았다.
"""

import json
from typing import Any

from agent.models import ToolCall
from core.result_store import resolve_result_path

# 동일 시그니처(_call_signature: name+args+참조파일 fingerprint) 호출이 반복될 때
# LLM 에 회신하는 루프 차단 메시지.
# 정상 실행 경로(history_calls)와 형식오류 self-correct 경로 양쪽에서 재사용한다.
_LOOP_GUARD_MESSAGE = (
    "[System] 동일한 인자로 이 도구를 연속해서 호출했습니다. 루프가 감지되었습니다. "
    "이전 실행 결과를 바탕으로 원인을 분석(Root Cause Analysis)하고 완전히 다른 "
    "접근 방식을 시도하세요."
)


def _collect_result_path_fingerprints(value: Any, parts: list[str]) -> None:
    """인자 트리에서 'result/...' 경로 문자열을 찾아 파일 fingerprint 를 수집한다.

    Args:
        value: tool_call 인자 트리의 한 노드 (str/dict/list/스칼라).
        parts: 수집된 ``경로:mtime_ns:size`` 문자열이 append 되는 출력 버퍼.
    """
    if isinstance(value, str):
        if value.strip().replace("\\", "/").startswith("result/"):
            target, error = resolve_result_path(value)
            if error is None and target is not None:
                try:
                    stat = target.stat()
                except OSError:
                    return
                parts.append(f"{value}:{stat.st_mtime_ns}:{stat.st_size}")
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_result_path_fingerprints(item, parts)
        return
    if isinstance(value, list):
        for item in value:
            _collect_result_path_fingerprints(item, parts)


def _call_signature(call: ToolCall) -> tuple[str, str, str]:
    """루프 가드용 호출 시그니처 — (도구명, 인자 JSON, 참조 파일 fingerprint).

    인자만 비교하면 'spec 파일을 고쳐 쓴 뒤 같은 경로로 재호출'(정당한 재시도)을
    루프로 오인한다. 인자 속 'result/...' 경로가 가리키는 파일의 mtime/size 를
    시그니처에 포함해, 관측 가능한 상태가 그대로인 진짜 반복만 차단한다.
    미존재 경로·일반 문자열은 fingerprint 에 기여하지 않는다.
    """
    args_str = json.dumps(call.arguments, sort_keys=True) if call.arguments else ""
    parts: list[str] = []
    _collect_result_path_fingerprints(call.arguments or {}, parts)
    return (call.name, args_str, "|".join(sorted(parts)))


def _record_invalid_call(
    call: ToolCall, history_calls: set[tuple[str, str, str]]
) -> bool:
    """형식오류 호출 시그니처를 history_calls 에 기록한다.

    같은 시그니처의 형식오류 호출이 반복되면(=self-correct 실패) True 를 반환해
    호출자가 루프 차단 메시지로 전환하도록 한다. 정상 실행 경로의 dedup 과 동일한
    history_calls 집합을 공유하므로 형식오류↔정상 호출 간 루프도 함께 감지된다.

    Returns:
        True: 이미 본 동일 호출(반복). False: 최초 기록.
    """
    sig = _call_signature(call)
    if sig in history_calls:
        return True
    history_calls.add(sig)
    return False
