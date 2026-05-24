<script>
  /**
   * 슬롯 가드가 발동했을 때 표시하는 질문 카드.
   *
   * options 가 있으면 클릭 가능한 pill 버튼을 렌더링하고, 없으면 질문 텍스트만 보여
   * 사용자가 아래 입력창에 직접 답변을 입력하도록 안내한다.
   *
   * answered=true 이면 카드 전체를 비활성화(dimmed)하여 이미 답변한 질문임을 나타낸다.
   *
   * 버튼 클릭 → sendMessage(option) 호출 → 기존 채팅 흐름으로 라우팅됨.
   * 백엔드는 pending_tool + "Pending Slot" system prompt 블록으로 자동 처리한다.
   */

  import { ui } from "../lib/state.svelte.js";
  import { sendMessage } from "../lib/chatActions.svelte.js";

  let { askUser } = $props();

  let isStreaming = $derived(ui.streaming);
  let isDisabled = $derived(askUser.answered || isStreaming);

  /**
   * 옵션 버튼 클릭 핸들러.
   * @param {string} option
   */
  async function handleOption(option) {
    if (isDisabled) return;
    await sendMessage(option);
  }
</script>

<div class="ask-card" class:answered={askUser.answered}>
  {#if askUser.tool_name}
    <div class="tool-label">🔧 {askUser.tool_name} 실행을 위한 질문</div>
  {/if}

  <p class="question">{askUser.question}</p>

  {#if askUser.options && askUser.options.length > 0}
    <div class="options" role="group" aria-label="선택지">
      {#each askUser.options as option (option)}
        <button
          class="option-btn"
          type="button"
          disabled={isDisabled}
          onclick={() => handleOption(option)}
        >
          {option}
        </button>
      {/each}
    </div>
    {#if !askUser.answered}
      <p class="hint">또는 아래 입력창에 직접 입력하세요</p>
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
    transition: opacity 0.2s;
  }

  .ask-card.answered {
    opacity: 0.6;
  }

  .tool-label {
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
    background: color-mix(in srgb, var(--accent) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
    border-radius: 20px;
    padding: 4px 12px;
    cursor: pointer;
    transition:
      background 0.15s,
      border-color 0.15s;
  }

  .option-btn:hover:not(:disabled) {
    background: color-mix(in srgb, var(--accent) 18%, transparent);
    border-color: color-mix(in srgb, var(--accent) 50%, transparent);
  }

  .option-btn:disabled {
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
