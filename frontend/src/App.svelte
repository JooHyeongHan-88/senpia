<script>
  import { onMount } from "svelte";

  let input = "";
  let messages = [];
  let streaming = false;

  let updateInfo = null; // { current, latest, update_available, notes, size }
  let updateDismissed = false;
  let modalOpen = false;
  let applying = false;
  let applyState = null; // { status, progress, total, message, target_version }
  let restarting = false;

  function getClientId() {
    let id = sessionStorage.getItem("client_id");

    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem("client_id", id);
    }

    return id;
  }

  const clientId = getClientId();

  async function loadHistory() {
    try {
      const r = await fetch(`/api/conversation?client_id=${clientId}`);
      if (!r.ok) return;
      const data = await r.json();
      messages = (data.messages ?? []).map((m) => ({
        role: m.role,
        content: m.content ?? "",
        toolStatus: null,
      }));
    } catch {
      // 서버가 아직 준비 안 됐을 수 있음 — 조용히 무시.
    }
  }

  async function sendMessage() {
    if (!input.trim() || streaming) return;

    const userMessage = input;
    messages = [
      ...messages,
      { role: "user", content: userMessage, toolStatus: null },
      { role: "assistant", content: "", toolStatus: null },
    ];
    input = "";
    streaming = true;

    try {
      const response = await fetch(`/api/chat?client_id=${clientId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMessage }),
      });

      if (!response.ok || !response.body) {
        appendToAssistant(`[error] HTTP ${response.status}`);
        return;
      }

      await consumeSseStream(response.body);
    } catch (e) {
      appendToAssistant(`[error] ${String(e)}`);
    } finally {
      streaming = false;
    }
  }

  async function consumeSseStream(body) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE 이벤트는 빈 줄로 구분된다.
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        const dataLine = rawEvent
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trimStart())
          .join("\n");

        if (!dataLine) continue;

        handleEvent(JSON.parse(dataLine));
      }
    }
  }

  function handleEvent(ev) {
    if (ev.type === "delta") {
      appendToAssistant(ev.content);
    } else if (ev.type === "tool_call") {
      setAssistantTool(`🔧 ${ev.call.name} 호출 중...`);
    } else if (ev.type === "tool_result") {
      setAssistantTool(`🔧 ${ev.name} → ${ev.result}`);
    } else if (ev.type === "error") {
      appendToAssistant(`\n[error] ${ev.message}`);
    } else if (ev.type === "done") {
      // 별도 처리 불필요 — UI 는 이미 누적된 상태.
    }
  }

  function appendToAssistant(text) {
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant") return;
    last.content += text;
    messages = messages; // svelte 반응성 트리거
  }

  function setAssistantTool(label) {
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant") return;
    last.toolStatus = label;
    messages = messages;
  }

  async function newConversation() {
    if (streaming) return;
    try {
      await fetch(`/api/conversation?client_id=${clientId}`, { method: "DELETE" });
    } catch {}
    messages = [];
  }

  function postJson(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  function checkUpdate() {
    fetch("/api/update/check")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;

        updateInfo = data;

        const dismissedFor = sessionStorage.getItem("update_dismissed_for");
        if (dismissedFor && dismissedFor === data.latest) {
          updateDismissed = true;
        }
      })
      .catch(() => {});
  }

  function dismissUpdate() {
    updateDismissed = true;
    if (updateInfo?.latest) {
      sessionStorage.setItem("update_dismissed_for", updateInfo.latest);
    }
  }

  async function applyUpdate() {
    applying = true;
    applyState = { status: "starting", progress: 0, total: 0, message: "" };
    modalOpen = true;

    const pollId = setInterval(async () => {
      try {
        const r = await fetch("/api/update/status");
        if (r.ok) {
          applyState = await r.json();
        }
      } catch {
        // 서버가 내려가는 중일 수 있음 — restarting 단계로 전환
        clearInterval(pollId);
        restarting = true;
      }
    }, 500);

    try {
      const r = await postJson("/api/update/apply", {});
      const data = await r.json();
      if (!data.ok) {
        clearInterval(pollId);
        applying = false;
        applyState = { status: "error", message: data.error || "unknown" };
      }
    } catch (e) {
      clearInterval(pollId);
      applying = false;
      applyState = { status: "error", message: String(e) };
    }
  }

  function progressPct(s) {
    if (!s || !s.total) return 0;
    return Math.min(100, Math.round((s.progress / s.total) * 100));
  }

  onMount(() => {
    // SSE 단일 채널로 생존을 알린다. 탭을 닫으면 브라우저가 자동으로 끊어주고,
    // 서버는 끊김을 보고 client 를 정리한다 (heartbeat / pagehide 비콘 불필요).
    const presence = new EventSource(`/api/presence?client_id=${clientId}`);

    loadHistory();
    checkUpdate();

    return () => {
      presence.close();
    };
  });
</script>

{#if updateInfo?.update_available && !updateDismissed && !modalOpen}
  <div class="update-banner">
    <span>새 버전 <b>{updateInfo.latest}</b> 사용 가능 (현재 {updateInfo.current})</span>
    <button onclick={applyUpdate}>지금 업데이트</button>
    <button class="ghost" onclick={dismissUpdate}>나중에</button>
  </div>
{/if}

{#if modalOpen}
  <div class="modal-backdrop">
    <div class="modal">
      {#if restarting}
        <h3>재시작 중…</h3>
        <p>새 버전으로 교체 후 자동으로 다시 열립니다.</p>
      {:else if applyState?.status === "error"}
        <h3>업데이트 실패</h3>
        <p>{applyState.message}</p>
        <button onclick={() => { modalOpen = false; applying = false; }}>닫기</button>
      {:else}
        <h3>업데이트 진행 중</h3>
        <p>{applyState?.message ?? ""}</p>
        <div class="progress">
          <div class="bar" style="width: {progressPct(applyState)}%"></div>
        </div>
        <small>{applyState?.status ?? ""}</small>
      {/if}
    </div>
  </div>
{/if}

<div class="header">
  <h1>My Agent</h1>
  <button class="new-btn" onclick={newConversation} disabled={streaming}>새 대화</button>
</div>

<div class="chat">
  {#each messages as msg}
    <div class={msg.role}>
      <b>{msg.role}</b>: {msg.content}
      {#if msg.toolStatus}
        <div class="tool-status">{msg.toolStatus}</div>
      {/if}
    </div>
  {/each}
</div>

<div class="input-row">
  <input
    bind:value={input}
    onkeydown={(e) => e.key === "Enter" && sendMessage()}
    placeholder="message..."
    disabled={streaming}
  />

  <button onclick={sendMessage} disabled={streaming}>
    Send
  </button>
</div>

<style>
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .new-btn {
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid #ccc;
    background: white;
    cursor: pointer;
  }

  .new-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .chat {
    margin-bottom: 1rem;
  }

  .user,
  .assistant {
    margin: 8px 0;
    white-space: pre-wrap;
  }

  .tool-status {
    margin-top: 4px;
    font-size: 0.85rem;
    color: #555;
    background: #f3f3f3;
    padding: 4px 8px;
    border-radius: 4px;
    display: inline-block;
  }

  .input-row {
    display: flex;
    gap: 8px;
  }

  input {
    flex: 1;
  }

  .update-banner {
    position: fixed;
    top: 12px;
    right: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: #1f6feb;
    color: white;
    border-radius: 6px;
    font-size: 0.9rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  }

  .update-banner button {
    padding: 4px 10px;
    border: none;
    border-radius: 4px;
    background: white;
    color: #1f6feb;
    cursor: pointer;
  }

  .update-banner button.ghost {
    background: transparent;
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.6);
  }

  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
  }

  .modal {
    background: white;
    color: #111;
    padding: 24px;
    border-radius: 8px;
    min-width: 320px;
    max-width: 480px;
  }

  .progress {
    width: 100%;
    height: 8px;
    background: #eee;
    border-radius: 4px;
    overflow: hidden;
    margin: 12px 0 4px;
  }

  .bar {
    height: 100%;
    background: #1f6feb;
    transition: width 0.2s ease;
  }
</style>
