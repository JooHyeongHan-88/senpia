<!--
  슬래시 커맨드 autocomplete 패널 — Composer 바로 위에 부유.

  Composer 가 query/skills/onPick/onClose 를 prop 으로 내려준다. 키보드 이벤트는
  Composer 가 가로채서 highlight 인덱스만 prop 으로 동기화한다 — focus 가
  textarea 에 머물도록 하기 위함.
-->
<script>
  let { query = "", skills = [], highlight = 0, onPick } = $props();

  // 단순 substring fuzzy — name + description 어느 쪽에 매칭되어도 통과.
  let filtered = $derived(filterSkills(skills, query));

  function filterSkills(all, q) {
    const needle = (q ?? "").trim().toLowerCase();
    if (!needle) return all.slice(0, 6);
    const hits = all.filter((s) => {
      const hay = `${s.name} ${s.description ?? ""}`.toLowerCase();
      return hay.includes(needle);
    });
    return hits.slice(0, 6);
  }

  // Composer 의 ↑↓ 가 invalid 한 인덱스를 보낼 수도 있으므로 안전 clamp.
  let safeHighlight = $derived(
    filtered.length === 0 ? -1 : Math.min(Math.max(highlight, 0), filtered.length - 1),
  );
</script>

{#if filtered.length > 0}
  <div class="picker" role="listbox" aria-label="스킬 선택">
    <div class="header">SKILL · {filtered.length}개</div>
    {#each filtered as skill, i (skill.name)}
      <button
        type="button"
        class="item"
        class:active={i === safeHighlight}
        role="option"
        aria-selected={i === safeHighlight}
        onclick={() => onPick(skill.name)}
        onmousedown={(e) => e.preventDefault()}
      >
        <div class="row1">
          <span class="icon">✦</span>
          <span class="name">{skill.name}</span>
          {#if skill.trigger && skill.trigger.length > 0}
            <span class="triggers">
              {skill.trigger.slice(0, 3).join(" · ")}
            </span>
          {/if}
        </div>
        {#if skill.description}
          <div class="desc">{skill.description}</div>
        {/if}
      </button>
    {/each}
  </div>
{:else if (query ?? "").trim().length > 0}
  <div class="picker empty">
    <div class="header">일치하는 스킬 없음</div>
  </div>
{/if}

<style>
  .picker {
    background: var(--bg);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-md);
    overflow: hidden;
    max-height: 280px;
    overflow-y: auto;
  }

  .header {
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--fg-subtle);
    padding: 8px 12px 4px;
    font-weight: 600;
  }

  .empty .header {
    padding: 10px 12px;
  }

  .item {
    display: flex;
    flex-direction: column;
    width: 100%;
    text-align: left;
    padding: 8px 12px;
    gap: 2px;
    border-radius: 0;
    transition: background var(--dur-fast) ease;
  }

  .item:hover,
  .item.active {
    background: var(--bg-hover);
  }

  .row1 {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .icon {
    font-size: 11px;
    color: var(--accent);
  }

  .name {
    font-size: 13px;
    font-weight: 600;
    color: var(--fg);
  }

  .triggers {
    font-size: 11px;
    color: var(--fg-subtle);
    margin-left: auto;
    font-family: var(--font-mono);
  }

  .desc {
    font-size: 12px;
    color: var(--fg-muted);
    line-height: 1.45;
    padding-left: 17px;
  }
</style>
