# Claude Handoff: Agent Harness Improvements

Hello Claude Code! This document explains the recent architectural improvements made to the Agent Harness (`backend/agent/harness.py`) and the underlying reasoning, so you have the correct context when making future modifications.

## 1. Subagent Delegation Constraint

### Context
Based on best practices from advanced agent frameworks (including Claude Code's own SDK documentation), we explicitly restrict **Nested Subagent Delegation** (a subagent calling another subagent). 

### Implementation
- `MAX_AGENT_DEPTH` in `backend/agent/config.py` is strictly set to `1`. (Orchestrator = 0, Subagent = 1).
- The `SUB_AGENT_DISPATCH` tool (`call_sub_agent`) is entirely filtered out of the `sub_specs` passed to subagents (via `_filter_specs_for_sub_agent`).
- **Rule of Thumb**: Subagents must only execute concrete tools to accomplish their specific task. Any multi-step delegation involving different roles must be orchestrated by the main agent (Orchestrator) using "Pattern 1" (Main agent orchestration).

## 2. Smart Loop Detection

### Context
Agents sometimes get stuck in loops, repeatedly calling the same tool with the same failing arguments.

### Implementation
- Added `history_calls: set[tuple[str, str]]` in the `_run_agent_turn` loop.
- It records a hash of `(tool_name, arguments_json_string)`.
- If an exact duplicate call is detected within the same turn, the tool execution is intercepted. Instead of running the tool, a system prompt is injected into the `ToolResultEvent` forcing the agent to perform Root Cause Analysis and change its approach.

## 3. Error Recovery (Prompt Injection)

### Context
When a tool throws a Python exception (Timeout, KeyError, etc.), returning just the stack trace often leads the agent to blindly retry or give up.

### Implementation
- In `_execute_tool`, if the tool returns `is_error=True` (or an exception is caught), a recovery prompt is appended to `result.content`: 
  `"[System] 작업이 실패했습니다. 에러 로그를 읽고 원인을 분석(Root Cause Analysis)한 뒤 최대 1회 더 재시도하세요."`
- This ensures the agent pauses to think (`reasoning` step) rather than immediately retrying identically.

## 4. Graceful Degradation / Fallback Guarantee

### Context
When an agent hits the `max_iterations` limit (default 5), the turn used to abruptly terminate with an `ErrorEvent`. This resulted in poor UX, as the user was left hanging without a concluding summary.

### Implementation
- In `_run_agent_turn`, when the `else:` block of the `for iteration in range(max_iterations):` loop is reached, it no longer immediately yields an `ErrorEvent`.
- Instead, it appends a synthetic User message prompting the agent to summarize what was completed and what failed, and makes **one final LLM call with no tools allowed** (`[]` for `sub_specs`).
- The resulting text is yielded to the frontend, ensuring the user always receives a natural language explanation of the failure before the turn technically ends.

## UI Implications
- In the Svelte frontend, `TodoProgress.svelte` detects error-related `toolStatus` strings (marked with "⚠️") and shows a "복구 시도 중..." (Attempting recovery...) badge.
- Fallback messages (generated due to max iterations) are highlighted with a distinct danger-themed markdown styling in `MessageBubble.svelte`.

## 5. Release Pipeline Reliability Improvements

### Context
The original release scripts (`packaging/release.ps1`) were robust in handling file operations but lacked defensive checks against human errors and network instability, which could lead to un-reproducible builds or partial upload failures.

### Implementation
- **Git Working Directory Check**: Added a pre-flight check using `git status --porcelain`. The script now aborts if there are uncommitted changes, ensuring only clean, reproducible states are built. This can be bypassed using the `-Force` switch.
- **Nexus Version Pre-flight Check**: Before starting the time-consuming frontend and PyInstaller builds, the script now sends a `HEAD` request to Nexus (`$NexusBaseUrl/$versionedName`). If the target version already exists (HTTP 200 OK), the script aborts early to prevent accidental overwrites, unless `-Force` is provided.
- **Secure Credentials**: Removed the necessity of passing `-NexusPass` as a plaintext CLI argument. The script now prioritizes environment variables (`NEXUS_USER`/`NEXUS_PASSWORD`). If absent, it securely prompts the user using `Read-Host -AsSecureString`.
- **Upload Retry Logic**: Wrapped `Invoke-WebRequest` calls for uploading the EXE and `latest.json` in a custom `Invoke-WithRetry` function (3 attempts, 5-second delay) to gracefully handle transient network errors.
- **Dry-run Integration**: `packaging/release-dryrun.ps1` was updated to accept a `-Force` flag and pass it down to `release.ps1` via splatting (`@releaseArgs`), allowing local testing even on dirty git branches.

## 6. Centralized Configuration via .env (SSOT)

### Context
Previously, release configurations (such as Nexus credentials and the repository base URL) were scattered across PowerShell script arguments, and the executable name was hardcoded in `packaging/App.spec`. This fragmented approach made managing environment-specific configurations difficult.

### Implementation
- **App.spec Integration**: The PyInstaller spec file (`packaging/App.spec`) now dynamically reads the `.env` file to extract `APP_NAME`. This completely removes the need to manually edit `App.spec` when renaming the application.
- **PowerShell Script Integration**: Both `release.ps1` and `release-dryrun.ps1` have been updated to parse the `.env` file upon execution. They automatically populate their context with `APP_NAME`, `APP_NEXUS_BASE_URL`, `APP_NEXUS_USER`, and `APP_NEXUS_PASSWORD`.
- **SSOT**: The `.env` file now serves as the Single Source of Truth for both the application runtime (FastAPI/Vite) and the build/deployment pipelines (PyInstaller/Nexus).
