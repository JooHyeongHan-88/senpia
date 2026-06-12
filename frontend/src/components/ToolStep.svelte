<script>
  /**
   * 단일 도구 호출을 접을 수 있는 카드로 표시한다.
   *
   * - 접힘(기본): 렌치 아이콘 + name + 상태 표시자 (스피너/✓/!)
   * - 펼침: detail(결과 텍스트) 표시
   * - status==="running" 동안 자동 펼침, 완료 시 자동 접힘.
   * - 사용자가 클릭하면 상태와 무관하게 토글된다.
   */

  let { seg } = $props();

  // null = 자동(running 이면 펼침), true/false = 사용자 명시 토글
  let userExpanded = $state(null);

  let isRunning = $derived(seg.status === "running");
  let expanded = $derived(userExpanded !== null ? userExpanded : isRunning);

  function toggle() {
    userExpanded = !expanded;
  }

  let statusLabel = $derived(
    seg.status === "ok" ? "✓" :
    seg.status === "error" ? "!" :
    null
  );
</script>

<div class="tool-step" data-status={seg.status}>
  <button
    class="tool-header"
    type="button"
    onclick={toggle}
    aria-expanded={expanded}
  >
    <span class="chevron" class:open={expanded}>›</span>
    <span class="tool-icon" aria-hidden="true">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
      </svg>
    </span>
    <span class="tool-name">{seg.name}</span>
    <span class="status-badge" class:ok={seg.status === "ok"} class:error={seg.status === "error"}>
      {#if isRunning}
        <span class="mini-spinner" aria-hidden="true"></span>
      {:else if statusLabel}
        {statusLabel}
      {/if}
    </span>
  </button>

  {#if expanded && seg.detail}
    <div class="tool-detail">{seg.detail}</div>
  {/if}
</div>

<style>
  .tool-step {
    margin: 4px 0;
  }

  .tool-header {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: none;
    border: none;
    padding: 3px 6px 3px 2px;
    cursor: pointer;
    color: var(--fg-muted);
    font-size: 12px;
    font-family: var(--font-mono);
    border-radius: var(--radius-sm);
    transition: color var(--dur-fast), background var(--dur-fast);
    max-width: 100%;
  }

  .tool-header:hover {
    color: var(--fg);
    background: var(--bg-hover, color-mix(in srgb, var(--border) 30%, transparent));
  }

  .chevron {
    display: inline-block;
    font-size: 14px;
    line-height: 1;
    flex-shrink: 0;
    transition: transform var(--dur-slow) ease;
    color: var(--fg-subtle);
  }

  .chevron.open {
    transform: rotate(90deg);
  }

  .tool-icon {
    display: inline-flex;
    align-items: center;
    line-height: 1;
    flex-shrink: 0;
  }

  .tool-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 500;
  }

  .status-badge {
    flex-shrink: 0;
    font-size: 11px;
    line-height: 1;
    color: var(--fg-subtle);
    display: flex;
    align-items: center;
  }

  .status-badge.ok {
    color: var(--color-success);
  }

  .status-badge.error {
    color: var(--danger);
    font-weight: 700;
  }

  /* running 상태 스피너 */
  .mini-spinner {
    display: inline-block;
    width: 10px;
    height: 10px;
    border: 1.5px solid var(--accent-border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: tool-spin 0.7s linear infinite;
  }

  @keyframes tool-spin {
    to { transform: rotate(360deg); }
  }

  /* 결과 텍스트 영역 */
  .tool-detail {
    margin: 3px 0 3px 22px;
    padding: 6px 10px;
    border-left: 2px solid var(--border);
    font-size: 11.5px;
    font-family: var(--font-mono);
    color: var(--fg-muted);
    white-space: pre-wrap;
    word-break: break-all;
    line-height: 1.5;
    background: var(--bg-elevated);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    max-height: 200px;
    overflow-y: auto;
  }

  [data-status="error"] .tool-detail {
    border-left-color: var(--danger);
  }

  [data-status="ok"] .tool-detail {
    border-left-color: color-mix(in srgb, var(--color-success) 60%, transparent);
  }
</style>
