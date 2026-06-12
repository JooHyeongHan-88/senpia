<script>
  import { ui, activeSession, isEmptySession } from "../lib/state.svelte.js";
  import MessageBubble from "./MessageBubble.svelte";
  import Logo from "./Logo.svelte";
  import { tick } from "svelte";

  let session = $derived(activeSession());
  let messages = $derived(session?.messages ?? []);
  let hero = $derived(isEmptySession());

  // 시간대별 인사말 — 장수 컴포넌트라 mount 1회 계산으로는 세션 전환·자정 넘김에
  // 둔감하다. activeSessionId 를 의존성으로 잡아 세션 전환 시 재계산한다.
  let greeting = $derived.by(() => {
    void ui.activeSessionId;
    const h = new Date().getHours();
    if (h >= 5 && h < 12) return "좋은 아침이에요";
    if (h >= 12 && h < 18) return "좋은 오후예요";
    return "좋은 저녁이에요";
  });

  let scrollEl = $state(null);
  let prevLastMessageId = $state(null);

  // 메시지 추가/스트리밍 시 자동 하단 스크롤. 마지막 메시지 id가 바뀌었을 때만 즉시 스크롤.
  $effect(() => {
    const last = messages[messages.length - 1];
    if (!scrollEl || !last) return;

    const isNewMessage = last.id !== prevLastMessageId;
    prevLastMessageId = last.id;

    tick().then(() => {
      if (!scrollEl) return;
      if (isNewMessage) {
        scrollEl.scrollTop = scrollEl.scrollHeight;
      } else {
        // 스트리밍 중에는 사용자가 위로 스크롤했으면 강제 이동 안 함.
        const nearBottom =
          scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight < 120;
        if (nearBottom) scrollEl.scrollTop = scrollEl.scrollHeight;
      }
    });
  });
</script>

<div class="scroll" class:hero bind:this={scrollEl}>
  <div class="inner">
    {#if hero}
      <div class="hero-block">
        <Logo size={30} />
        <h1 class="hero-greeting">{greeting}</h1>
      </div>
    {:else}
      {#each messages as msg (msg.id)}
        <MessageBubble message={msg} />
      {/each}
      <div class="tail-space"></div>
    {/if}
  </div>
</div>

<style>
  .scroll {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
  }

  .inner {
    max-width: 760px;
    margin: 0 auto;
    padding: 24px 24px 0;
  }

  /* 히어로 모드 — 인사말 블록을 하단(컴포저 직상단)에 정렬.
     App.svelte 의 hero-spacer 가 컴포저 아래 공간을 흡수해 쌍이 중앙 부근에 뜬다. */
  .scroll.hero {
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    overflow: hidden;
  }

  .scroll.hero .inner {
    width: 100%;
  }

  .hero-block {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 14px;
    padding-bottom: 10px;
  }

  .hero-greeting {
    font-family: var(--font-display);
    font-size: clamp(26px, 4vw, 34px);
    font-weight: 600;
    letter-spacing: -0.01em;
    color: var(--fg);
    margin: 0;
  }

  .tail-space {
    height: 16px;
  }
</style>
