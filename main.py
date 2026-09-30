"""
Meridian Data Copilot - CLI Entry Point.
"""

import sys
from langchain_core.messages import HumanMessage
from src.database import check_connection, get_domain_guidelines
from src.agent import meridian_graph

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_query(query: str):
    print(f"\n[User Query]: {query}\n" + "-" * 60)
    initial_state = {
        "messages": [HumanMessage(content=query)],
        "tool_history": [],
        "chart_figures": [],
        "iteration": 0,
        "sql_retries": 0,
    }
    result = meridian_graph.invoke(initial_state)
    final_msg = result["messages"][-1]
    
    history = result.get("tool_history", [])
    if history:
        print(f"\n[Reasoning Trace - {len(history)} Tool Action(s)]:")
        for idx, h in enumerate(history, 1):
            print(f"  {idx}. {h['tool']} ({h['status']}) - {h['duration_sec']}s")
            
    print("\n[Meridian Response]:\n")
    print(final_msg.content)
    print("=" * 60)


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "What was the total revenue in MAD for dealerships in Casablanca in 2024?"
    print(f"DB Connected: {check_connection()}")
    run_query(q)
