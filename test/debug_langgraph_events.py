"""
LangGraph 1.0.10 astream_events 이벤트 구조 진단 스크립트

실제 워크플로와 동일한 구조(Command 라우팅)로 astream_events가
어떤 이벤트를 방출하는지 확인한다.

실행:
    cd AI-INNOVATION-CHALLENGE-2026
    python test/debug_langgraph_events.py
"""

import asyncio
import json
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command


# ── 최소 State ────────────────────────────────────────────────────
def _add(a: list, b: list) -> list:
    return a + b

class MinimalState(TypedDict):
    messages: Annotated[list, _add]
    step: str


# ── 노드 함수 (실제 워크플로와 동일한 패턴) ─────────────────────────

async def supervisor_agent(state: MinimalState) -> Command:
    """함수명(supervisor_agent) != 노드명("supervisor") — 실제 워크플로와 동일"""
    return Command(
        goto="search_agent",
        update={"step": "supervisor_done"},
    )


async def search_agent(state: MinimalState) -> Command:
    """함수명 == 노드명 ("search_agent") — 실제 워크플로와 동일"""
    return Command(
        goto="supervisor_final",
        update={"step": "search_done"},
    )


async def supervisor_agent_final(state: MinimalState) -> dict:
    """함수명(supervisor_agent_final) != 노드명("supervisor_final")"""
    return {
        "messages": [AIMessage(content="완료")],
        "step": "final",
    }


# ── 그래프 빌드 ───────────────────────────────────────────────────

def build_test_graph():
    g = StateGraph(MinimalState)
    g.add_node("supervisor", supervisor_agent)        # 함수명 != 노드명
    g.add_node("search_agent", search_agent)          # 함수명 == 노드명
    g.add_node("supervisor_final", supervisor_agent_final)  # 함수명 != 노드명

    g.add_edge(START, "supervisor")
    g.add_edge("supervisor_final", END)

    return g.compile()


# ── 이벤트 수집 ───────────────────────────────────────────────────

TRACKED = {"supervisor", "search_agent", "supervisor_final"}

async def run_and_print_events():
    graph = build_test_graph()
    initial = {
        "messages": [HumanMessage(content="테스트")],
        "step": "",
    }
    config = {"configurable": {"thread_id": "test-1"}, "recursion_limit": 20}

    print("\n" + "=" * 70)
    print("LangGraph 1.0.10  astream_events(version='v2') 이벤트 목록")
    print("=" * 70)

    node_start_events = []
    all_events = []

    async for event in graph.astream_events(initial, config, version="v2"):
        event_type    = event.get("event", "")
        name          = event.get("name", "")
        metadata      = event.get("metadata", {})
        lg_node       = metadata.get("langgraph_node", "<MISSING>")
        lg_step       = metadata.get("langgraph_step", "")

        all_events.append(event_type)

        # chain 이벤트만 출력 (너무 많아지는 LLM 토큰 제외)
        if "chain" in event_type or event_type in ("on_custom_event",):
            flag = "★" if lg_node in TRACKED else " "
            print(f"{flag} event={event_type:<25} name={name:<30} "
                  f"langgraph_node={lg_node:<25} step={lg_step}")

            if event_type == "on_chain_start" and lg_node in TRACKED:
                node_start_events.append(lg_node)

    print("\n" + "=" * 70)
    print("요약")
    print("=" * 70)
    print(f"전체 이벤트 수: {len(all_events)}")
    print(f"event 종류: {sorted(set(all_events))}")
    print()
    print(f"_TRACKED_NODES에 매칭된 on_chain_start: {node_start_events}")

    if node_start_events:
        print("\n✅ node_start 이벤트 정상 감지 — 백엔드 로직은 정상")
        print("   프론트엔드 또는 프록시 레이어 문제일 가능성 높음")
    else:
        print("\n❌ node_start 이벤트 감지 실패")
        print("   'on_chain_start' + metadata['langgraph_node'] 조건이 매칭되지 않음")
        print()
        print("   [확인 1] on_chain_start 이벤트 자체가 없다면:")
        print("           LangGraph 1.0 에서 이벤트 타입이 바뀐 것일 수 있음")
        print("   [확인 2] on_chain_start는 있지만 langgraph_node가 <MISSING>이라면:")
        print("           metadata 키가 변경된 것 — event['tags'] 또는 다른 키 확인 필요")
        print()
        # 추가: on_chain_start인데 TRACKED에 안 잡힌 이벤트 재출력
        print("--- on_chain_start 이벤트 중 TRACKED 미매칭 상세 ---")

    print()

    # 한 번 더: on_chain_start 전부 출력 (상세 확인용)
    print("=" * 70)
    print("[상세] on_chain_start 이벤트 전체 (metadata 포함)")
    print("=" * 70)
    async for event in graph.astream_events(initial, config, version="v2"):
        if event.get("event") == "on_chain_start":
            metadata = event.get("metadata", {})
            print(json.dumps({
                "event": event.get("event"),
                "name":  event.get("name"),
                "tags":  event.get("tags", []),
                "metadata_keys": list(metadata.keys()),
                "langgraph_node": metadata.get("langgraph_node"),
                "langgraph_step": metadata.get("langgraph_step"),
                "langgraph_triggers": metadata.get("langgraph_triggers"),
            }, ensure_ascii=False, indent=2))
            print()


if __name__ == "__main__":
    asyncio.run(run_and_print_events())
