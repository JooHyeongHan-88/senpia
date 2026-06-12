<script>
  /**
   * LLM 추론 과정(reasoning_content)을 접을 수 있는 블록으로 표시한다.
   *
   * - streaming=true 이면 헤더에 "생각 중..." 애니메이션을 보여 준다.
   * - 기본은 접힌 상태이며, 클릭으로 토글한다.
   * - 스트리밍이 끝나면 헤더가 "추론 과정"으로 바뀐다.
   */

  let { text = "", streaming = false } = $props();

  let expanded = $state(false);
</script>

<div class="reasoning-wrap">
  <button
    class="reasoning-header"
    type="button"
    onclick={() => (expanded = !expanded)}
    aria-expanded={expanded}
  >
    <span class="chevron" class:open={expanded}>›</span>
    {#if streaming && !text}
      <span class="label">생각 중</span>
      <span class="thinking-dots" aria-hidden="true">
        <span></span><span></span><span></span>
      </span>
    {:else}
      <span class="label">{streaming ? "생각 중..." : "추론 과정"}</span>
    {/if}
  </button>

  {#if expanded && text}
    <div class="reasoning-body">{text}</div>
  {/if}
</div>

<style>
  .reasoning-wrap {
    margin-bottom: 8px;
  }

  .reasoning-header {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: none;
    border: none;
    padding: 2px 4px;
    cursor: pointer;
    color: var(--fg-muted);
    font-size: 12px;
    line-height: 1.5;
    border-radius: var(--radius-sm);
    transition: color var(--dur-fast);
  }

  .reasoning-header:hover {
    color: var(--fg);
  }

  .chevron {
    display: inline-block;
    font-size: 14px;
    line-height: 1;
    transition: transform var(--dur-slow) ease;
    transform: rotate(0deg);
  }

  .chevron.open {
    transform: rotate(90deg);
  }

  .label {
    font-size: 12px;
    font-weight: 500;
  }

  /* ── 스트리밍 중 점 애니메이션 ── */
  .thinking-dots {
    display: inline-flex;
    gap: 3px;
    align-items: center;
    margin-left: 2px;
  }

  .thinking-dots span {
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: var(--fg-muted);
    animation: reasoning-blink 1.2s infinite ease-in-out both;
  }

  .thinking-dots span:nth-child(2) {
    animation-delay: 0.15s;
  }

  .thinking-dots span:nth-child(3) {
    animation-delay: 0.3s;
  }

  @keyframes reasoning-blink {
    0%,
    80%,
    100% {
      opacity: 0.25;
      transform: scale(0.85);
    }
    40% {
      opacity: 1;
      transform: scale(1);
    }
  }

  /* ── 추론 본문 ── */
  .reasoning-body {
    margin-top: 4px;
    padding: 8px 12px;
    border-left: 2px solid var(--border);
    font-size: 12px;
    line-height: 1.6;
    color: var(--fg-muted);
    white-space: pre-wrap;
    word-wrap: break-word;
  }
</style>
