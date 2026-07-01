# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

Svelte(Vite) 정적 자산을 FastAPI가 서빙하고 PyInstaller로 단일 `.exe`로 패키징하는 AI Agent 채팅 UI 앱.
다중 대화 세션(localStorage 영속화) · LLM 설정 UI · GitHub Enterprise Releases 자동 업그레이드(sha256 검증, self-replace) 내장.

- Python 패키지 관리: `uv` / JS 패키지 관리: `npm` (명령어 전체 → `.claude/rules/commands.md`)
- 빌드 산출물 흐름: **`build/` (중간)** → **`release/` (GitHub Release 첨부 대상)**
- **앱 이름 변경**: `.env`의 `APP_NAME` 값 하나만 바꾸면 된다. `App.spec`과 `release.ps1`이 이 값을 읽는다.
- 환경 변수: `.env`가 빌드 파이프라인의 단일 진실 공급원 → 전체 표는 `.claude/rules/environment.md`.

> ⛔ **`docs/overview/` 는 사람이 관리하는 프로젝트 소개 자료다(마크다운 원고).** 사용자가 그 폴더를
> 갱신하라고 **명시적으로 지시한 경우에만** 읽거나 편집한다. 그 외에는 — 코드/문서를 광범위하게
> 손볼 때라도 — `docs/overview/**` 를 자발적으로 열거나 수정하지 않는다.

---

## 자주 쓰는 명령어

```powershell
uv run python backend/main.py                       # 백엔드 dev 서버 (터미널 1)
cd frontend; npm run dev                             # Vite dev 서버 (터미널 2)
uv run ruff format . && uv run ruff check --fix .    # Python 변경 후 반드시 실행
uv run python -m pytest backend/tests/ -v            # 테스트 전체
pwsh packaging/release.ps1 -Channel prod -Upload     # Prod 빌드 + 릴리즈
```

> 테스트 파일별 커버리지 맵 · 릴리즈 채널 플래그 · 의존성 명령 전체 → `.claude/rules/commands.md`.

---

## 에이전트 설계 원칙 (필독)

이 프로젝트는 **미리 갖추어진 Python API를 plan에 따라 실행하는 Agent 플랫폼**이다.
코드를 작성하거나 파일을 편집하는 AI 코딩 어시스턴트가 아니다.

| 상황 | 에이전트 행동 |
|---|---|
| 일반 질문 | 텍스트로 직접 답변 |
| 도구 실행이 필요한 작업 | `add_todo` 로 plan 작성 → 등록된 tool 순차 실행 → `complete_todo` |
| 복잡한 작업 (여러 도메인) | 오케스트레이터가 `call_sub_agent`(순차) 또는 `call_sub_agents_parallel`(독립 작업 동시) 로 서브 에이전트에게 위임 |
| 산출물을 저장해야 할 때 | `save_artifact(filename, content/source, kind)` → 반환된 `path` 를 `display_markdown` 등에 전달. kind 는 markdown/json/text/parquet + 바이너리(png/svg/pdf/pptx/xlsx, namespace `$bytes` 변수) |
| 과거 산출물을 재사용할 때 | `list_artifacts` 로 경로 재발견 → `load_artifact(path, store_as)` 로 namespace 로 복원 → 후속 분석. 단순 재표시는 `display_*` 에 경로 직접 전달 |

**서브 에이전트 제약**: 기본 순차 실행. 독립·완결 작업은 `call_sub_agents_parallel(tasks=[...])` 로 **옵트인 병렬** 실행 가능(동시성 상한 `APP_MAX_PARALLEL_SUBAGENTS`). 백그라운드 실행 없음, 서브가 `call_sub_agent`/`call_sub_agents_parallel` 재호출 불가(4중 방어선).  
→ 중첩 차단 방어선 · 병렬 디스패치 상세: `.claude/rules/agent_runtime.md`

| 디렉터리 | 역할 | 라우팅 |
|---|---|---|
| `SKILLS/` | 오케스트레이터·서브 에이전트 공통 작업 가이드 | Front Matter `trigger` 키워드 매칭 |
| `AGENTS/` | 서브 에이전트 페르소나·도구 화이트리스트 | `call_sub_agent(agent_name=...)` 명시 위임 |

> **Mock 전용 콘텐츠**: 현재 `SKILLS/`, `AGENTS/`, `backend/scripts/` 의 파일들은 실 LLM 없이
> Harness/UI 를 검증하는 **Mock 시나리오(A~H)** 다. 운영 시 도메인 콘텐츠로 교체·삭제한다.
> `APP_ALLOWED_LIBRARIES=scripts,polars` 도 운영 라이브러리로 교체. 트리거·검증 대상 표는
> `docs/guides/mock-scenarios.md`.

---

## 확장 시스템 (Extensions)

**`extensions/`** — 메인 앱과 완전히 격리된 독립 도구(Svelte5 SPA + FastAPI 라우터). 폴더 단위로
추가·삭제 가능(host 코드 변경 없음). 예시: [evaluator](extensions/evaluator/) (parquet 큐레이션 UI).

모든 확장은 **채팅창 우측 아티팩트 패널에 same-origin iframe 으로 임베드**되어 열린다. 두 진입 경로:
① 에이전트가 `open_curation(tool, sources, mapping)` 호출 → `kind:"extension"` 칩이
`/ext/<tool>/?bundle=` iframe 을 자동으로 연다(메시지 영속). ② TopBar 드롭다운 런처로 소스 없이
열면 확장의 **랜딩 페이지**가 뜬다.

→ 격리 원칙·로더·`open_curation` 규약·런처·App.spec 번들: `.claude/rules/extensions_architecture.md`  
→ evaluator 심화(API 라우터·ColumnMapping·export·차트 구현): `.claude/rules/extensions_evaluator.md`  
→ 개발자 가이드: `docs/guides/extensions.md`

---

## 상세 문서

**`.claude/rules/`** — 아키텍처 참고서 (Claude Code 전용)

| 파일 | 내용 |
|---|---|
| `commands.md` | 자주 쓰는 명령어 · 테스트 파일별 커버리지 맵 · 릴리즈 채널 플래그 |
| `environment.md` | 환경 변수 전체 표 (`.env` 단일 진실 공급원 · frozen vs dev) |
| `app_lifecycle.md` | PyInstaller 경로 분기 · App 기동 시퀀스 · Presence · 동시성 · Origin 가드 |
| `agent_runtime.md` | 에이전트 원칙 · AgentRegistry · 런타임 메타 도구 · 아티팩트 IO · manifest · namespace · evaluator 보안 · 도구 등록 · 로딩 정책 |
| `charts_pipeline.md` | ViewState 스택 · `/api/chart/filter` · 렌더러 확장(R8) |
| `harness_resilience.md` | Harness 복원력 불변식 — F1~F12·R1~R8 카탈로그 ("이 방어 코드가 있는 이유") |
| `frontend_state.md` | `$state ui` · 액션 함수 · localStorage 스키마 · 데이터 흐름 · 세션 동기화 · reactive proxy 주의 |
| `frontend_components.md` | 컴포넌트 카탈로그 · ModelPicker · TurnStatus · 서브에이전트 트레일 · 차트 인터랙션 UI · 테마 |
| `extensions_architecture.md` | 확장 시스템 공통 — 격리 원칙 · 로더 · `open_curation` 규약 · 런처 · App.spec 번들 · 새 확장 추가 |
| `extensions_evaluator.md` | evaluator 심화 — API 라우터 · ColumnMapping · export · 프론트 진입 · 차트 구현 |
| `settings_architecture.md` | LLM 설정 저장 구조(멀티 프로바이더) · API key 보안 · threading.Lock |
| `update_architecture.md` | 자동 업데이트 4단계 · rename-to-backup 전략 · 콘텐츠 동기화(SKILLS/AGENTS/PROMPTS 런타임 갱신) · 릴리즈 빌드 순서 · PowerShell 5.1 주의 |
| `agent_extension.md` | 새 Tool 등록 · 서브 에이전트 등록 · AgentMeta 확장 필드 · 새 LLM 프로바이더 추가 |
| `code_conventions.md` | Python 코딩 규칙 · ruff · 타입 힌트 · Pydantic |

**`docs/guides/`** — 에이전트·도구 개발자 참고서

| 파일 | 내용 |
|---|---|
| `guides/builtin-tools.md` | `save_artifact` · `display_chart` · `display_markdown` · `open_curation` 등 내장 도구 전체 + 차트 파이프라인 |
| `guides/extensions.md` | 확장 시스템 개발자 가이드 — 디렉터리 컨벤션 · 패널 iframe 임베드 · 런처 드롭다운/`extension.json` · 랜딩 페이지 · 새 확장 추가 |
| `guides/charts.md` | `display_chart` 차트 유형(mark)별 encoding · parquet+spec 파이프라인 · brush 필터 지원 차트 |
| `guides/library-runtime.md` | `api_refs` 메타 도구 8개 · 세션 namespace · evaluator 보안 모델 |
| `guides/mock-scenarios.md` | 시나리오 A~H 상세 흐름 · 산출물 경로 · 신규 시나리오 추가 방법 |
| `guides/skills.md` | `SKILLS/*.md` Front Matter · 트리거 매칭 원리 · `activate_skill` (3번째 경로) |
| `guides/agents.md` | `AGENTS/*.md` Front Matter · Case 3 라우팅 · 페르소나 작성법 |
| `guides/prompts.md` | `PROMPTS/*.md` 합성 순서 · 핫리로드 정책 |

**`docs/harness/`** — 하니스 동작 흐름·구조 (패키지 단위, 개발자 심화)

| 파일 | 내용 |
|---|---|
| `harness/README.md` | 턴 생애주기 다이어그램 · 모듈 맵 · 중복방지 안내 |
| `harness/turn-loop.md` | `loop.py`·`lifecycle.py`·`compaction.py` — run_turn · _run_agent_turn · budget · tool_exec · wind-down(R7)/fallback(F6) · 히스토리 압축(R10) |
| `harness/call-handlers.md` | `call_handlers.py` — 3단계 파이프라인 · sentinel 라우트 · 가드(`activate_skill` 포함) |
| `harness/dispatch.md` | `dispatch/` — 순차·병렬(dispatch_id·semaphore) · spec_filter(4중 차단) · result_format |
| `harness/prompt.md` | `prompt/` — compose · sections · artifacts · api_refs · wind_down |
| `harness/state.md` | `state/` — todo · balancing · loop_guard · pending · persistence(실패 턴 영속) |
