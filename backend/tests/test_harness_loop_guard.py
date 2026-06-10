"""루프 가드 시그니처(_call_signature) — 참조 파일 fingerprint 회귀 테스트.

같은 (도구, 인자) 호출이라도 인자가 가리키는 'result/...' 파일 내용이 바뀌면
정당한 재시도로 판정해야 한다 — spec 파일을 고쳐 쓴 뒤 같은 경로로
display_chart 를 재호출하는 시나리오가 루프로 오인 차단되던 회귀 케이스.
"""

from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.harness import _call_signature, _record_invalid_call  # noqa: E402
from agent.models import ToolCall  # noqa: E402
from core import result_store  # noqa: E402
from tests._runner import run_tests  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_result_dir():
    original = result_store.RESULT_DIR
    yield
    result_store.RESULT_DIR = original


def _make_artifact(content: str = "v1") -> str:
    """tmp RESULT_DIR 에 산출물 파일을 만들고 'result/...' 경로를 반환한다."""
    result_store.RESULT_DIR = Path(tempfile.mkdtemp(prefix="loopguard-"))
    cid = f"lg-{uuid.uuid4().hex[:10]}"
    result_store.set_session_context(cid, "루프가드")
    slot = result_store.turn_slot()
    target = slot / "charts.spec.json"
    target.write_text(content, encoding="utf-8")
    return result_store.to_result_relative(target)


def _display_call(source: str) -> ToolCall:
    return ToolCall(id="c1", name="display_chart", arguments={"source": source})


def test_same_args_same_file_same_signature() -> None:
    src = _make_artifact()
    assert _call_signature(_display_call(src)) == _call_signature(_display_call(src))


def test_changed_file_changes_signature() -> None:
    """파일 내용이 바뀌면 같은 인자라도 시그니처가 달라진다 (재시도 허용)."""
    src = _make_artifact("v1")
    sig_before = _call_signature(_display_call(src))

    target, error = result_store.resolve_result_path(src)
    assert error is None and target is not None
    # 길이가 다른 내용으로 덮어써 mtime 해상도와 무관하게 size 차이를 보장한다.
    target.write_text("v2-changed-content", encoding="utf-8")

    assert _call_signature(_display_call(src)) != sig_before


def test_nested_result_path_contributes_fingerprint() -> None:
    """dict/list 중첩 위치의 'result/...' 경로도 fingerprint 에 잡힌다."""
    src = _make_artifact()
    call = ToolCall(id="c2", name="t", arguments={"specs": [{"path": src}]})
    assert _call_signature(call)[2] != ""


def test_non_result_args_have_empty_fingerprint() -> None:
    call = ToolCall(id="c3", name="echo", arguments={"text": "안녕", "n": 3})
    assert _call_signature(call)[2] == ""


def test_missing_result_path_ignored() -> None:
    """존재하지 않는 result/ 경로는 fingerprint 에 기여하지 않는다 (에러 없이 통과)."""
    call = ToolCall(
        id="c4", name="t", arguments={"source": "result/없는세션/20990101-000000/x.md"}
    )
    assert _call_signature(call)[2] == ""


def test_record_invalid_call_blocks_repeat_until_file_changes() -> None:
    """동일 호출 반복은 차단, 참조 파일이 바뀐 뒤 재호출은 다시 허용된다."""
    src = _make_artifact("v1")
    history: set[tuple[str, str, str]] = set()

    assert _record_invalid_call(_display_call(src), history) is False
    assert _record_invalid_call(_display_call(src), history) is True

    target, _ = result_store.resolve_result_path(src)
    assert target is not None
    target.write_text("v2-longer-content", encoding="utf-8")

    assert _record_invalid_call(_display_call(src), history) is False


if __name__ == "__main__":
    run_tests(globals())
