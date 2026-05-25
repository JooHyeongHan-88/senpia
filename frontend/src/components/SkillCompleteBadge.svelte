<script>
  /**
   * SkillCompleteEvent 수신 시 todo_list 전체 완료 통계를 한 줄로 표시하는 배지.
   *
   * @prop {{ completed: number, failed: number, skipped: number }} data
   */
  let { data } = $props();
</script>

<div class="sc-badge">
  <span class="sc-icon">✓</span>
  <span class="sc-label">작업 완료</span>
  {#if data.completed > 0}
    <span class="sc-stat completed">{data.completed} 완료</span>
  {/if}
  {#if data.failed > 0}
    <span class="sc-stat failed">{data.failed} 실패</span>
  {/if}
  {#if data.skipped > 0}
    <span class="sc-stat skipped">{data.skipped} 건너뜀</span>
  {/if}
</div>

<style>
  .sc-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-top: 6px;
    padding: 3px 10px 3px 8px;
    border-radius: 20px;
    background: color-mix(in srgb, var(--color-success) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--color-success) 30%, transparent);
    font-size: 11px;
    font-weight: 500;
    animation: badge-in 0.2s ease-out both;
  }

  .sc-icon {
    color: var(--color-success);
    font-size: 12px;
    line-height: 1;
  }

  .sc-label {
    color: var(--fg-muted);
  }

  .sc-stat {
    padding: 1px 6px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 600;
  }

  .sc-stat.completed {
    background: color-mix(in srgb, var(--color-success) 15%, transparent);
    color: var(--color-success);
  }

  .sc-stat.failed {
    background: color-mix(in srgb, var(--danger) 15%, transparent);
    color: var(--danger);
  }

  .sc-stat.skipped {
    background: color-mix(in srgb, var(--fg-subtle) 15%, transparent);
    color: var(--fg-subtle);
  }

  @keyframes badge-in {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
</style>
