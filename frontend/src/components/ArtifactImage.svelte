<script>
  import { onMount, onDestroy } from "svelte";
  import { openLightbox } from "../lib/artifactActions.svelte.js";

  const PAGE_SIZE = 6;

  let { payload } = $props();

  // payload.items 는 list. 백워드 안전망: 잘못된 형태가 들어와도 빈 list 로 처리.
  let items = $derived(Array.isArray(payload?.items) ? payload.items : []);
  let total = $derived(items.length);

  // 가시 개수 — IntersectionObserver 가 sentinel 진입 시 +PAGE_SIZE.
  // total 은 $derived 이라 초기값 캡쳐 경고가 나오므로 항상 PAGE_SIZE 로 시작하고
  // 아래 $effect 에서 items 길이에 맞춰 클램프한다.
  let visibleCount = $state(PAGE_SIZE);
  let visible = $derived(items.slice(0, Math.min(visibleCount, total)));

  // 로드 실패한 항목의 인덱스 집합 — 개별 카드에서 placeholder 표시.
  let failedSet = $state(new Set());

  // items 가 바뀌면(다른 칩으로 전환) 가시 개수 리셋.
  $effect(() => {
    payload;
    visibleCount = Math.min(PAGE_SIZE, total);
    failedSet = new Set();
  });

  let sentinelEl = $state(null);
  let observer = null;

  function ensureObserver() {
    if (observer || !sentinelEl) return;
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && visibleCount < total) {
            visibleCount = Math.min(visibleCount + PAGE_SIZE, total);
          }
        }
      },
      { rootMargin: "120px" },
    );
    observer.observe(sentinelEl);
  }

  // sentinelEl 가 마운트되면 observer 부착, 사라지면 해제.
  $effect(() => {
    if (sentinelEl) ensureObserver();
    return () => {
      observer?.disconnect();
      observer = null;
    };
  });

  onMount(() => {
    ensureObserver();
  });

  onDestroy(() => {
    observer?.disconnect();
  });

  function handleImageError(idx) {
    failedSet = new Set([...failedSet, idx]);
  }

  function handleCardClick(idx) {
    openLightbox("image", items, idx);
  }
</script>

<div class="artifact-image-wrap">
  <div class="toolbar">
    <span class="img-label">
      {#if total === 1}
        {items[0]?.alt || items[0]?.caption || "이미지"}
      {:else}
        이미지 갤러리
      {/if}
    </span>
    {#if total > 1}
      <span class="counter" aria-live="polite">
        {visibleCount} / {total}장 표시
      </span>
    {/if}
  </div>

  {#if total === 0}
    <div class="empty">표시할 이미지가 없습니다.</div>
  {:else}
    <div class="scroll-area">
      <div class="gallery">
        {#each visible as item, idx (idx)}
          <figure class="card">
            <button
              type="button"
              class="card-btn"
              onclick={() => handleCardClick(idx)}
              aria-label={item.alt || item.caption || `이미지 ${idx + 1}`}
            >
              {#if failedSet.has(idx)}
                <div class="card-error">
                  <span class="error-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <rect x="3" y="3" width="18" height="18" rx="2" />
                      <circle cx="9" cy="9" r="2" />
                      <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
                    </svg>
                  </span>
                  <span>이미지를 불러올 수 없습니다.</span>
                  <small>{item.src}</small>
                </div>
              {:else}
                <img
                  src={item.src}
                  alt={item.alt || ""}
                  loading="lazy"
                  onerror={() => handleImageError(idx)}
                />
              {/if}
            </button>
            {#if item.caption}
              <figcaption class="caption">{item.caption}</figcaption>
            {/if}
          </figure>
        {/each}

        <!-- 무한 스크롤 sentinel — 가시 영역에 더 로드할 항목이 남았을 때만 노출 -->
        {#if visibleCount < total}
          <div bind:this={sentinelEl} class="sentinel" aria-hidden="true">
            <span class="sentinel-dot"></span>
            <span class="sentinel-dot"></span>
            <span class="sentinel-dot"></span>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .artifact-image-wrap {
    display: flex;
    flex-direction: column;
    height: 100%;
    gap: 0;
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
  }

  .img-label {
    font-size: 12px;
    color: var(--fg-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 60%;
  }

  .counter {
    font-size: 11px;
    color: var(--fg-muted);
    font-variant-numeric: tabular-nums;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 2px 8px;
    flex-shrink: 0;
  }

  .scroll-area {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
  }

  .gallery {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    padding: 16px;
    max-width: 720px;
    margin: 0 auto;
  }

  .card {
    margin: 0;
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
  }

  .card-btn {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 0;
    cursor: zoom-in;
    width: 100%;
    overflow: hidden;
    transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
    line-height: 0;
  }

  .card-btn:hover {
    border-color: color-mix(in srgb, var(--accent) 50%, var(--border));
    box-shadow: var(--shadow-md);
  }

  .card-btn img {
    display: block;
    width: 100%;
    height: auto;
    max-height: 460px;
    object-fit: contain;
    background: var(--bg);
  }

  .caption {
    font-size: 12px;
    color: var(--fg-muted);
    text-align: center;
    margin: 0;
    line-height: 1.5;
    max-width: 100%;
  }

  .card-error {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 32px 16px;
    color: var(--danger);
    font-size: 12px;
    line-height: 1.5;
  }

  .card-error .error-icon {
    display: inline-flex;
  }

  .card-error small {
    font-size: 10px;
    color: var(--fg-muted);
    word-break: break-all;
    text-align: center;
  }

  .empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--fg-muted);
    font-size: 13px;
  }

  .sentinel {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 16px;
    width: 100%;
  }

  .sentinel-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--fg-muted);
    animation: pulse 1.2s infinite ease-in-out both;
  }

  .sentinel-dot:nth-child(2) {
    animation-delay: 0.15s;
  }

  .sentinel-dot:nth-child(3) {
    animation-delay: 0.3s;
  }

  @keyframes pulse {
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
</style>
