<script>
  /**
   * 에이전트 플래너의 작업 목록(TodoItem[])을 접을 수 있는 체크리스트로 표시한다.
   *
   * 각 항목은 status 에 따라 아이콘과 색상이 결정된다:
   *   pending  → 빈 원 (회색)
   *   running  → CSS 스피너 (accent)
   *   completed → 체크마크 (success)
   *   failed   → ✗ (danger)
   *   skipped  → 대시 (muted)
   *
   * 서브에이전트 확장 대비: 현재는 flat 배열이지만 TodoItem 에 children 필드가
   * 추가되면 재귀 렌더링으로 전환 가능한 구조로 작성한다.
   */

  let { todos = [] } = $props();

  let expanded = $state(true);

  let completedCount = $derived(
    todos.filter((t) => t.status === "completed").length
  );
  let failedCount = $derived(
    todos.filter((t) => t.status === "failed").length
  );

  /**
   * 상태별 아이콘 텍스트 반환.
   * @param {string} status
   * @returns {string}
   */
  function statusIcon(status) {
    switch (status) {
      case "completed": return "✓";
      case "failed":    return "✗";
      case "skipped":   return "—";
      default:          return "";
    }
  }
</script>

<div class="todo-wrap">
  <button
    class="todo-header"
    type="button"
    onclick={() => (expanded = !expanded)}
    aria-expanded={expanded}
  >
    <span class="chevron" class:open={expanded}>›</span>
    <span class="label">작업 진행</span>
    <span class="count">
      {completedCount}/{todos.length} 완료{failedCount > 0 ? ` · ${failedCount} 실패` : ""}
    </span>
  </button>

  {#if expanded}
    <ul class="todo-list" role="list">
      {#each todos as item (item.task_id)}
        <li class="todo-item" data-status={item.status}>
          <!-- 상태 아이콘 -->
          <span class="icon-wrap" aria-label={item.status}>
            {#if item.status === "running"}
              <span class="spinner" aria-hidden="true"></span>
            {:else}
              <span class="icon">{statusIcon(item.status)}</span>
            {/if}
          </span>

          <!-- 설명 + 요약 -->
          <span class="item-body">
            <span class="desc">{item.description}</span>
            {#if item.result_summary && (item.status === "completed" || item.status === "failed")}
              <span class="summary">{item.result_summary}</span>
            {/if}
          </span>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .todo-wrap {
    margin-bottom: 10px;
    border-left: 3px solid var(--accent);
    padding-left: 10px;
  }

  .todo-header {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: none;
    border: none;
    padding: 2px 0;
    cursor: pointer;
    color: var(--fg-muted);
    font-size: 12px;
    font-weight: 500;
    border-radius: 4px;
  }

  .todo-header:hover {
    color: var(--fg);
  }

  .chevron {
    display: inline-block;
    font-size: 14px;
    line-height: 1;
    transition: transform 0.18s ease;
  }

  .chevron.open {
    transform: rotate(90deg);
  }

  .label {
    font-size: 12px;
  }

  .count {
    font-size: 11px;
    color: var(--fg-subtle);
    font-weight: 400;
  }

  /* ── 항목 목록 ── */
  .todo-list {
    list-style: none;
    margin: 6px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .todo-item {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 13px;
    line-height: 1.5;
  }

  /* ── 상태별 스타일 ── */
  .icon-wrap {
    flex-shrink: 0;
    width: 16px;
    height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 2px;
  }

  .icon {
    font-size: 12px;
    line-height: 1;
  }

  /* pending: 빈 원 */
  [data-status="pending"] .icon::before {
    content: "○";
    color: var(--fg-subtle);
  }

  [data-status="pending"] .icon {
    color: var(--fg-subtle);
  }

  /* running: accent 스피너 */
  .spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid color-mix(in srgb, var(--accent) 25%, transparent);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  /* completed: 초록 체크 */
  [data-status="completed"] .icon {
    color: var(--color-success);
    font-weight: 700;
  }

  [data-status="completed"] .desc {
    color: var(--fg-muted);
  }

  /* failed: 빨간 ✗ */
  [data-status="failed"] .icon {
    color: var(--danger);
    font-weight: 700;
  }

  [data-status="failed"] .desc {
    color: var(--fg-muted);
  }

  /* skipped: muted 대시 */
  [data-status="skipped"] .icon {
    color: var(--fg-subtle);
  }

  [data-status="skipped"] .desc {
    color: var(--fg-subtle);
    text-decoration: line-through;
  }

  /* ── 항목 본문 ── */
  .item-body {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .desc {
    color: var(--fg);
    transition: color 0.2s;
  }

  .summary {
    font-size: 11px;
    color: var(--fg-subtle);
  }
</style>
