# SKILLS 작성 가이드

`SKILLS/` 디렉터리의 마크다운 파일들은 **에이전트의 상황별 행동 지침**이다.
사용자 메시지에 트리거 키워드가 포함되면 해당 파일의 본문이 시스템 프롬프트에 주입된다.
코드를 수정하지 않고 파일 추가만으로 에이전트 동작을 확장할 수 있는 핵심 확장 포인트다.

---

## 파일 구조

```
SKILLS/
  report_generator.md   ← 파일명은 자유, name Front Matter 가 실제 식별자
  time_lookup.md
  data_analysis.md
```

파일마다 YAML Front Matter + 마크다운 본문으로 구성된다.

```markdown
---
name: report_generator
description: 매출 보고서를 조회·생성·이메일 발송하는 멀티스텝 작업
trigger: ["보고서", "리포트", "report", "이메일 발송", "주간 매출"]
priority: 8
requires_tools: ["fetch_sales", "render_report", "send_email"]
---

# 보고서 자동 생성 가이드
...본문...
```

---

## Front Matter 필드

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `name` | string | **필수** | — | 스킬 식별자. 슬래시 커맨드(`/report_generator`), `AGENTS/` 의 `skills` 목록에서 이 이름으로 참조 |
| `description` | string | 선택 | `""` | 한 줄 요약. 슬래시 커맨드 자동완성 패널에 표시 |
| `trigger` | string[] | 선택 | `[]` | 사용자 메시지에서 찾을 키워드 목록. 대소문자 무관 부분문자열 매칭 |
| `priority` | int | 선택 | `5` | 여러 스킬이 동시에 매칭될 때 우선순위. 값이 클수록 먼저 선택 |
| `requires_tools` | string[] | 선택 | `[]` | 이 스킬이 사용하는 도구 이름 힌트. 해당 도구가 미등록이면 priority 에서 감점 |
| `api_refs` | string[] | 선택 | `[]` | 외부 Python 라이브러리 dotted-path 목록. 활성화 시 시그니처·docstring 이 system prompt 에 자동 주입되고 메타 도구 8종이 자동 노출됨 → [library-runtime.md](library-runtime.md) |
| `expose` | bool | 선택 | `true` | `false` 면 **유저 비노출** — 슬래시 메뉴·trigger·이름 매칭 전부 차단. `activate_skill` 로만 켜지는 비공개 SKILL |

### name

- 영소문자 + 언더스코어 형식 권장: `sales_report`, `time_lookup`
- `AGENTS/` Front Matter 의 `skills` 배열에 이 이름을 적어야 Case 3 라우팅이 작동
- 슬래시 커맨드로 강제 활성화할 때도 이 이름을 사용: `/sales_report`

### trigger

```yaml
trigger: ["보고서", "리포트", "report", "이메일 발송", "주간 매출", "일일 매출"]
```

- 사용자 메시지 전체에서 각 키워드를 **포함 여부**로 판단 (정규식 아님)
- 여러 키워드가 동시에 포함되면 hit count 가 늘어 우선순위 상승
- `trigger` 가 없어도 사용자가 `name` 자체를 입력하면 매칭됨 (`"time_lookup 써줘"` → `time_lookup` 활성)

### priority

- 동점(hit count 동일)일 때 이 값이 높은 스킬이 먼저 선택됨
- 한 턴에 최대 3개 스킬이 동시 활성화될 수 있음
- `requires_tools` 에 등록되지 않은 도구가 있으면 `priority -= 미등록_수 × 10` 감점

### requires_tools

```yaml
requires_tools: ["fetch_sales", "send_email"]
```

- 실제 실행을 강제하지 않음 — 우선순위 계산 힌트용
- 나열한 도구가 `ToolRegistry` 에 없으면 이 스킬의 priority 가 자동 감점됨
- 도구가 필요 없는 순수 가이드 스킬이면 생략하거나 빈 리스트로 둠

### expose — 비공개(유저 비노출) SKILL

여러 SKILL 이 공유하는 작은 작업 조각처럼, **유저에게 노출할 필요는 없지만 다른 SKILL/에이전트가
재사용하고 싶은** SKILL 은 `expose: false` 로 숨긴다.

```yaml
---
name: clean_candidates
description: 후보 표 정제 공통 절차 (비공개)
expose: false
---
```

- `false` 면 **유저 도달 경로가 전부 차단**된다: 슬래시 자동완성 메뉴, `/이름` 강제 활성화,
  trigger 키워드 매칭, 메시지 안 이름 매칭. 유저는 어떤 방법으로도 직접 켤 수 없다.
- **들어오는 길은 `activate_skill(name)` 하나뿐** — 부모 SKILL 본문이나 에이전트가 이름으로 호출한다.
  비공개 SKILL 은 비활성 카탈로그에도 안 뜨므로, **본문에서 이름을 명시한 곳에서만** 발견된다.

  ```markdown
  # 부모 SKILL 본문 예시
  2. 후보를 정제한다 — `activate_skill('clean_candidates')` 로 정제 절차를 켜고 그대로 따른다.
  ```

- 기본값은 `true` — 생략하면 기존처럼 유저에게 노출되는 일반 SKILL 이다.
- **파일명 `_` 접두는 무관**하다(레지스트리는 `*.md` 를 전부 로드). 숨김 여부는 오직 `expose: false`
  로 결정된다.
- `activate_skill` 은 카탈로그가 아니라 전체 레지스트리에서 이름으로 해석하므로, 비공개라도 이름만
  정확하면 켜진다. 따라서 비공개 SKILL 의 `trigger` 는 무의미(있어도 차단됨) — 보통 생략한다.

---

## 본문(Body) 작성 요령

본문은 시스템 프롬프트에 `# Skill: {name}\n{본문}` 형태로 그대로 주입된다.
LLM이 읽을 지시문이므로 **명확한 행동 규칙**을 우선적으로 작성한다.

### 단순 스킬 — 도구 1~2개, 단일 호출

```markdown
---
name: time_lookup
trigger: ["지금 시간", "현재 시각", "몇 시", "now"]
priority: 3
requires_tools: ["now"]
---

# 가이드
- `now` 도구를 한 번만 호출한다.
- 결과는 "현재 시각은 …입니다." 한 문장으로 답한다.
- 시각 외 정보 요청(날짜 계산, 타임존 변환)은 명확하지 않으면 되묻는다.
```

### 멀티스텝 스킬 — add_todo 패턴 필수

두 단계 이상의 순차 작업이 있으면 반드시 `add_todo` 패턴을 명시한다.

```markdown
---
name: report_generator
trigger: ["보고서", "리포트", "주간 매출"]
priority: 8
requires_tools: ["fetch_sales", "render_report", "send_email"]
---

# 보고서 자동 생성 가이드

## 절차
1. `add_todo` 로 아래 3단계를 한 번에 등록한다.
2. `fetch_sales(date_from, date_to)` 데이터 조회 → `complete_todo`
3. `render_report(template, data)` 본문 생성 → `complete_todo`
4. `send_email(to, subject, body)` 발송 → `complete_todo`

## 필수 슬롯
- 보고 기간: 명시하지 않으면 되묻는다.
- 수신자: 명시하지 않으면 선택지를 제시한다.

## 금지
- 임의 수신자나 이메일 주소를 추측하지 않는다.
- 데이터가 없을 때 더미 값을 채워 넣지 않는다.
```

### 다른 SKILL 호출 — 본문에서 `activate_skill`

본문에 `activate_skill('이름')` 을 시키는 지시문을 적어 두면, LLM 이 그 단계에서 다른 SKILL 을
런타임에 켜고 켜진 지침을 그대로 따른다. 여러 부모 SKILL 이 공유하는 작은 절차 조각을
비공개 SKILL(`expose: false`)로 빼두고 이름으로 호출하는 것이 대표 용법이다.

```markdown
---
name: weekly_report
trigger: ["주간 리포트"]
requires_tools: ["fetch_sales", "render_report"]
---

# 주간 리포트 가이드

## 절차
1. `add_todo` 로 아래 단계를 등록한다.
2. `fetch_sales(date_from, date_to)` 로 데이터를 조회한다 → `complete_todo`
3. 후보 표를 정제한다 — `activate_skill('clean_candidates')` 로 정제 절차를 켜고,
   켜진 지침을 그대로 수행한다 → `complete_todo`
4. `render_report(...)` 로 리포트를 만든다 → `complete_todo`
```

- 호출 대상은 **전체 레지스트리에서 이름으로 직접 해석**되므로, 비활성 카탈로그에 안 뜨는
  `expose: false` 비공개 SKILL 도 이름만 정확하면 켜진다 (→ [expose 절](#expose--비공개유저-비노출-skill)).
- 켜진 SKILL 본문은 그 턴의 system prompt 에 즉시 합쳐진다.

#### 비공개 SKILL 체인 (A → a → b → c → A 마무리)

부모 A 가 비공개 a → b → c 를 차례로 거친 뒤 A 의 남은 절차를 마치고 끝내는 흐름도 가능하다.
다만 **콜 스택이 아니라 누적 모델**임을 유의한다 — `activate_skill` 은 활성 목록에 *추가*만 하므로,
켜진 SKILL 본문들이 동시에 컨텍스트에 쌓인 채로 남는다. "c 가 끝나면 A 로 복귀"는 자동 pop 이
아니라 A 본문이 계속 살아 있어 LLM 이 남은 단계를 이어가는 형태다.

```markdown
---
name: candidate_pipeline
trigger: ["후보 파이프라인"]
---

# 후보 파이프라인 가이드

## 절차
1. `add_todo` 로 정제 → 스코어링 → 랭킹 → 요약 4단계를 한 번에 등록한다.
2. `activate_skill('_clean')` 로 정제 후 결과를 확인한다 → `complete_todo`
3. `activate_skill('_score')` 로 스코어링한다 → `complete_todo`
4. `activate_skill('_rank')` 로 순위를 매긴다 → `complete_todo`
5. (이 SKILL 본문으로 복귀) 상위 N개를 표로 요약하고 마무리한다 → `complete_todo`
```

- **순서·종료는 본문이 관리한다**: SKILL 에는 형식적 완료 신호가 없으므로, 순차 실행이
  중요하면 위처럼 `add_todo` 로 단계를 박아 LLM 이 순서를 지키게 한다.
- **예산 주의**: `activate_skill` 한 번이 도구 라운드트립 한 번이다. 체인이 깊으면 활성화
  호출 + 각 단계 작업이 누적돼 `APP_MAX_AGENT_ITERATIONS`(12)·`APP_MAX_AGENT_CALLS_PER_TURN`(20)
  예산을 빠르게 소진하고 wind-down(R7)에 마무리가 잘릴 수 있다. 단계가 많고 서로 독립적이면
  서브에이전트 위임(`call_sub_agent` / `call_sub_agents_parallel`)을 우선 검토한다.

### 서술 구조 권장 패턴

| 섹션 | 내용 |
|---|---|
| `## 절차` | 순서가 중요한 경우 numbered list |
| `## 필수 슬롯` | 반드시 확인해야 할 입력값과 확인 방법 |
| `## 행동 원칙` | 어떤 방식으로 판단할지 |
| `## 금지` | 해선 안 되는 행동 명시 |
| `## 출력 형식` | 최종 응답의 형태 |

---

## 라우팅 동작 상세

```
사용자: "이번 주 매출 보고서 뽑아줘"
  ↓
SkillRegistry.select("이번 주 매출 보고서 뽑아줘")
  ↓
trigger 매칭:
  report_generator: "보고서"(1hit), "주간 매출"(1hit) → 2hits, priority=8
  data_analysis:    "보고서"(0hit)                     → skip
  ↓
상위 3개 선택 → [report_generator]
  ↓
system prompt 에 주입:
  # Skill: report_generator
  {report_generator.md 본문}
```

### 슬래시 커맨드로 강제 활성화

trigger 매칭 없이 특정 스킬을 강제 활성화하려면 UI Composer 에서 슬래시를 입력한다.

```
사용자: /report_generator
```

`force_skills=["report_generator"]` 로 API 에 전달되어 trigger 매칭을 우회하고
해당 스킬이 바로 시스템 프롬프트에 포함된다.

### LLM 능동 활성화 — `activate_skill` (3번째 경로)

트리거 키워드를 놓쳤거나 어떤 스킬을 써야 할지 LLM이 스스로 판단해야 할 때,
**비활성 SKILL 카탈로그**를 확인한 후 `activate_skill(name)` 도구를 호출해 해당 스킬을
런타임에 활성화할 수 있다.

- 활성화하면 system prompt 가 동적으로 재조립되어 그 턴 안에서 스킬 지침이 적용된다
- 비활성 카탈로그(이름·description·trigger)는 `# Inactive Skills` 섹션으로 system prompt에 포함됨
- SKILL 수가 많을 때 LLM이 트리거 미스를 보완하는 안전망으로 작동한다

```
SKILL 활성화 3가지 경로:
① 트리거 키워드 자동 매칭  (SkillRegistry.select)
② 슬래시 커맨드 강제 지정  (/skill_name → force_skills)
③ LLM 능동 활성화           (activate_skill 도구 호출 → 동적 재조립)
```

### 멀티 스킬 동시 활성화

3개까지 동시 활성화된다. 이 경우 harness 가 자동으로 다음 지침을 추가 주입한다:

> "실제 작업을 시작하기 전에 반드시 `add_todo` 로 각 스킬의 실행 순서를 등록하세요."

---

## 자주 하는 실수

| 실수 | 결과 | 수정 방법 |
|---|---|---|
| `name` 을 파일명과 다르게 설정 | `AGENTS/` 에서 참조 실패 | `name` 과 파일명을 일치시킬 것 (필수는 아니지만 권장) |
| `trigger` 를 문자열로 작성 | Front Matter 파싱 오류, 스킬 로드 실패 | 반드시 YAML 배열 형식 `["a", "b"]` |
| `requires_tools` 에 실제 미등록 도구 나열 | priority 감점으로 다른 스킬에 밀림 | 미등록 도구는 나열하지 않거나 먼저 등록 |
| 본문에 `add_todo` 언급 없이 다단계 지시 | LLM이 plan 없이 단계 실행, TodoProgress UI 미표시 | 2단계 이상이면 반드시 절차 섹션에 `add_todo` 패턴 명시 |
