---
name: _time_log_render
description: 조회한 시각을 마크다운 로그로 저장하고 패널에 렌더링하는 공통 절차 (비공개 의존 SKILL)
expose: false
requires_tools:
  - save_artifact
  - display_markdown
---

# 시각 로그 저장·렌더링 절차

상위 SKILL이 이미 조회한 시각 문자열을 받아, 마크다운 로그로 저장하고 우측 패널에 렌더링한다.
이 SKILL은 유저에게 노출되지 않으며 `activate_skill('_time_log_render')` 로만 켜진다.

## 단계

1. `save_artifact(filename="time_log.md", kind="markdown")` 로 "현재 시각 기록" 문서를 저장한다.
2. 반환된 `result/<session>/<ts>/time_log.md` 경로를 `display_markdown` 으로 패널에 렌더링한다.

## 주의

- `display_markdown` 의 `source` 는 항상 `result/<session>/<ts>/<filename>` 형식이어야 한다
  (절대경로·외부 URL 금지).
- 동일 인자 연속 호출 금지 (loop-guard 차단).
