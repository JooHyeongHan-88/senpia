# LLM 설정 아키텍처

## 설정 저장 위치

| 항목 | 저장 위치 | 비고 |
|---|---|---|
| provider, model, api_key, base_url | `settings.json` | `SettingsStore`로 관리 |
| temperature, max_tokens | `.env` / 환경 변수 (`APP_LLM_TEMPERATURE` 등) | settings.json에 저장 안 함 |
| system_prompt | `.env` / 환경 변수 (`APP_SYSTEM_PROMPT`) | settings.json에 저장 안 함 |
| 세션·메시지 | 브라우저 localStorage | 백엔드 미저장 |

`settings.json` 경로:
- **dev**: `backend/settings/settings.json`
- **frozen EXE**: `%APPDATA%\{APP_NAME}\settings.json`

## LLMSettings 저장 구조 (멀티 프로바이더)

`LLMSettings`는 `providers: dict[str, ProviderConfig]` 슬롯에 **프로바이더별 접속 정보를 동시에 캐싱**한다.
활성 프로바이더를 전환해도 이전 프로바이더의 model/api_key/base_url이 보존된다.

```json
{
  "provider": "dtgpt",
  "providers": {
    "dtgpt":             { "model": "gpt-4o", "api_key": "sk-...", "base_url": "" },
    "openai_compatible": { "model": "llama-3-70b", "api_key": "...", "base_url": "https://..." }
  }
}
```

`LLMSettings.model` / `api_key` / `base_url` 프로퍼티는 `providers[provider]` 슬롯을 대리해
기존 코드(factory.py 등)와 하위호환성을 유지한다.

**구 포맷 자동 마이그레이션**: `SettingsStore._load()`가 top-level `model/api_key/base_url` 감지 시
신 포맷으로 변환 후 즉시 저장한다.

## 설정 API

| 엔드포인트 | 설명 |
|---|---|
| `GET /api/settings` | 현재 설정 반환 (모든 프로바이더 api_key 마스킹) |
| `POST /api/settings` | 부분 업데이트 (flat 또는 structured patch) |
| `GET /api/settings/providers` | 가용 프로바이더 메타데이터 목록 |
| `GET /api/settings/models?provider=` | 프로바이더 모델 목록 (`{base_url}/models` 호출, 클라이언트 5분 캐시) |
| `POST /api/settings/test` | 연결 테스트 (저장 없이 임시 설정으로 ping) |
| `GET /api/app-info` | 앱 이름·버전 반환 |

### POST /api/settings patch 형식

**flat (UI 저장 형태)**:
```json
{ "provider": "dtgpt", "model": "gpt-4o", "api_key": "sk-new", "base_url": "" }
```
→ `providers["dtgpt"]` 슬롯에만 반영. `provider` 생략 시 현재 활성 프로바이더 슬롯 업데이트.

**model만 변경 (ModelPicker)**:
```json
{ "model": "gpt-4o-mini" }
```

**api_key 처리 규칙**: `null` → 변경 없음, `""` → 키 삭제, `"sk-..."` → 새 값으로 교체.

## ModelPicker 흐름

사이드바 하단의 `ModelPicker.svelte`에서 현재 프로바이더/모델을 표시하고 빠르게 전환할 수 있다.

```
ModelPicker 버튼 클릭
  └─ openModelPicker() → loadModels(currentProvider)
       └─ GET /api/settings/models?provider=dtgpt
            → {base_url}/models 엔드포인트 호출 (5분 TTL, ui.modelListByProvider 캐시)

모델 선택
  └─ POST /api/settings { model: "gpt-4o" } → ui.currentModel 갱신
```

`GET /api/settings/models` 실패(base_url/api_key 미설정) 시 `{ models: [], error: "..." }` 반환.

## SettingsStore — threading.Lock 주의

`backend/settings/store.py`의 `SettingsStore`는 `threading.Lock`을 사용한다.
Python `threading.Lock`은 **non-reentrant** — 같은 스레드에서 두 번 `acquire()` 하면 데드락.

`update()` 내에서 절대 `self.get()`을 호출하지 말 것 (get도 lock을 잡는다).
락 안에서는 `self._cache`를 직접 참조한다.

```python
# ✅ 올바른 패턴
with self._lock:
    if self._cache is None:
        self._load()
    update_dict = self._cache.model_dump()
    ...

# ❌ 데드락 발생
with self._lock:
    current = self.get()   # self._lock 재취득 → 영원히 대기
```

## API Key 보안 규칙

1. API 키는 `settings.json`에만 저장. **브라우저 localStorage에는 절대 저장하지 않는다.**
2. `GET /api/settings` 응답에서 **모든 프로바이더의** api_key는 항상 마스킹(`sk-p••••••4f2a` 형식).
   마스킹 로직은 `backend/settings/masking.py` 단일 지점에서 처리.
3. 에러 메시지에 API 키 평문이 포함되지 않도록 주의.

## 프론트엔드 설정 모달 흐름

```
openSettings()
  ├─ GET /api/settings → draft.cache[provider_id] (프로바이더별 편집 상태)
  ├─ GET /api/settings/providers → ui.providers
  └─ settingsDraft = { provider, cache: { dtgpt: {model, api_key:"", _maskedKey, base_url, clearKey}, ... } }
       └─ api_key 입력 필드는 항상 빈칸 (마스킹키는 placeholder용)

saveSettings()
  └─ POST /api/settings (structured patch: providers 전체 교체)

testConnectionAction()
  └─ POST /api/settings/test
       └─ api_key 비어있으면 백엔드가 동일 provider 슬롯의 저장된 키 fallback 사용
```

## 프로바이더 hot-swap

`/api/chat` 요청마다 `_settings_store.get()`으로 최신 설정을 읽고 `get_provider(settings)`로 인스턴스를 즉시 생성한다.
서버 재시작 없이 프로바이더/모델 전환이 적용된다.

## DTGPT 프로바이더 특이사항

DTGPT는 OpenAI Compatible 구현체(`openai.py`)를 재사용하되, base_url을 settings.json이 아닌 환경 변수에서 고정 주입하는 방식이다.

- **base_url**: `APP_DTGPT_BASE_URL` 환경 변수에서 런타임에 읽음 (`backend/agent/config.py`의 `DTGPT_BASE_URL`)
- **model**: settings.json의 `providers["dtgpt"].model`에 저장 (UI + ModelPicker에서 변경 가능)
- **api_key**: settings.json의 `providers["dtgpt"].api_key`에 저장 (UI에서 입력)
- **UI**: `ProviderMeta.requires_base_url=False`이므로 설정 모달에서 Base URL 필드가 숨겨짐

## 새 프로바이더 추가 방법

→ `.claude/rules/agent_extension.md` 참조.
