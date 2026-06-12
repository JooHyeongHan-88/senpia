<script>
  /**
   * 에이전트 플래너의 작업 목록(TodoItem[])을 접을 수 있는 체크리스트로 표시한다.
   *
   * 각 항목은 status 에 따라 아이콘과 색상이 결정된다:
   *   pending   → 빈 원 (회색)
   *   running   → CSS 스피너 (accent) + 자동 펼침
   *   completed → 체크마크 (success)
   *   failed    → ✗ (danger)
   *   skipped   → 대시 (muted)
   *
   * 항목별 expand 규칙:
   *   - 기본 접힘
   *   - running 항목은 자동 펼침 (result_summary 도착 대기)
   *   - 사용자 클릭으로 언제든 토글 가능
   *   - result_summary 가 있으면 펼쳤을 때 표시
   *   토글 상태는 task_id 키 기반 Map 으로 보존 (배열 재생성에 안정)
   */

  import SkillCompleteBadge from "./SkillCompleteBadge.svelte";

  let { todos = [], complete = null } = $props();

  // ── 전체 목록 expand 상태 ──
  // null = 자동(미완료 항목 있으면 펼침, 전부 terminal 이면 접힘), true/false = 사용자 명시 토글
  let userExpanded = $state(null);

  // ── 항목별 expand 상태 (task_id → boolean | undefined) ──
  // undefined = 자동(running → 펼침, 나머지 → 접힘)
  let itemExpanded = $state({});

  let completedCount = $derived(todos.filter((t) => t.status === "completed").length);
  let failedCount = $derived(todos.filter((t) => t.status === "failed").length);

  // 미완료 항목이 있으면 목록 자동 펼침, 전부 terminal 이면 접힘 (Claude Desktop 식)
  let hasActive = $derived(todos.some((t) => t.status === "pending" || t.status === "running"));
  let listExpanded = $derived(userExpanded !== null ? userExpanded : hasActive);

  function toggleList() {
    userExpanded = !listExpanded;
  }

  /**
   * 항목 개별 expand 여부 결정.
   * 사용자가 명시 토글했으면 그 값을, 아니면 running 항목을 자동 펼침.
   */
  function isItemExpanded(item) {
    const val = itemExpanded[item.task_id];
    if (val !== undefined) return val;
    return item.status === "running";
  }

  function toggleItem(taskId) {
    const item = todos.find((t) => t.task_id === taskId);
    if (!item) return;
    itemExpanded = { ...itemExpanded, [taskId]: !isItemExpanded(item) };
  }

  /**
   * 항목에 펼쳤을 때 보여줄 내용이 있는지 여부.
   * result_summary 가 있거나 running 상태이면 클릭 가능하게 한다.
   */
  function itemHasDetail(item) {
    return !!item.result_summary || item.status === "running";
  }

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
    onclick={toggleList}
    aria-expanded={listExpanded}
  >
    <span class="chevron" class:open={listExpanded}>›</span>
    <span class="label">작업 진행</span>
    <span class="count">
      {completedCount}/{todos.length} 완료{failedCount > 0 ? ` · ${failedCount} 실패` : ""}
    </span>
  </button>

  {#if listExpanded}
    <ul class="todo-list" role="list">
      {#each todos as item (item.task_id)}
        {@const hasDetail = itemHasDetail(item)}
        {@const itemOpen = isItemExpanded(item)}

        <li class="todo-item" data-status={item.status}>
          <!-- 상태 아이콘 -->
          <span class="icon-wrap" aria-label={item.status}>
            {#if item.status === "running"}
              <span class="spinner" aria-hidden="true"></span>
            {:else}
              <span class="icon">{statusIcon(item.status)}</span>
            {/if}
          </span>

          <!-- 설명 + 세부 내역 -->
          <span class="item-body">
            {#if hasDetail}
              <!-- 클릭으로 세부 내역 expand -->
              <button
                class="desc-btn"
                type="button"
                onclick={() => toggleItem(item.task_id)}
                aria-expanded={itemOpen}
              >
                <span class="item-chevron" class:open={itemOpen}>›</span>
                <span class="desc">{item.description}</span>
              </button>
              {#if itemOpen && item.result_summary}
                <span class="summary">{item.result_summary}</span>
              {/if}
            {:else}
              <!-- 세부 내역 없음 — 일반 텍스트 -->
              <span class="desc plain">{item.description}</span>
            {/if}
          </span>
        </li>
      {/each}
    </ul>
  {/if}

  <!-- skill_complete 통계 배지 -->
  {#if complete}
    <SkillCompleteBadge data={complete} />
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
    border-radius: var(--radius-sm);
  }

  .todo-header:hover {
    color: var(--fg);
  }

  .chevron {
    display: inline-block;
    font-size: 14px;
    line-height: 1;
    transition: transform var(--dur-slow) ease;
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
    gap: 3px;
  }

  .todo-item {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 13px;
    line-height: 1.5;
  }

  /* ── 상태 아이콘 ── */
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

  [data-status="pending"] .icon::before {
    content: "○";
    color: var(--fg-subtle);
  }

  [data-status="pending"] .icon {
    color: var(--fg-subtle);
  }

  .spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid var(--accent-border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  [data-status="completed"] .icon {
    color: var(--color-success);
    font-weight: 700;
  }

  [data-status="completed"] .desc {
    color: var(--fg-muted);
  }

  [data-status="failed"] .icon {
    color: var(--danger);
    font-weight: 700;
  }

  [data-status="failed"] .desc {
    color: var(--fg-muted);
  }

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
    min-width: 0;
    flex: 1;
  }

  /* 세부 내역 있을 때 클릭 가능한 설명 버튼 */
  .desc-btn {
    display: inline-flex;
    align-items: baseline;
    gap: 3px;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    color: inherit;
    font-size: inherit;
    font-family: inherit;
    line-height: inherit;
    text-align: left;
  }

  .desc-btn:hover .desc {
    color: var(--fg);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .item-chevron {
    display: inline-block;
    font-size: 11px;
    line-height: 1;
    color: var(--fg-subtle);
    transition: transform var(--dur-fast) ease;
    flex-shrink: 0;
    margin-top: 2px;
  }

  .item-chevron.open {
    transform: rotate(90deg);
  }

  .desc {
    color: var(--fg);
    transition: color var(--dur-fast);
  }

  /* 클릭 불가 일반 텍스트 설명 */
  .plain {
    display: inline-block;
  }

  .summary {
    font-size: 11.5px;
    color: var(--fg-subtle);
    padding-left: 14px; /* item-chevron 너비만큼 들여쓰기 */
    white-space: pre-wrap;
    word-break: break-word;
  }
</style>
