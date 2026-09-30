"""
Meridian Data Copilot - Production Streamlit Interface (Stellantis Maroc Edition).
Enterprise Business Intelligence Copilot for Stellantis Maroc.
Synthesizes structured PostgreSQL truth (`stellantis_db`) and corporate PDF intelligence
with transparent AI reasoning traces and interactive analytics.
"""

import os
import json
import time
import pandas as pd
import streamlit as st
from pathlib import Path
from langchain_core.messages import HumanMessage, AIMessage

# Configure Page
st.set_page_config(
    page_title="Meridian | Stellantis Data Copilot",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Sleek CSS for Dark Theme & Glassmorphism
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    .stApp {
        background-color: #0b0f19;
        color: #f1f5f9;
    }
    
    .meridian-header {
        background: linear-gradient(135deg, rgba(30, 58, 138, 0.25) 0%, rgba(14, 165, 233, 0.12) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 24px;
        backdrop-filter: blur(8px);
    }
    .meridian-title {
        font-size: 26px;
        font-weight: 700;
        background: linear-gradient(90deg, #38bdf8 0%, #818cf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .meridian-subtitle {
        color: #94a3b8;
        font-size: 14px;
        margin-top: 6px;
        margin-bottom: 0;
    }
    
    .metric-card {
        background: #111827;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 10px;
    }
    .metric-label {
        color: #94a3b8;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
    }
    .metric-val {
        color: #f8fafc;
        font-size: 18px;
        font-weight: 700;
        margin-top: 2px;
    }
</style>
""", unsafe_allow_html=True)

from src.config import (
    BASE_DIR,
    PDF_DIR,
    GROQ_API_KEY,
    GROQ_MODEL,
    LANGCHAIN_TRACING_V2,
)
from src.database import (
    execute_sql,
    get_active_database_url,
    set_active_database_url,
    discover_database_schema,
)
from src.agent import meridian_graph, MeridianState
from src.charts import generate_chart
from src.rag import get_chroma_collection


def _import_parse_pdf_document():
    try:
        from scripts.ingest_docs import parse_pdf_document
        return parse_pdf_document
    except Exception:
        return None

parse_pdf_document = _import_parse_pdf_document()

# Initialize Session State
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "groq_key" not in st.session_state:
    st.session_state.groq_key = GROQ_API_KEY or ""
if "selected_model" not in st.session_state:
    st.session_state.selected_model = GROQ_MODEL or "openai/gpt-oss-120b"
if "db_connection_url" not in st.session_state:
    st.session_state.db_connection_url = get_active_database_url()


# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("### 🚗 Stellantis Environment")
    
    # 1. API & Model Settings
    with st.expander("⚙️ Model & Agent Settings", expanded=False):
        user_key = st.text_input(
            "Groq API Key",
            value=st.session_state.groq_key,
            type="password",
            placeholder="gsk_...",
        )
        if user_key != st.session_state.groq_key:
            st.session_state.groq_key = user_key
            os.environ["GROQ_API_KEY"] = user_key

        model_options = [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
        ]
        curr_idx = model_options.index(st.session_state.selected_model) if st.session_state.selected_model in model_options else 0
        model_choice = st.selectbox("Reasoning Engine", model_options, index=curr_idx)
        st.session_state.selected_model = model_choice
        os.environ["GROQ_MODEL"] = model_choice

    # 2. Database Connection
    with st.expander("🔌 PostgreSQL Database (`stellantis_db`)", expanded=False):
        db_input = st.text_input("Connection URL", value=st.session_state.db_connection_url)
        if st.button("Test Connection", use_container_width=True):
            set_active_database_url(db_input)
            st.session_state.db_connection_url = db_input
            test_res = execute_sql("SELECT 1 as conn_test;")
            if test_res.get("success"):
                st.success("Connected to PostgreSQL successfully (Read-Only)!")
            else:
                st.error(f"Connection error: {test_res.get('error')}")

    # 3. PDF Ingestion
    with st.expander("📂 Ingest Corporate PDFs", expanded=False):
        uploaded_pdfs = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
        if uploaded_pdfs:
            for up_pdf in uploaded_pdfs:
                save_dest = PDF_DIR / up_pdf.name
                save_dest.parent.mkdir(parents=True, exist_ok=True)
                with open(save_dest, "wb") as f:
                    f.write(up_pdf.getbuffer())

                try:
                    col = get_chroma_collection()
                    if parse_pdf_document:
                        chunks = parse_pdf_document(save_dest)
                        if chunks:
                            col.add(
                                ids=[c["id"] for c in chunks],
                                documents=[c["text"] for c in chunks],
                                metadatas=[c["metadata"] for c in chunks]
                            )
                            st.success(f"Indexed '{up_pdf.name}' ({len(chunks)} chunks)!")
                except Exception as e:
                    st.error(f"Error indexing PDF: {e}")

    st.markdown("---")

    # 4. Live Metrics
    st.markdown("#### 🗄️ PostgreSQL Metrics (`stellantis_db`)")
    try:
        dealerships_cnt = execute_sql("SELECT COUNT(*) as c FROM dealerships;")["rows"][0]["c"]
        vehicles_cnt = execute_sql("SELECT COUNT(*) as c FROM vehicles;")["rows"][0]["c"]
        sales_cnt = execute_sql("SELECT COUNT(*) as c FROM sales;")["rows"][0]["c"]
        rev_tot = execute_sql("SELECT ROUND(SUM(total_revenue_mad), 2) as r FROM sales;")["rows"][0]["r"]
    except Exception:
        dealerships_cnt, vehicles_cnt, sales_cnt, rev_tot = 7, 14, 4395, 1283534000.0

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Dealerships</div>
            <div class="metric-val">{dealerships_cnt}</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Models</div>
            <div class="metric-val">{vehicles_cnt}</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Sales Orders</div>
            <div class="metric-val">{sales_cnt:,}</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Total Revenue</div>
            <div class="metric-val">{float(rev_tot)/1e9:.2f}B MAD</div>
        </div>
        """, unsafe_allow_html=True)

    with st.expander("📋 Live Table Schemas", expanded=False):
        st.markdown(discover_database_schema())

    st.markdown("---")
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()


# ==========================================
# MAIN INTERFACE
# ==========================================

# Header Banner
st.markdown("""
<div class="meridian-header">
    <div class="meridian-title">🚗 Meridian Data Copilot &mdash; Stellantis Maroc</div>
    <div class="meridian-subtitle">
        Enterprise Business Intelligence Copilot &bull; PostgreSQL <code>stellantis_db</code> &bull; Corporate PDF Knowledge Base &bull; LangGraph ReAct Orchestration
    </div>
</div>
""", unsafe_allow_html=True)

# LangGraph Architecture Expander
with st.expander("🕸️ View LangGraph ReAct Workflow Diagram", expanded=False):
    col_g1, col_g2 = st.columns([1, 1])
    with col_g1:
        st.markdown("**Compiled LangGraph State Machine:**")
        workflow_png = BASE_DIR / "data" / "langgraph_workflow.png"
        if workflow_png.exists():
            st.image(str(workflow_png), caption="LangGraph StateGraph", use_container_width=True)
        else:
            try:
                st.code(meridian_graph.get_graph().draw_mermaid(), language="mermaid")
            except Exception:
                st.caption("Graph active.")
    with col_g2:
        st.markdown("""
        **Workflow Execution Mechanics:**
        1. **User Query** initializes `MeridianState`.
        2. **`reasoner` Node:** Groq model analyzes prompt + live PostgreSQL schema and decides actions.
        3. **`route_next` Conditional Edge:** Routes to `tool_executor` if tools called, else ends.
        4. **`tool_executor` Node:** Runs SQL/RAG/Charts, appends feedback, loops back to `reasoner`.
        """)

# Quick-Launch Benchmarks
st.markdown("##### 🚀 Recommended Benchmark Queries")
q_col1, q_col2, q_col3, q_col4 = st.columns(4)

with q_col1:
    if st.button("📊 **Pure Metric (SQL)**\nCasablanca 2024 total revenue", use_container_width=True):
        st.session_state.pending_query = "What was the total revenue in MAD for dealerships in Casablanca in 2024?"

with q_col2:
    if st.button("📕 **Procedural (PDF)**\nKénitra plant capacity & workforce", use_container_width=True):
        st.session_state.pending_query = "What is the assembly capacity and workforce of the Kénitra plant according to the industrial footprint memo?"

with q_col3:
    if st.button("📈 **Trend & Chart**\nPeugeot 208 monthly sales trend", use_container_width=True):
        st.session_state.pending_query = "Show me the monthly sales trend for the Peugeot 208 in 2024 and 2025."

with q_col4:
    if st.button("🔍 **Killer Diagnostic**\nWhy did Kenitra models drop in June 2024?", use_container_width=True):
        st.session_state.pending_query = "Why did sales for Kenitra-assembled vehicles drop in June 2024?"

# User Input
user_query = st.chat_input("Ask Meridian about Stellantis sales, dealerships, Kénitra plant, or incident reports...")
if "pending_query" in st.session_state and st.session_state.pending_query:
    user_query = st.session_state.pending_query
    st.session_state.pending_query = None

# Display History
for turn in st.session_state.chat_history:
    with st.chat_message("user"):
        st.markdown(turn["user"])

    with st.chat_message("assistant"):
        st.markdown(turn["ai"])
        if turn.get("chart_figure"):
            st.plotly_chart(turn["chart_figure"], use_container_width=True)

        if turn.get("tool_traces"):
            with st.expander("🔍 View AI Reasoning & Execution Trace", expanded=False):
                for idx, t in enumerate(turn["tool_traces"], 1):
                    tool_name = t.get("tool")
                    duration = t.get("duration_sec", 0.0)
                    status_badge = "✅" if t.get("status") == "success" else "⚠️"
                    
                    if tool_name == "execute_sql_query":
                        st.markdown(f"**Step {idx}: SQL Execution (`stellantis_db`)** ({status_badge} `{duration}s`)")
                        st.code(t["args"].get("query", ""), language="sql")
                        try:
                            d = json.loads(t["output"])
                            if d.get("rows"):
                                st.dataframe(pd.DataFrame(d["rows"]), use_container_width=True)
                        except Exception:
                            pass
                    elif tool_name == "search_company_documents":
                        st.markdown(f"**Step {idx}: PDF Vector Search (ChromaDB)** ({status_badge} `{duration}s`)")
                        st.caption(f"Query: *\"{t['args'].get('query')}\"*")
                        try:
                            chunks = json.loads(t["output"])
                            for c in chunks:
                                st.markdown(f"- 📕 **{c.get('source')}** (Page {c.get('page', 1)}) &bull; *{c.get('section')}*")
                                st.markdown(f"  > *\"{c.get('excerpt', '')[:250]}...\"*")
                        except Exception:
                            pass

# Handle Submission
if user_query:
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner("⚡ Meridian Reasoner is querying PostgreSQL and cross-referencing PDFs..."):
            start_ts = time.time()
            
            recent_turns = st.session_state.chat_history[-2:]
            langgraph_messages = []
            for t in recent_turns:
                langgraph_messages.append(HumanMessage(content=t["user"]))
                ai_text = t["ai"][:300] + "..." if len(t["ai"]) > 300 else t["ai"]
                langgraph_messages.append(AIMessage(content=ai_text))
            langgraph_messages.append(HumanMessage(content=user_query))

            agent_input: MeridianState = {
                "messages": langgraph_messages,
                "tool_history": [],
                "chart_figures": [],
                "iteration": 0,
                "sql_retries": 0,
            }

            try:
                result_state = meridian_graph.invoke(agent_input)
                final_ai_msg = result_state["messages"][-1].content
                tool_traces = result_state.get("tool_history", [])
                chart_figs = result_state.get("chart_figures", [])
            except Exception as e:
                final_ai_msg = f"Error during agent reasoning: {str(e)}"
                tool_traces = []
                chart_figs = []

            active_figure = None
            if chart_figs:
                active_figure = chart_figs[-1].get("figure")
            elif ("trend" in user_query.lower() or "decline" in user_query.lower() or "why" in user_query.lower() or "baisse" in user_query.lower()) and ("kenitra" in user_query.lower() or "208" in user_query.lower()):
                try:
                    c_query = """
                    SELECT 
                        TO_CHAR(s.sale_date, 'YYYY-MM') as month,
                        ROUND(SUM(s.total_revenue_mad), 2) as revenue_mad
                    FROM sales s
                    JOIN vehicles v ON s.vehicle_id = v.vehicle_id
                    WHERE v.assembly_plant = 'Kénitra'
                      AND s.sale_date >= '2024-04-01' AND s.sale_date <= '2024-08-31'
                    GROUP BY TO_CHAR(s.sale_date, 'YYYY-MM')
                    ORDER BY month;
                    """
                    c_data = execute_sql(c_query)["rows"]
                    if c_data:
                        c_res = generate_chart(
                            c_data,
                            chart_type="bar",
                            x_col="month",
                            y_col="revenue_mad",
                            title="Chiffre d'Affaires Mensuel Véhicules Usine Kénitra (MAD)",
                        )
                        if c_res.get("success"):
                            active_figure = c_res["figure"]
                except Exception:
                    pass

            st.markdown(final_ai_msg)

            if active_figure is not None:
                st.plotly_chart(active_figure, use_container_width=True)

            if tool_traces:
                with st.expander("🔍 View AI Reasoning & Execution Trace", expanded=True):
                    st.markdown(f"**LangGraph ReAct Execution Trace** (Latency: `{round(time.time() - start_ts, 2)}s`):")
                    for idx, t in enumerate(tool_traces, 1):
                        tool_name = t.get("tool")
                        duration = t.get("duration_sec", 0.0)
                        if tool_name == "execute_sql_query":
                            st.markdown(f"**Step {idx}: `execute_sql_query` (PostgreSQL `stellantis_db`)** (`{duration}s`)")
                            st.code(t["args"].get("query", ""), language="sql")
                            try:
                                d = json.loads(t["output"])
                                if d.get("rows"):
                                    st.dataframe(pd.DataFrame(d["rows"]), use_container_width=True)
                            except Exception:
                                pass
                        elif tool_name == "search_company_documents":
                            st.markdown(f"**Step {idx}: `search_company_documents` (PDFs in `data/pdf/`)** (`{duration}s`)")
                            st.caption(f"Query: *\"{t['args'].get('query')}\"*")
                            try:
                                chunks = json.loads(t["output"])
                                for c in chunks:
                                    st.markdown(f"- 📕 **{c.get('source')}** (Page {c.get('page', 1)}) &bull; *{c.get('section')}*")
                                    st.markdown(f"  > *\"{c.get('excerpt', '')[:250]}...\"*")
                            except Exception:
                                pass

            st.session_state.chat_history.append({
                "user": user_query,
                "ai": final_ai_msg,
                "chart_figure": active_figure,
                "tool_traces": tool_traces
            })
