<script>
  import { onMount, onDestroy } from "svelte";
  import { ui } from "../lib/state.svelte.js";
  import {
    closeLightbox,
    lightboxNext,
    lightboxPrev,
  } from "../lib/artifactActions.svelte.js";
  import ChartCell from "./ChartCell.svelte";

  const MIN_WIDTH = 320;
  const MIN_HEIGHT = 240;
  // 뷰포트 비율 한도 — 모달이 화면 밖으로 넘치지 않도록.
  const MAX_VW_RATIO = 0.95;
  const MAX_VH_RATIO = 0.95;
  const INITIAL_VW_RATIO = 0.8;
  const INITIAL_VH_RATIO = 0.8;

  // 사용자 드래그로 변경되는 모달 크기. 초기값은 마운트 후 setInitialSize() 가 채운다.
  let width = $state(720);
  let height = $state(560);

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function setInitialSize() {
    width = Math.round(window.innerWidth * INITIAL_VW_RATIO);
    height = Math.round(window.innerHeight * INITIAL_VH_RATIO);
  }

  // 라이트박스가 열릴 때마다 초기 크기로 리셋 (이전 세션 크기 잔존 방지).
  $effect(() => {
    if (ui.lightbox.open) setInitialSize();
  });

  // ── 드래그 리사이즈 ────────────────────────────────────────────────
  let resizing = $state(false);
  let dragStart = { x: 0, y: 0, w: 0, h: 0 };

  function onResizePointerDown(e) {
    if (e.button !== 0) return;
    resizing = true;
    dragStart = { x: e.clientX, y: e.clientY, w: width, h: height };
    e.currentTarget.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  }

  function onResizePointerMove(e) {
    if (!resizing) return;
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    // 창이 flex-center 로 중앙 배치되므로 핸들(우하단)은 마우스의 절반 속도로 이동.
    // 핸들이 마우스를 따라오려면 delta 를 2배 적용해야 한다.
    width = clamp(
      dragStart.w + dx * 2,
      MIN_WIDTH,
      Math.floor(window.innerWidth * MAX_VW_RATIO),
    );
    height = clamp(
      dragStart.h + dy * 2,
      MIN_HEIGHT,
      Math.floor(window.innerHeight * MAX_VH_RATIO),
    );
  }

  function onResizePointerUp(e) {
    if (!resizing) return;
    resizing = false;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  }

  // ── 키보드 ────────────────────────────────────────────────────────
  function onKeydown(e) {
    if (!ui.lightbox.open) return;
    if (e.key === "Escape") {
      e.preventDefault();
      closeLightbox();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      lightboxPrev();
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      lightboxNext();
    }
  }

  onMount(() => {
    window.addEventListener("keydown", onKeydown);
  });

  onDestroy(() => {
    window.removeEventListener("keydown", onKeydown);
  });

  function onBackdropClick(e) {
    if (e.target === e.currentTarget) closeLightbox();
  }

  // backdrop 영역에서 키보드 사용자도 Escape/Enter 로 닫을 수 있도록 명시 핸들러.
  // window 레벨 keydown 도 동작하지만 svelte a11y 룰을 만족시키기 위해 부착.
  function onBackdropKeydown(e) {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      closeLightbox();
    }
  }

  // 현재 표시 항목.
  let current = $derived(ui.lightbox.items[ui.lightbox.index] ?? null);
  let total = $derived(ui.lightbox.items.length);
  let hasMultiple = $derived(total > 1);
</script>

{#if ui.lightbox.open && current}
  <div
    class="lightbox-backdrop"
    class:resizing
    role="dialog"
    aria-modal="true"
    aria-label="아티팩트 확대 보기"
    tabindex="-1"
    onclick={onBackdropClick}
    onkeydown={onBackdropKeydown}
  >
    <div
      class="lightbox-window"
      style="width: {width}px; height: {height}px"
    >
      <header class="lightbox-header">
        <span class="lightbox-title">
          {#if ui.lightbox.kind === "image"}
            {current.alt || current.caption || "이미지"}
          {:else if ui.lightbox.kind === "chart"}
            {current.title || "차트"}
          {/if}
        </span>
        <div class="header-actions">
          {#if hasMultiple}
            <span class="position-counter" aria-live="polite">
              {ui.lightbox.index + 1} / {total}
            </span>
          {/if}
          <button
            type="button"
            class="icon-btn"
            onclick={closeLightbox}
            aria-label="닫기"
            title="닫기 (Esc)"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            >
              <path d="M3 3l10 10M13 3 3 13" />
            </svg>
          </button>
        </div>
      </header>

      <div class="lightbox-body">
        {#if ui.lightbox.kind === "image"}
          {#key ui.lightbox.index}
            <img
              src={current.src}
              alt={current.alt || ""}
              class="lightbox-image"
            />
          {/key}
        {:else if ui.lightbox.kind === "chart"}
          {#key ui.lightbox.index}
            <div class="lightbox-chart">
              <ChartCell item={current} embedded={false} />
            </div>
          {/key}
        {/if}

        {#if hasMultiple}
          <button
            type="button"
            class="nav-btn nav-prev"
            onclick={lightboxPrev}
            aria-label="이전 항목"
            title="이전 (←)"
          >
            ‹
          </button>
          <button
            type="button"
            class="nav-btn nav-next"
            onclick={lightboxNext}
            aria-label="다음 항목"
            title="다음 (→)"
          >
            ›
          </button>
        {/if}
      </div>

      {#if ui.lightbox.kind === "image" && current.caption}
        <footer class="lightbox-caption">{current.caption}</footer>
      {/if}

      <!-- drag-to-resize 핸들 (우하단). pointer 이벤트로 폭·높이 직접 조정. -->
      <div
        class="resize-handle"
        role="separator"
        aria-orientation="horizontal"
        aria-label="모달 크기 조절"
        onpointerdown={onResizePointerDown}
        onpointermove={onResizePointerMove}
        onpointerup={onResizePointerUp}
        onpointercancel={onResizePointerUp}
      >
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          <path d="M2 12 L12 2 M6 12 L12 6 M10 12 L12 10" stroke="currentColor" stroke-width="1.5" fill="none" />
        </svg>
      </div>
    </div>
  </div>
{/if}

<style>
  .lightbox-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    animation: fade-in 0.15s ease-out;
  }

  .lightbox-backdrop.resizing {
    cursor: nwse-resize;
    user-select: none;
  }

  @keyframes fade-in {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .lightbox-window {
    position: relative;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-width: 320px;
    min-height: 240px;
    max-width: 95vw;
    max-height: 95vh;
  }

  .lightbox-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-elevated);
    flex-shrink: 0;
  }

  .lightbox-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--fg);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }

  .position-counter {
    font-size: 11px;
    color: var(--fg-muted);
    font-variant-numeric: tabular-nums;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 2px 8px;
  }

  .icon-btn {
    width: 26px;
    height: 26px;
    border: none;
    background: transparent;
    color: var(--fg-muted);
    cursor: pointer;
    border-radius: var(--radius-sm);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: background 0.12s, color 0.12s;
  }

  .icon-btn:hover {
    background: var(--bg-hover);
    color: var(--fg);
  }

  .lightbox-body {
    position: relative;
    flex: 1;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    background: var(--bg);
  }

  .lightbox-image {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    display: block;
  }

  .lightbox-chart {
    width: 100%;
    height: 100%;
    padding: 8px;
    box-sizing: border-box;
  }

  .lightbox-caption {
    padding: 8px 14px;
    border-top: 1px solid var(--border);
    background: var(--bg-elevated);
    font-size: 12px;
    color: var(--fg-muted);
    text-align: center;
    flex-shrink: 0;
  }

  /* 좌/우 네비게이션 버튼 — body 위에 절대 위치 */
  .nav-btn {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 38px;
    height: 38px;
    border-radius: 50%;
    border: 1px solid var(--border);
    background: color-mix(in srgb, var(--bg) 85%, transparent);
    backdrop-filter: blur(4px);
    color: var(--fg);
    cursor: pointer;
    font-size: 22px;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: background 0.12s, transform 0.12s;
  }

  .nav-btn:hover {
    background: var(--bg);
    transform: translateY(-50%) scale(1.05);
  }

  .nav-prev {
    left: 12px;
  }

  .nav-next {
    right: 12px;
  }

  .resize-handle {
    position: absolute;
    bottom: 0;
    right: 0;
    width: 18px;
    height: 18px;
    cursor: nwse-resize;
    display: flex;
    align-items: flex-end;
    justify-content: flex-end;
    color: var(--fg-muted);
    touch-action: none;
    user-select: none;
    z-index: 2;
  }

  .resize-handle:hover {
    color: var(--accent);
  }
</style>
