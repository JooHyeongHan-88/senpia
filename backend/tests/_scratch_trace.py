import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent.tools  # noqa: F401  triggers tool registration
from agent.models import AgentState
from agent.providers.mock import MockProvider
from agent.registries.agents import registry as agent_registry
from agent.registries.prompts import registry as prompt_registry
from agent.registries.skills import registry as skill_registry
from agent.registries.tools import registry
from agent.stores.conversation import ConversationStore
from agent import harness

agent_registry.load()
skill_registry.load()


class MemState:
    def __init__(self):
        self.states = {}
    def get(self, cid):
        return self.states.setdefault(cid, AgentState())
    def set(self, cid, st):
        self.states[cid] = st
    def reset(self, cid):
        self.states.pop(cid, None)


async def run_scenario(trigger, client_id):
    store = ConversationStore(max_history=40)
    state_store = MemState()
    events = []
    async for ev in harness.run_turn(
        client_id, trigger,
        store=store, state_store=state_store,
        skill_registry=skill_registry, prompt_registry=prompt_registry,
        registry=registry, agent_registry=agent_registry,
        provider=MockProvider(), max_iterations=5, max_agent_calls=10,
    ):
        events.append(ev)
    return events, state_store.get(client_id)


def summarize(label, events, state):
    lines = [f"\n===== {label} ====="]
    for ev in events:
        t = type(ev).__name__
        if t in ("DeltaEvent", "ReasoningEvent"):
            continue
        if t == "AgentProgressEvent":
            ip = getattr(ev, "inner_payload", {})
            lines.append(f"  AgentProgress[{ev.inner_type}] name={ip.get('name')!r} is_error={ip.get('is_error')!r}" + (f" result={str(ip.get('result'))[:90]!r}" if ip.get('result') else ""))
            continue
        extra = ""
        for attr in ("message", "summary", "name", "result", "to_agent", "from_agent", "is_error", "is_fallback"):
            if hasattr(ev, attr):
                val = getattr(ev, attr)
                if val not in (None, "", False):
                    extra += f" {attr}={str(val)[:90]!r}"
        lines.append(f"  {t}{extra}")
    if state:
        lines.append("  -- final todo_list:")
        for it in state.todo_list:
            lines.append(f"     [{it.status.value}] {it.description[:50]}")
    print("\n".join(lines))


async def main():
    ev_d, st_d = await run_scenario("데이터 요약", "sess-D")
    summarize("Scenario D", ev_d, st_d)
    ev_e, st_e = await run_scenario("전체 분석 보고서", "sess-E")
    summarize("Scenario E", ev_e, st_e)


asyncio.run(main())
