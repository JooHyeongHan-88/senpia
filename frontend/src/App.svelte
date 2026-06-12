<script>
  import { onMount, onDestroy } from "svelte";
  import { isEmptySession } from "./lib/state.svelte.js";
  import { initApp, teardown } from "./lib/chatActions.svelte.js";
  import { loadSettingsForInit } from "./lib/settingsActions.svelte.js";

  import Sidebar from "./components/Sidebar.svelte";
  import TopBar from "./components/TopBar.svelte";
  import ChatArea from "./components/ChatArea.svelte";
  import Composer from "./components/Composer.svelte";
  import UpdateBanner from "./components/UpdateBanner.svelte";
  import UpdateModal from "./components/UpdateModal.svelte";
  import SettingsModal from "./components/SettingsModal.svelte";
  import ArtifactPanel from "./components/ArtifactPanel.svelte";
  import ArtifactLightbox from "./components/ArtifactLightbox.svelte";

  onMount(() => {
    initApp();
    loadSettingsForInit();
  });

  onDestroy(() => {
    teardown();
  });

  let hero = $derived(isEmptySession());
</script>

<div class="app">
  <Sidebar />
  <main class="main">
    <TopBar />
    <ChatArea />
    <Composer />
    {#if hero}
      <!-- 컴포저 아래 여백 흡수 — 인사말+컴포저 쌍이 중앙 약간 위에 떠 보이게 -->
      <div class="hero-spacer"></div>
    {/if}
  </main>
  <ArtifactPanel />
</div>

<UpdateBanner />
<UpdateModal />
<SettingsModal />
<ArtifactLightbox />

<style>
  .app {
    display: flex;
    height: 100%;
    overflow: hidden;
  }

  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg);
  }

  /* ChatArea(flex:1)와 비율 분배 — 1 : 0.85 로 쌍을 중앙보다 살짝 위에 배치 */
  .hero-spacer {
    flex: 0.85 1 0;
    min-height: 0;
  }
</style>
