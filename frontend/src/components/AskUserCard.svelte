<script>
  /**
   * 보완 질문 카드 — 슬롯 가드 또는 ask_user sentinel 이 발생시킨 질문을 표시.
   *
   * input_type 으로 3-mode 렌더링:
   *   - "choice": 옵션 버튼만 (자유 입력 hint 없음)
   *   - "text":   질문 텍스트만 (옵션 버튼 미표시) — 사용자는 아래 Composer 에 직접 입력
   *   - "both":   옵션 버튼 + "또는 직접 입력하세요" hint
   *
   * answered=true 이면 카드 전체를 비활성화(dimmed)하여 이미 답변한 질문임을 나타낸다.
   *
   * 버튼 클릭 → sendMessage(option) 호출 → 기존 채팅 흐름으로 라우팅됨.
   * 백엔드는 pending_tool / pending_question system prompt 블록으로 자동 컨텍스트 재주입.
   */

  import { ui } from "../lib/state.svelte.js";
  import { sendMessage } from "../lib/chatActions.svelte.js";

  let { askUser } = $props();

  let isStreaming = $derived(ui.streaming);
  let isDisabled = $derived(askUser.answered || isStreaming);
  // 구버전 메시지 (input_type 없음) 호환 — options 유무로 폴백.
  let mode = $derived(askUser.input_type ?? (askUser.options ? "both" : "text"));
  let showOptions = $derived(
    (mode === "choice" || mode === "both") && askUser.options?.length > 0,
  );
  // 다중 선택 모드 — 옵션이 실제로 표시될 때만 의미 있다.
  let multi = $derived(!!askUser.multi_select && showOptions);

  // 다중 선택 누적 상태 (Svelte 5: 재할당으로 반응성 트리거).
  let selected = $state([]);
  let canSubmit = $derived(multi && selected.length > 0 && !isDisabled);

  /**
   * 단일 선택 — 클릭 즉시 전송.
   * @param {string} option
   */
  async function handleOption(option) {
    if (isDisabled) return;
    await sendMessage(option);
  }

  /**
   * 다중 선택 토글 — 선택 목록에 추가/제거.
   * @param {string} option
   */
  function toggleOption(option) {
    if (isDisabled) return;
    selected = selected.includes(option)
      ? selected.filter((o) => o !== option)
      : [...selected, option];
  }

  /** 다중 선택 확정 — 고른 항목을 한 메시지로 합쳐 전송. */
  async function submitMulti() {
    if (!canSubmit) return;
    await sendMessage(selected.join(", "));
  }
</script>

<div class="ask-card" class:answered={askUser.answered}>
  {#if askUser.tool_name}
    <div class="tool-label">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
      </svg>
      {askUser.tool_name} 실행을 위한 질문
    </div>
  {/if}

  <p class="question">{askUser.question}</p>

  {#if showOptions}
    <div class="options" role="group" aria-label="선택지">
      {#each askUser.options as option (option)}
        {#if multi}
          <button
            class="option-btn"
            class:selected={selected.includes(option)}
            type="button"
            aria-pressed={selected.includes(option)}
            disabled={isDisabled}
            onclick={() => toggleOption(option)}
          >
            {option}
          </button>
        {:else}
          <button
            class="option-btn"
            type="button"
            disabled={isDisabled}
            onclick={() => handleOption(option)}
          >
            {option}
          </button>
        {/if}
      {/each}
    </div>
  {/if}

  {#if multi && !askUser.answered}
    <button
      class="submit-btn"
      type="button"
      disabled={!canSubmit}
      onclick={submitMulti}
    >
      선택 완료{selected.length > 0 ? ` (${selected.length})` : ""}
    </button>
  {/if}

  {#if !askUser.answered}
    {#if multi}
      {#if mode === "both"}
        <p class="hint">여러 개를 고른 뒤 선택 완료를 누르거나 직접 입력하세요</p>
      {:else}
        <p class="hint">여러 개를 고른 뒤 선택 완료를 누르세요</p>
      {/if}
    {:else if mode === "both"}
      <p class="hint">또는 아래 입력창에 직접 입력하세요</p>
    {:else if mode === "choice"}
      <p class="hint">위 선택지 중 하나를 골라주세요</p>
    {:else if mode === "text"}
      <p class="hint">아래 입력창에 답변을 입력해주세요</p>
    {/if}
  {/if}

  {#if askUser.answered}
    <span class="answered-label">✓ 답변 완료</span>
  {/if}
</div>

<style>
  .ask-card {
    margin-top: 8px;
    padding: 12px 14px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    display: flex;
    flex-direction: column;
    gap: 8px;
    transition: opacity var(--dur-slow);
  }

  .ask-card.answered {
    opacity: 0.6;
  }

  .tool-label {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: var(--fg-subtle);
    font-family: var(--font-mono);
  }

  .question {
    margin: 0;
    font-size: 14px;
    color: var(--fg);
    line-height: 1.5;
  }

  /* ── 옵션 버튼 ── */
  .options {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .option-btn {
    display: inline-flex;
    align-items: center;
    font-size: 12px;
    font-weight: 500;
    color: var(--accent);
    background: var(--accent-soft);
    border: 1px solid var(--accent-border);
    border-radius: var(--radius-full);
    padding: 4px 12px;
    cursor: pointer;
    transition:
      background var(--dur-fast),
      border-color var(--dur-fast);
  }

  .option-btn:hover:not(:disabled) {
    background: var(--accent-soft-strong);
    border-color: color-mix(in srgb, var(--accent) 50%, transparent);
  }

  /* ── 다중 선택 — 선택된 칩 강조 ── */
  .option-btn.selected {
    background: var(--accent);
    color: var(--accent-fg);
    border-color: var(--accent);
  }

  .option-btn.selected:hover:not(:disabled) {
    background: var(--accent-hover);
    border-color: var(--accent-hover);
  }

  .option-btn:disabled {
    cursor: default;
    opacity: 0.5;
  }

  /* ── 다중 선택 확정 버튼 ── */
  .submit-btn {
    align-self: flex-start;
    font-size: 12px;
    font-weight: 600;
    color: var(--accent-fg);
    background: var(--accent);
    border: 1px solid var(--accent);
    border-radius: var(--radius-full);
    padding: 5px 16px;
    cursor: pointer;
    transition: background var(--dur-fast);
  }

  .submit-btn:hover:not(:disabled) {
    background: var(--accent-hover);
  }

  .submit-btn:disabled {
    cursor: default;
    opacity: 0.5;
  }

  .hint {
    margin: 0;
    font-size: 11px;
    color: var(--fg-subtle);
  }

  .answered-label {
    font-size: 11px;
    color: var(--color-success);
    font-weight: 500;
  }
</style>
