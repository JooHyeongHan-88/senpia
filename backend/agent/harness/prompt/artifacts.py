"""Session Artifacts 프롬프트 섹션 — 디스크 manifest 기반 산출물 재발견.

히스토리 윈도우 밖이나 세션 복원(tool 메시지 소실) 후에도 LLM 이 과거 산출물을
재발견할 수 있도록, 디스크 manifest 를 진실원천으로 최근 N개를 compact 하게 노출한다.
"""

from core.result_store import current_client_id, read_manifest_entries

# Session Artifacts 프롬프트 섹션 — 노출 개수와 설명 절단 길이 (토큰 예산 통제).
_ARTIFACTS_SECTION_LIMIT = 10
_ARTIFACT_DESC_MAX_CHARS = 80


def _render_session_artifacts_section(limit: int = _ARTIFACTS_SECTION_LIMIT) -> str:
    """현재 세션 산출물 목록을 '# Session Artifacts' 프롬프트 섹션으로 렌더링한다.

    히스토리 윈도우 밖이나 세션 복원(tool 메시지 소실) 후에도 LLM 이 과거
    산출물을 재발견할 수 있도록, 디스크 manifest 를 진실원천으로 최근 N개를
    compact 하게 노출한다. 빈 세션이면 빈 문자열을 반환해 섹션을 생략한다.

    Args:
        limit: 노출할 최대 산출물 수.

    Returns:
        '# Session Artifacts' 섹션 문자열, 또는 산출물이 없으면 "".
    """
    client_id = current_client_id()
    if not client_id:
        return ""

    entries = read_manifest_entries(client_id, limit)
    if not entries:
        return ""

    lines: list[str] = [
        "\n# Session Artifacts",
        "이 세션에서 저장된 산출물 (최신순). 사용자가 과거 산출물을 지칭하면 아래 경로를 사용하라:",
    ]
    for e in entries:
        path = e.get("path", "")
        if not path:
            continue
        kind = e.get("kind", "")
        desc = str(e.get("description", "")).strip()[:_ARTIFACT_DESC_MAX_CHARS]
        shape = ""
        if e.get("rows") is not None and e.get("columns") is not None:
            shape = f", {e['rows']}×{e['columns']}"
        suffix = f" — {desc}" if desc else ""
        lines.append(f"- {path} ({kind}{shape}){suffix}")

    lines.append(
        "재표시는 display_markdown/display_chart/display_image 에 경로를 직접 전달하고, "
        "재계산·추가분석은 load_artifact(path=..., store_as=...) 로 namespace 에 로드하라. "
        "전체 목록이 필요하면 list_artifacts 를 호출하라. "
        "exec_code 에서 'result/...' 를 open() 으로 직접 열지 말고 load_artifact 를 쓰라 "
        "(frozen EXE 경로 안전)."
    )
    return "\n".join(lines)
