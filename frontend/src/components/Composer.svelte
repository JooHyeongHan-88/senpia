<script>
  import { ui } from "../lib/state.svelte.js";
  import { sendMessage, stopStreaming } from "../lib/chatActions.svelte.js";
  import SkillPicker from "./SkillPicker.svelte";

  // contenteditable 입력창. Svelte 가 관리하는 자식을 두지 않고 내용은 명령형으로 조작한다
  // (Svelte 반응성과 DOM 변형 충돌 방지). 인용은 contenteditable=false pill atom 으로 인라인 삽입.
  let editorEl = $state(null);
  let highlight = $state(0);
  // 빈 상태 판정용 평문 거울. 입력/삽입/삭제 때 editorEl 에서 동기화.
  let plainText = $state("");
  let hasPills = $state(false);
  // 에디터 밖 버튼(@참조)이 포커스를 가져가도 caret 위치를 복원하려고 보존하는 range.
  let savedRange = null;
  // 외부 신호(삽입/복원) 중복 소비 방지용 nonce 기억.
  let lastInsertNonce = 0;
  let lastSetNonce = 0;

  // 슬래시 토큰 — caret 직전의 "/query" (텍스트 중간 포함). updateSlashToken 이 채운다.
  let slashActive = $state(false);
  let slashQuery = $state("");
  let slashSuppressed = $state(null); // Esc 로 닫은 토큰 (재타이핑/이동 시 해제)
  // 토큰의 DOM 위치 (비반응 — pickSkill 이 "/query" 를 pill 로 교체할 때 사용).
  let slashRange = null; // { node, start, end }

  let pickerOpen = $derived(slashActive && !ui.streaming && slashQuery !== slashSuppressed);
  let pickerQuery = $derived(slashActive ? slashQuery : "");
  let filteredSkills = $derived(filterSkills(ui.availableSkills, pickerQuery));

  let isEmpty = $derived(plainText.trim().length === 0 && !hasPills);
  let canSend = $derived(!isEmpty && !ui.streaming);

  let placeholder = $derived(
    ui.streaming
      ? "응답 중…  ·  ESC 로 중지"
      : "메시지를 입력하세요  ·  / 로 스킬 호출",
  );

  function filterSkills(all, q) {
    const needle = (q ?? "").trim().toLowerCase();
    if (!needle) return all.slice(0, 6);
    return all
      .filter((s) => `${s.name} ${s.description ?? ""}`.toLowerCase().includes(needle))
      .slice(0, 6);
  }

  // ── 에디터 상태 동기화 ──────────────────────────────────────────────
  function syncEditorState() {
    if (!editorEl) return;
    plainText = editorEl.textContent ?? "";
    hasPills = !!editorEl.querySelector(".ref-pill, .skill-pill");
  }

  function saveRange() {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const r = sel.getRangeAt(0);
    if (editorEl && editorEl.contains(r.commonAncestorContainer)) {
      savedRange = r.cloneRange();
    }
  }

  // caret 직전의 "/query" 슬래시 토큰을 찾는다. 토큰은 줄머리/공백 뒤 "/" 로 시작하고
  // 공백·"/" 를 포함하지 않아야 한다 (텍스트 중간에서도 동작 — Claude Desktop 류).
  function detectSlashToken() {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || !sel.isCollapsed) return null;
    const r = sel.getRangeAt(0);
    const node = r.startContainer;
    if (!editorEl || node.nodeType !== Node.TEXT_NODE || !editorEl.contains(node)) {
      return null;
    }
    const off = r.startOffset;
    const before = node.textContent.slice(0, off);
    const m = before.match(/(?:^|\s)\/([^\s/]*)$/);
    if (!m) return null;
    const query = m[1];
    return { node, start: off - query.length - 1, end: off, query };
  }

  function updateSlashToken() {
    const tok = detectSlashToken();
    if (tok) {
      slashRange = { node: tok.node, start: tok.start, end: tok.end };
      slashQuery = tok.query;
      slashActive = true;
    } else {
      slashRange = null;
      slashActive = false;
      slashQuery = "";
      slashSuppressed = null; // 토큰이 사라지면 억제 해제
    }
  }

  // caret 위치 보존 + 슬래시 토큰 재평가를 한 번에 (keyup/mouseup/blur/input 공용).
  function refreshCaret() {
    saveRange();
    updateSlashToken();
  }

  function focusEnd() {
    if (!editorEl) return;
    editorEl.focus();
    const sel = window.getSelection();
    const r = document.createRange();
    r.selectNodeContents(editorEl);
    r.collapse(false);
    sel.removeAllRanges();
    sel.addRange(r);
    savedRange = r.cloneRange();
  }

  // ── pill DOM (Svelte 컴포넌트 대신 평 DOM — contenteditable 안에 안전하게 삽입) ──
  function buildPill(path, label) {
    const span = document.createElement("span");
    span.className = "ref-pill";
    span.contentEditable = "false";
    span.dataset.path = path;
    span.dataset.label = label;
    span.title = path;
    span.innerHTML =
      '<svg class="ref-pill-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
    const lbl = document.createElement("span");
    lbl.className = "ref-pill-label";
    lbl.textContent = label;
    span.appendChild(lbl);
    return span;
  }

  function insertPill(path, label) {
    if (!editorEl) return;
    editorEl.focus();
    const sel = window.getSelection();
    let range;
    if (savedRange && editorEl.contains(savedRange.commonAncestorContainer)) {
      range = savedRange.cloneRange();
    } else {
      range = document.createRange();
      range.selectNodeContents(editorEl);
      range.collapse(false);
    }
    sel.removeAllRanges();
    sel.addRange(range);
    range.deleteContents();
    const pill = buildPill(path, label);
    const space = document.createTextNode(" "); // pill 뒤 caret 자리 확보
    range.insertNode(space);
    range.insertNode(pill);
    range.setStartAfter(space);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
    savedRange = range.cloneRange();
    syncEditorState();
  }

  // 스킬 pill — "/" 명령으로 삽입되는 inline atom (ref pill 과 시각·동작 일관, 별도 톤).
  function buildSkillPill(name) {
    const span = document.createElement("span");
    span.className = "skill-pill";
    span.contentEditable = "false";
    span.dataset.skill = name;
    span.title = `스킬: ${name}`;
    span.innerHTML = '<span class="skill-pill-icon">✦</span>';
    const lbl = document.createElement("span");
    lbl.className = "skill-pill-label";
    lbl.textContent = name;
    span.appendChild(lbl);
    return span;
  }

  // "/query" 토큰 자리를 스킬 pill 로 교체 (토큰 위치 없으면 caret 위치에 삽입).
  function insertSkillPill(name) {
    if (!editorEl) return;
    editorEl.focus();
    const sel = window.getSelection();
    let range;
    if (slashRange && editorEl.contains(slashRange.node)) {
      range = document.createRange();
      range.setStart(slashRange.node, slashRange.start);
      range.setEnd(slashRange.node, slashRange.end);
    } else if (savedRange && editorEl.contains(savedRange.commonAncestorContainer)) {
      range = savedRange.cloneRange();
    } else {
      range = document.createRange();
      range.selectNodeContents(editorEl);
      range.collapse(false);
    }
    sel.removeAllRanges();
    sel.addRange(range);
    range.deleteContents();
    const pill = buildSkillPill(name);
    const space = document.createTextNode(" ");
    range.insertNode(space);
    range.insertNode(pill);
    range.setStartAfter(space);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
    savedRange = range.cloneRange();
    slashRange = null;
    slashActive = false;
    slashQuery = "";
    slashSuppressed = null;
    syncEditorState();
  }

  // caret 직전에 붙어 있는 pill 엘리먼트를 반환 (없으면 null) — 백스페이스 통째 삭제용.
  function pillBeforeCaret() {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || !sel.isCollapsed) return null;
    const r = sel.getRangeAt(0);
    const node = r.startContainer;
    if (node.nodeType === Node.TEXT_NODE) {
      if (r.startOffset > 0) return null; // 텍스트 중간 — 일반 글자 삭제
      const prev = node.previousSibling;
      return _isAtomPill(prev) ? prev : null;
    }
    const child = node.childNodes[r.startOffset - 1];
    return _isAtomPill(child) ? child : null;
  }

  function _isRefPill(node) {
    return (
      node &&
      node.nodeType === Node.ELEMENT_NODE &&
      node.classList?.contains("ref-pill")
    );
  }

  function _isSkillPill(node) {
    return (
      node &&
      node.nodeType === Node.ELEMENT_NODE &&
      node.classList?.contains("skill-pill")
    );
  }

  // ref / skill 어느 쪽이든 통째 삭제·직렬화 대상이 되는 inline atom.
  function _isAtomPill(node) {
    return _isRefPill(node) || _isSkillPill(node);
  }

  // ── parts 직렬화 (text 노드 + pill atom + br → 순서 있는 배열) ──
  function readParts() {
    const parts = [];
    const pushText = (t) => {
      if (!t) return;
      const last = parts[parts.length - 1];
      if (last && last.type === "text") last.value += t;
      else parts.push({ type: "text", value: t });
    };
    const walk = (node) => {
      node.childNodes.forEach((n) => {
        if (n.nodeType === Node.TEXT_NODE) {
          pushText(n.textContent.replace(/ /g, " "));
        } else if (n.nodeType === Node.ELEMENT_NODE) {
          if (_isRefPill(n)) {
            parts.push({ type: "ref", path: n.dataset.path, label: n.dataset.label });
          } else if (_isSkillPill(n)) {
            parts.push({ type: "skill", name: n.dataset.skill });
          } else if (n.tagName === "BR") {
            pushText("\n");
          } else {
            pushText("\n"); // 예기치 못한 블록(붙여넣기 잔재) — 줄바꿈 후 재귀
            walk(n);
          }
        }
      });
    };
    walk(editorEl);
    return parts;
  }

  function clearEditor() {
    if (editorEl) editorEl.innerHTML = "";
    savedRange = null;
    syncEditorState();
  }

  function setEditorFromParts(parts) {
    if (!editorEl) return;
    editorEl.innerHTML = "";
    for (const p of parts ?? []) {
      if (p.type === "ref" && p.path) {
        editorEl.appendChild(buildPill(p.path, p.label || p.path));
        editorEl.appendChild(document.createTextNode(" "));
      } else if (p.type === "skill" && p.name) {
        editorEl.appendChild(buildSkillPill(p.name));
        editorEl.appendChild(document.createTextNode(" "));
      } else if (p.type === "text") {
        editorEl.appendChild(document.createTextNode(p.value ?? ""));
      }
    }
    syncEditorState();
    queueMicrotask(() => focusEnd());
  }

  // ── 액션 ────────────────────────────────────────────────────────────
  // 슬래시 picker 에서 스킬 선택 → "/query" 토큰을 inline 스킬 pill 로 교체.
  // (@인용 pill 과 동일하게 본문 텍스트 흐름 안에 들어가며, 전송 시 force_skills 로 추출됨)
  function pickSkill(name) {
    if (!name) return;
    insertSkillPill(name);
    highlight = 0;
  }

  async function submit() {
    if (!canSend) return;
    // 스킬 pill 포함 — readParts 가 {type:"skill"} 로 직렬화, sendMessage 가 force_skills 추출.
    const parts = readParts();
    clearEditor();
    await sendMessage(parts);
  }

  function insertLineBreak() {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const r = sel.getRangeAt(0);
    r.deleteContents();
    const br = document.createElement("br");
    r.insertNode(br);
    r.setStartAfter(br);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
    syncEditorState();
    refreshCaret();
  }

  function onInput() {
    highlight = 0;
    syncEditorState();
    refreshCaret();
  }

  function onPaste(e) {
    e.preventDefault();
    const text = e.clipboardData?.getData("text/plain") ?? "";
    if (!text) return;
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const r = sel.getRangeAt(0);
    r.deleteContents();
    const node = document.createTextNode(text);
    r.insertNode(node);
    r.setStartAfter(node);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
    syncEditorState();
    refreshCaret();
  }

  function onKey(e) {
    // 패널 열림 — 화살표/Enter/Esc/Tab 을 가로채 picker 조작에만 사용.
    if (pickerOpen && filteredSkills.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        highlight = (highlight + 1) % filteredSkills.length;
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        highlight = (highlight - 1 + filteredSkills.length) % filteredSkills.length;
        return;
      }
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        pickSkill(filteredSkills[highlight]?.name);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        slashSuppressed = slashQuery; // picker 만 닫음 — "/query" 텍스트는 그대로 둔다.
        return;
      }
      if (e.key === "Tab") {
        e.preventDefault();
        pickSkill(filteredSkills[highlight]?.name);
        return;
      }
    }

    // 백스페이스 — caret 직전이 pill 이면 글자 단위가 아니라 통째 삭제.
    if (e.key === "Backspace" && !e.isComposing) {
      const pill = pillBeforeCaret();
      if (pill) {
        e.preventDefault();
        const after = pill.nextSibling;
        pill.remove();
        // pill 직후 caret 정착자(nbsp)도 같이 정리해 흔적이 남지 않게 한다.
        if (after && after.nodeType === Node.TEXT_NODE && after.textContent === " ") {
          after.remove();
        }
        syncEditorState();
        refreshCaret();
        return;
      }
    }

    // Enter — 전송, Shift+Enter — 줄바꿈. 한글 조합(isComposing) 중엔 무시.
    if (e.key === "Enter" && !e.isComposing) {
      if (e.shiftKey) {
        e.preventDefault();
        insertLineBreak();
      } else {
        e.preventDefault();
        submit();
      }
    }
  }

  // ── 외부 신호 소비 ($effect — composerSeed 패턴 계승, nonce 로 중복 방지) ──
  $effect(() => {
    const sig = ui.composerInsertRef;
    if (sig && sig.nonce !== lastInsertNonce) {
      lastInsertNonce = sig.nonce;
      for (const item of sig.items ?? []) insertPill(item.path, item.label);
      ui.composerInsertRef = null;
      queueMicrotask(() => editorEl?.focus());
    }
  });

  $effect(() => {
    const sig = ui.composerSetParts;
    if (sig && sig.nonce !== lastSetNonce) {
      lastSetNonce = sig.nonce;
      setEditorFromParts(sig.parts ?? []);
      ui.composerSetParts = null;
    }
  });

  // 윈도우 레벨 ESC — 입력창이 streaming 중 비편집이라 onKey 가 안 잡힌다.
  function onWindowKey(e) {
    if (e.key !== "Escape" || !ui.streaming) return;
    e.preventDefault();
    stopStreaming();
  }
</script>

<svelte:window onkeydown={onWindowKey} />

<div class="composer-wrap">
  <!-- 슬래시 커맨드 패널 — 입력창 위에 부유 -->
  {#if pickerOpen}
    <div class="picker-anchor">
      <SkillPicker
        query={pickerQuery}
        skills={ui.availableSkills}
        {highlight}
        onPick={pickSkill}
      />
    </div>
  {/if}

  <div class="composer">
    <div
      bind:this={editorEl}
      class="editor"
      class:is-empty={isEmpty}
      contenteditable={ui.streaming ? "false" : "true"}
      role="textbox"
      tabindex="0"
      aria-multiline="true"
      aria-label="메시지 입력"
      data-placeholder={placeholder}
      oninput={onInput}
      onkeydown={onKey}
      onpaste={onPaste}
      onkeyup={refreshCaret}
      onmouseup={refreshCaret}
      onblur={refreshCaret}
    ></div>
    <button class="send" onclick={submit} disabled={!canSend} aria-label="전송">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 2 11 13" />
        <path d="m22 2-7 20-4-9-9-4 20-7z" />
      </svg>
    </button>
  </div>
  <div class="hint">Enter 로 전송 · Shift+Enter 줄바꿈 · / 로 스킬 검색</div>
</div>

<style>
  .composer-wrap {
    max-width: 760px;
    margin: 0 auto;
    padding: 12px 24px 18px;
    width: 100%;
    position: relative; /* picker-anchor 의 절대 위치 기준 */
  }

  /* SkillPicker 를 입력창 바로 위에 띄움 */
  .picker-anchor {
    position: absolute;
    left: 24px;
    right: 24px;
    bottom: calc(100% - 4px);
    z-index: 20;
  }

  .composer {
    display: flex;
    align-items: flex-end;
    gap: 8px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    padding: 10px 10px 10px 14px;
    box-shadow: var(--shadow-sm);
    transition: border-color var(--dur-fast) ease, box-shadow var(--dur-fast) ease;
  }

  .composer:focus-within {
    border-color: var(--accent);
    box-shadow: var(--focus-ring);
  }

  .editor {
    flex: 1;
    min-width: 0;
    outline: none;
    background: transparent;
    font-size: 15px; /* 채팅 본문(.markdown 15px)과 톤 일치 */
    line-height: 1.5;
    padding: 4px 0;
    min-height: 24px;
    max-height: 200px;
    overflow-y: auto;
    color: var(--fg);
    white-space: pre-wrap;
    word-break: break-word;
    position: relative;
  }

  /* 빈 상태 placeholder — :empty 는 bogus <br> 에 취약해 is-empty 클래스로 제어 */
  .editor.is-empty::before {
    content: attr(data-placeholder);
    color: var(--fg-subtle);
    pointer-events: none;
  }

  /* 인라인 인용 pill — 본문 텍스트와 구분되는 액센트 톤 */
  :global(.editor .ref-pill) {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    vertical-align: baseline;
    font-size: 13px;
    font-weight: 500;
    color: var(--accent);
    background: var(--accent-soft);
    border: 1px solid var(--accent-border);
    border-radius: var(--radius-sm);
    padding: 0 6px;
    margin: 0 1px;
    line-height: 1.5;
    white-space: nowrap;
    user-select: none;
    cursor: default;
  }

  :global(.editor .ref-pill-icon) {
    flex-shrink: 0;
    opacity: 0.85;
  }

  :global(.editor .ref-pill-label) {
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* 인라인 스킬 pill — "/" 명령으로 삽입. ref pill 과 같은 형태에 강조 톤(채움)으로 구분 */
  :global(.editor .skill-pill) {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    vertical-align: baseline;
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
    background: var(--accent-soft-strong);
    border: 1px solid var(--accent-border);
    border-radius: var(--radius-sm);
    padding: 0 7px;
    margin: 0 1px;
    line-height: 1.5;
    white-space: nowrap;
    user-select: none;
    cursor: default;
  }

  :global(.editor .skill-pill-icon) {
    flex-shrink: 0;
    font-size: 11px;
    line-height: 1;
  }

  :global(.editor .skill-pill-label) {
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .send {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border-radius: var(--radius-md);
    background: var(--accent);
    color: var(--accent-fg);
    transition: background var(--dur-fast) ease, transform 0.06s ease;
    flex-shrink: 0;
  }

  .send:hover:not(:disabled) {
    background: var(--accent-hover);
  }

  .send:active:not(:disabled) {
    transform: scale(0.96);
  }

  .send:disabled {
    background: var(--border-strong);
    color: var(--fg-subtle);
  }

  .hint {
    text-align: center;
    margin-top: 8px;
    font-size: 11.5px;
    color: var(--fg-subtle);
  }
</style>
