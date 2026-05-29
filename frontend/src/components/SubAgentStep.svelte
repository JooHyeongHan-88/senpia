<script>
  /**
   * 서브에이전트 실행 블록을 접을 수 있는 카드로 표시한다.
   *
   * - status==="running": 자동 펼침, 내부 세그먼트를 실시간으로 노출
   * - status==="done": 자동 접힘, 헤더에 요약 표시
   * - 사용자 클릭으로 언제든 토글 가능
   * - 내부 segments 는 <Segment> 를 재귀 호출하여 렌더한다 (동일 타임라인 구조)
   */

  import Segment from "./Segment.svelte";

  let { seg, isStreaming = false } = $props();

  // null = 자동(running 이면 펼침), true/false = 사용자 명시 토글
  let userExpanded = $state(null);

  let isRunning = $derived(seg.status === "running");
  let expanded = $derived(userExpanded !== null ? userExpanded : isRunning);

  function toggle() {
    userExpanded = !expanded;
  }

  let summaryPreview = $derived(
    seg.summary
      ? (seg.summary.length > 70 ? seg.summary.slice(0, 70) + "…" : seg.summary)
      : null
  );
</script>

<div class="subagent-step" data-status={seg.status}>
  <button
    class="subagent-header"
    type="button"
    onclick={toggle}
    aria-expanded={expanded}
  >
    <span class="chevron" class:open={expanded}>›</span>
    <span class="agent-icon">🤖</span>
    <span class="agent-name">{seg.agentId}</span>
    {#if isRunning}
      <span class="running-pill">
        <span class="mini-spinner" aria-hidden="true"></span>
        진행 중
      </span>
    {:else if summaryPreview}
      <span class="summary-preview">{summaryPreview}</span>
    {:else}
      <span class="done-pill">완료</span>
    {/if}
  </button>

  {#if expanded}
    <div class="subagent-body">
      <!-- 서브에이전트 SKILL 뱃지 -->
      {#if seg.activeSkills && seg.activeSkills.length > 0}
        <div class="agent-skill-bar">
          {#each seg.activeSkills as skill (skill)}
            <span class="agent-skill-chip">
              <span class="agent-skill-icon">◆</span>
              {skill}
            </span>
          {/each}
        </div>
      {/if}

      <!-- 내부 타임라인 — Segment 를 재귀 호출 -->
      {#each seg.segments as inner (inner.id)}
        <Segment seg={inner} {isStreaming} />
      {/each}

      <!-- 내부 세그먼트가 없고 실행 중일 때 thinking 표시 -->
      {#if seg.segments.length === 0 && isRunning}
        <div class="inner-thinking" aria-label="에이전트 실행 중">
          <span></span><span></span><span></span>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .subagent-step {
    margin: 6px 0;
    border-left: 2px solid var(--border);
    border-radius: 0 6px 6px 0;
    overflow: hidden;
  }

  [data-status="running"] {
    border-left-color: var(--accent);
  }

  [data-status="done"] {
    border-left-color: color-mix(in srgb, var(--color-success) 50%, var(--border));
  }

  .subagent-header {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    background: var(--bg-elevated);
    border: none;
    padding: 6px 10px;
    cursor: pointer;
    color: var(--fg-muted);
    font-size: 12px;
    text-align: left;
    transition: background 0.13s;
  }

  .subagent-header:hover {
    background: color-mix(in srgb, var(--border) 25%, var(--bg-elevated));
  }

  .chevron {
    display: inline-block;
    font-size: 14px;
    line-height: 1;
    flex-shrink: 0;
    transition: transform 0.18s ease;
    color: var(--fg-subtle);
  }

  .chevron.open {
    transform: rotate(90deg);
  }

  .agent-icon {
    font-size: 13px;
    line-height: 1;
    flex-shrink: 0;
  }

  .agent-name {
    font-weight: 600;
    font-size: 12px;
    color: var(--accent);
    flex-shrink: 0;
  }

  .running-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    font-weight: 600;
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
    border-radius: 10px;
    padding: 1px 7px 1px 5px;
  }

  .done-pill {
    font-size: 10px;
    font-weight: 500;
    color: var(--color-success);
    background: color-mix(in srgb, var(--color-success) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--color-success) 25%, transparent);
    border-radius: 10px;
    padding: 1px 7px;
  }

  .summary-preview {
    font-size: 11px;
    color: var(--fg-subtle);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
  }

  /* ── 서브에이전트 내부 ── */
  .subagent-body {
    padding: 8px 12px 8px 14px;
    background: var(--bg-elevated);
    display: flex;
    flex-direction: column;
  }

  /* ── SKILL 뱃지 ── */
  .agent-skill-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-bottom: 8px;
  }

  .agent-skill-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    font-weight: 600;
    color: var(--fg-muted);
    background: color-mix(in srgb, var(--border) 40%, transparent);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 2px 7px 2px 6px;
    white-space: nowrap;
    letter-spacing: 0.02em;
    animation: skill-pop 0.18s ease-out both;
  }

  .agent-skill-icon {
    font-size: 8px;
    line-height: 1;
    opacity: 0.65;
  }

  @keyframes skill-pop {
    from { opacity: 0; transform: scale(0.85) translateY(-2px); }
    to   { opacity: 1; transform: scale(1) translateY(0); }
  }

  /* ── 내부 thinking dots ── */
  .inner-thinking {
    display: inline-flex;
    gap: 4px;
    padding: 4px 0;
  }

  .inner-thinking span {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--fg-muted);
    animation: blink 1.2s infinite ease-in-out both;
  }

  .inner-thinking span:nth-child(2) { animation-delay: 0.15s; }
  .inner-thinking span:nth-child(3) { animation-delay: 0.3s; }

  @keyframes blink {
    0%, 80%, 100% { opacity: 0.25; transform: scale(0.85); }
    40%           { opacity: 1;    transform: scale(1); }
  }

  /* ── running 스피너 ── */
  .mini-spinner {
    display: inline-block;
    width: 8px;
    height: 8px;
    border: 1.5px solid color-mix(in srgb, var(--accent) 30%, transparent);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: tool-spin 0.7s linear infinite;
  }

  @keyframes tool-spin {
    to { transform: rotate(360deg); }
  }
</style>
