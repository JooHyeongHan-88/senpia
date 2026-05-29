import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent.tools  # noqa
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
        self.s = {}

    def get(self, c):
        return self.s.setdefault(c, AgentState())

    def set(self, c, v):
        self.s[c] = v

    def reset(self, c):
        self.s.pop(c, None)


async def run(trigger, cid, max_iter, budget):
    store = ConversationStore(max_history=40)
    ss = MemState()
    err = []
    ret = []
    final_delta = []
    async for ev in harness.run_turn(
        cid,
        trigger,
        store=store,
        state_store=ss,
        skill_registry=skill_registry,
        prompt_registry=prompt_registry,
        registry=registry,
        agent_registry=agent_registry,
        provider=MockProvider(),
        max_iterations=max_iter,
        max_agent_calls=budget,
    ):
        tn = type(ev).__name__
        if tn == "ErrorEvent":
            err.append((ev.message, getattr(ev, "is_fallback", False)))
        elif tn == "AgentReturnEvent":
            ret.append((ev.from_agent, ev.summary[:60]))
        elif tn == "DeltaEvent":
            final_delta.append(ev.content)
    st = ss.get(cid)
    todos = [(t.status.value, t.description[:30]) for t in st.todo_list]
    return err, ret, todos, "".join(final_delta)[:80]


async def main():
    for mi, bud in [(5, 10), (8, 20)]:
        print(f"\n############ max_iter={mi} budget={bud} ############")
        for label, trig, c in [
            ("D", "데이터 요약", "D"),
            ("E", "전체 분석 보고서", "E"),
        ]:
            err, ret, todos, fd = await run(trig, f"s{c}-{mi}-{bud}", mi, bud)
            print(f"\n--- Scenario {label} ---")
            print(f"  AgentReturns: {ret}")
            print(f"  Errors: {err}")
            print(f"  Orch todos: {todos}")
            print(f"  Final reply: {fd!r}")


asyncio.run(main())
