<script>
  import ChartCell from "./ChartCell.svelte";
  import { openLightbox } from "../lib/artifactActions.svelte.js";

  const PAGE_SIZE = 6;

  let { payload } = $props();

  let items = $derived(Array.isArray(payload?.items) ? payload.items : []);
  let total = $derived(items.length);
  let totalPages = $derived(Math.max(1, Math.ceil(total / PAGE_SIZE)));

  let page = $state(1);

  // items 가 바뀌면(다른 칩) 1페이지로 리셋.
  $effect(() => {
    payload;
    page = 1;
  });

  // 페이지 변경 시 범위 클램프 — 외부 변화에 안전망.
  $effect(() => {
    if (page > totalPages) page = totalPages;
    if (page < 1) page = 1;
  });

  let visibleItems = $derived(
    items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
  );

  function goPrev() {
    if (page > 1) page -= 1;
  }

  function goNext() {
    if (page < totalPages) page += 1;
  }

  function openCellInLightbox(globalIndex) {
    openLightbox("chart", items, globalIndex);
  }
</script>

<div class="artifact-chart-wrap">
  <div class="toolbar">
    <span class="chart-label">
      {#if total === 1}
        {items[0]?.title || "차트"}
      {:else}
        차트 그리드
      {/if}
    </span>
    {#if total > 1}
      <div class="pager" role="group" aria-label="페이지 네비게이션">
        <button
          type="button"
          class="page-btn"
          onclick={goPrev}
          disabled={page <= 1}
          aria-label="이전 페이지"
        >
          ‹
        </button>
        <span class="page-counter">페이지 {page} / {totalPages}</span>
        <button
          type="button"
          class="page-btn"
          onclick={goNext}
          disabled={page >= totalPages}
          aria-label="다음 페이지"
        >
          ›
        </button>
      </div>
    {/if}
  </div>

  {#if total === 0}
    <div class="empty">표시할 차트가 없습니다.</div>
  {:else if total === 1}
    <!-- 단일 차트: 전체 영역 사용 + 클릭 가능 -->
    <div class="single-area">
      {#key items[0]}
        <ChartCell
          item={items[0]}
          embedded={false}
          onclick={() => openCellInLightbox(0)}
        />
      {/key}
    </div>
  {:else}
    <!-- 다중 차트: 반응형 그리드. {#key} 로 페이지 전환 시 강제 remount → 인스턴스 dispose 보장 -->
    {#key page}
      <div class="grid">
        {#each visibleItems as item, idx (idx)}
          {@const globalIndex = (page - 1) * PAGE_SIZE + idx}
          <ChartCell
            {item}
            embedded={true}
            onclick={() => openCellInLightbox(globalIndex)}
          />
        {/each}
      </div>
    {/key}
  {/if}
</div>

<style>
  .artifact-chart-wrap {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 14px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-elevated);
    flex-shrink: 0;
    gap: 8px;
  }

  .chart-label {
    font-size: 12px;
    color: var(--fg-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }

  .pager {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex-shrink: 0;
  }

  .page-btn {
    width: 26px;
    height: 26px;
    border: 1px solid var(--border);
    background: var(--bg);
    border-radius: var(--radius-sm);
    color: var(--fg);
    cursor: pointer;
    font-size: 16px;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: background 0.12s;
  }

  .page-btn:hover:not(:disabled) {
    background: var(--bg-hover);
  }

  .page-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .page-counter {
    font-size: 11px;
    color: var(--fg-muted);
    font-variant-numeric: tabular-nums;
    padding: 0 6px;
  }

  .single-area {
    flex: 1;
    padding: 8px;
    box-sizing: border-box;
    min-height: 0;
  }

  .grid {
    flex: 1;
    overflow-y: auto;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
    padding: 12px;
    align-content: start;
  }

  .empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--fg-muted);
    font-size: 13px;
  }
</style>
