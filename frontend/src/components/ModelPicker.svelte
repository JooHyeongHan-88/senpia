<script>
  import { ui } from "../lib/state.svelte.js";
  import {
    openModelPicker,
    closeModelPicker,
    loadModels,
    selectModel,
  } from "../lib/settingsActions.svelte.js";

  let searchQuery = $state("");

  let providerLabel = $derived(
    ui.providers.find((p) => p.id === ui.currentProvider)?.label ?? ui.currentProvider,
  );

  let modelList = $derived(
    (ui.modelListByProvider[ui.currentProvider]?.models ?? []).filter((m) =>
      m.toLowerCase().includes(searchQuery.toLowerCase()),
    ),
  );

  let isLoading = $derived(
    ui.modelListByProvider[ui.currentProvider]?.loading ?? false,
  );

  let showSearch = $derived(
    (ui.modelListByProvider[ui.currentProvider]?.models?.length ?? 0) > 5,
  );

  function onKeydown(e) {
    if (e.key === "Escape") closeModelPicker();
  }

  function onRefresh() {
    loadModels(ui.currentProvider, { force: true });
  }
</script>

<svelte:window onkeydown={onKeydown} />

<!-- 모델 Picker 버튼 -->
<div class="picker-wrapper">
  <button
    class="picker-btn"
    onclick={openModelPicker}
    title="모델 변경"
    aria-expanded={ui.modelPickerOpen}
    aria-haspopup="listbox"
  >
    <span class="provider-chip" data-provider={ui.currentProvider}>
      {providerLabel}
    </span>
    <span class="model-name">
      {ui.currentModel || "모델 미설정"}
    </span>
    <svg class="chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="m18 15-6-6-6 6" />
    </svg>
  </button>

  <!-- Dropup 팝오버 -->
  {#if ui.modelPickerOpen}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="backdrop" onclick={closeModelPicker}></div>

    <div class="popup" role="listbox" aria-label="모델 선택">
      <div class="popup-header">
        <span class="popup-title">{providerLabel} 모델</span>
        <button class="refresh-btn" onclick={onRefresh} title="목록 새로고침" disabled={isLoading}>
          <svg
            class:spinning={isLoading}
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
            <path d="M21 3v5h-5" />
            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
            <path d="M8 16H3v5" />
          </svg>
        </button>
      </div>

      {#if showSearch}
        <div class="search-wrap">
          <!-- svelte-ignore a11y_autofocus -->
        <input
            class="search-input"
            type="text"
            placeholder="모델 검색..."
            bind:value={searchQuery}
            autofocus
          />
        </div>
      {/if}

      <div class="model-list">
        {#if isLoading && modelList.length === 0}
          <div class="list-empty">
            <span class="spinner" aria-hidden="true"></span>
            불러오는 중…
          </div>
        {:else if modelList.length === 0}
          <div class="list-empty">
            {searchQuery ? "검색 결과 없음" : "모델 없음 — 설정에서 API 키를 확인하세요"}
          </div>
        {:else}
          {#each modelList as m (m)}
            <button
              class="model-item"
              class:active={m === ui.currentModel}
              role="option"
              aria-selected={m === ui.currentModel}
              onclick={() => selectModel(m)}
            >
              <span class="model-item-name">{m}</span>
              {#if m === ui.currentModel}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
              {/if}
            </button>
          {/each}
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .picker-wrapper {
    position: relative;
    padding: 6px 12px 8px;
    border-top: 1px solid var(--border);
  }

  /* ── 트리거 버튼 ── */
  .picker-btn {
    display: flex;
    align-items: center;
    gap: 7px;
    width: 100%;
    padding: 7px 10px;
    border-radius: 8px;
    color: var(--fg);
    background: transparent;
    font-size: 12.5px;
    text-align: left;
    transition: background 0.1s;
    min-width: 0;
  }

  .picker-btn:hover {
    background: var(--bg-hover);
  }

  .provider-chip {
    flex-shrink: 0;
    font-size: 10.5px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    background: var(--bg-active);
    color: var(--fg-muted);
  }

  .provider-chip[data-provider="dtgpt"] {
    background: color-mix(in srgb, var(--accent) 15%, transparent);
    color: var(--accent);
  }

  .provider-chip[data-provider="openai_compatible"] {
    background: color-mix(in srgb, var(--color-success) 15%, transparent);
    color: var(--color-success);
  }

  .model-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--fg);
  }

  .chevron {
    flex-shrink: 0;
    color: var(--fg-subtle);
    transition: transform 0.15s;
  }

  .picker-btn[aria-expanded="true"] .chevron {
    transform: rotate(180deg);
  }

  /* ── Popup ── */
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 19;
  }

  .popup {
    position: absolute;
    bottom: calc(100% + 4px);
    left: 12px;
    right: 12px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-md);
    z-index: 20;
    display: flex;
    flex-direction: column;
    max-height: 320px;
    overflow: hidden;
    animation: popup-in 0.12s ease;
  }

  @keyframes popup-in {
    from {
      opacity: 0;
      transform: translateY(6px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* ── Popup 헤더 ── */
  .popup-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px 8px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .popup-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fg-subtle);
  }

  .refresh-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 5px;
    color: var(--fg-muted);
  }

  .refresh-btn:hover:not(:disabled) {
    background: var(--bg-hover);
    color: var(--fg);
  }

  .refresh-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }

  /* ── 검색 ── */
  .search-wrap {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .search-input {
    width: 100%;
    padding: 6px 8px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--bg-elevated);
    color: var(--fg);
    font-size: 12.5px;
    outline: none;
  }

  .search-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 15%, transparent);
  }

  /* ── 모델 리스트 ── */
  .model-list {
    overflow-y: auto;
    padding: 4px 0;
  }

  .model-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    width: 100%;
    padding: 7px 12px;
    text-align: left;
    font-size: 12.5px;
    color: var(--fg);
    transition: background 0.08s;
  }

  .model-item:hover {
    background: var(--bg-hover);
  }

  .model-item.active {
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  .model-item-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-mono);
  }

  .list-empty {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 14px 12px;
    font-size: 12px;
    color: var(--fg-subtle);
  }

  /* ── 스피너 ── */
  .spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid var(--border-strong);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    flex-shrink: 0;
  }

  .spinning {
    animation: spin 0.7s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
