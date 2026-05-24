<script>
  import { renderMarkdown } from "../lib/markdown.js";

  let { message } = $props();

  let isUser = $derived(message.role === "user");
  let html = $derived(isUser ? "" : renderMarkdown(message.content));
</script>

<div class="row" class:user={isUser}>
  <div class="bubble" class:user={isUser}>
    {#if isUser}
      <!-- 슬래시 커맨드로 부착한 skill 을 대화창 안에서도 표시 -->
      {#if message.appliedSkills && message.appliedSkills.length > 0}
        <div class="skill-bar user-skills">
          {#each message.appliedSkills as skill (skill)}
            <span class="skill-chip user-chip">
              <span class="skill-icon">✦</span>
              {skill}
            </span>
          {/each}
        </div>
      {/if}
      {#if message.content}
        <div class="user-content">{message.content}</div>
      {/if}
    {:else}
      <!-- 활성 스킬 뱃지 — skill_active 이벤트 수신 시 표시 -->
      {#if message.activeSkills && message.activeSkills.length > 0}
        <div class="skill-bar">
          {#each message.activeSkills as skill (skill)}
            <span class="skill-chip">
              <span class="skill-icon">✦</span>
              {skill}
            </span>
          {/each}
        </div>
      {/if}

      {#if !message.content && !message.toolStatus}
        <div class="thinking" aria-label="응답 생성 중">
          <span></span><span></span><span></span>
        </div>
      {:else}
        <div class="markdown">{@html html}</div>
      {/if}
      {#if message.toolStatus}
        <div class="tool-status">{message.toolStatus}</div>
      {/if}
    {/if}
  </div>
</div>

<style>
  .row {
    display: flex;
    justify-content: flex-start;
    margin: 18px 0;
  }

  .row.user {
    justify-content: flex-end;
  }

  .bubble {
    max-width: 100%;
  }

  .bubble.user {
    max-width: 78%;
    background: var(--user-bubble);
    color: var(--fg);
    padding: 10px 14px;
    border-radius: 16px 16px 4px 16px;
  }

  .user-content {
    white-space: pre-wrap;
    word-wrap: break-word;
    font-size: 14px;
    line-height: 1.6;
  }

  /* ── 스킬 뱃지 바 ── */
  .skill-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
  }

  /* 사용자 버블 안 skill bar — 콘텐츠 위에 표시 */
  .user-skills {
    margin-bottom: 6px;
  }

  /* 사용자 버블 안 chip — accent 대신 반투명 흰색 계열로 대비 확보 */
  .user-chip {
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 15%, transparent);
    border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  }

  .skill-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    font-weight: 500;
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent) 25%, transparent);
    border-radius: 20px;
    padding: 2px 9px 2px 7px;
    line-height: 1.6;
    white-space: nowrap;
    animation: skill-pop 0.18s ease-out both;
  }

  .skill-icon {
    font-size: 12px;
    line-height: 1;
  }

  @keyframes skill-pop {
    from {
      opacity: 0;
      transform: scale(0.85) translateY(-2px);
    }
    to {
      opacity: 1;
      transform: scale(1) translateY(0);
    }
  }

  /* ── 도구 상태 ── */
  .tool-status {
    margin-top: 8px;
    font-size: 12px;
    color: var(--fg-muted);
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    padding: 5px 10px;
    border-radius: 6px;
    display: inline-block;
    font-family: var(--font-mono);
  }

  .thinking {
    display: inline-flex;
    gap: 4px;
    padding: 6px 0;
  }

  .thinking span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--fg-muted);
    animation: blink 1.2s infinite ease-in-out both;
  }

  .thinking span:nth-child(2) {
    animation-delay: 0.15s;
  }

  .thinking span:nth-child(3) {
    animation-delay: 0.3s;
  }

  @keyframes blink {
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
