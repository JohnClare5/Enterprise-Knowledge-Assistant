from __future__ import annotations

import sys
import os
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from eka.router import EnterpriseAssistant
from eka.evaluation import run_eval_compare, save_eval_compare


st.set_page_config(page_title="Enterprise Knowledge Assistant", layout="wide")
st.title("Enterprise Knowledge Assistant")

with st.sidebar:
    page = st.radio("Page", ["Chat", "Eval"], horizontal=True)
    strategy = st.selectbox(
        "Retrieval",
        ["vector_bm25_rerank", "vector_bm25", "vector", "hybrid_rerank", "hybrid", "bm25", "tfidf"],
        index=0,
    )
    generation = st.selectbox("Generation", ["extractive", "deepseek", "openai"], index=0)
    os.environ["EKA_GENERATION_MODE"] = generation
    show_chunks = st.toggle("Show evidence", value=True)
    show_trace = st.toggle("Show trace", value=True)

if "assistant" not in st.session_state:
    st.session_state.assistant = EnterpriseAssistant(retrieval_strategy=strategy)
    st.session_state.strategy = strategy
if st.session_state.get("strategy") != strategy:
    st.session_state.assistant = EnterpriseAssistant(retrieval_strategy=strategy)
    st.session_state.strategy = strategy
if "messages" not in st.session_state:
    st.session_state.messages = []

if page == "Chat":
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("输入企业制度、流程或业务数据问题")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        response = st.session_state.assistant.ask(question, session_id="streamlit")
        with st.chat_message("assistant"):
            st.markdown(response.answer)
            cols = st.columns(4)
            cols[0].metric("Route", response.route_type.value)
            cols[1].metric("Confidence", f"{response.confidence:.2f}")
            cols[2].metric("Grounded", "yes" if response.grounded else "no")
            cols[3].metric("Citations", len(response.citations))
            if response.citations:
                st.caption("引用")
                for citation in response.citations:
                    source = citation.url or citation.source
                    st.write(f"- {citation.doc_name} / {citation.section} / {source}")
            if response.sql:
                st.code(response.sql, language="sql")
                st.json(response.raw_result)
            if show_trace:
                with st.expander("Workflow Trace", expanded=True):
                    st.json(response.trace)
            if show_chunks and response.retrieved_chunks:
                with st.expander("Evidence", expanded=False):
                    for ev in response.retrieved_chunks:
                        st.markdown(
                            f"**#{ev.rank} {ev.chunk.doc_name} / {ev.chunk.section}** "
                            f"`{ev.score:.3f}` `{ev.retrieval_method}`"
                        )
                        meta_cols = st.columns(3)
                        meta_cols[0].caption(ev.chunk.metadata.get("source_type", "unknown"))
                        meta_cols[1].caption(ev.chunk.metadata.get("heading_path", ev.chunk.section))
                        meta_cols[2].caption(ev.chunk.metadata.get("url") or ev.chunk.source)
                        st.write(ev.chunk.text)
        st.session_state.messages.append({"role": "assistant", "content": response.answer})
else:
    st.subheader("Offline Evaluation")
    strategies_text = st.text_input(
        "Strategies",
        value="bm25,tfidf,hybrid,hybrid_rerank",
    )
    if st.button("Run Compare", type="primary"):
        strategies = [item.strip() for item in strategies_text.split(",") if item.strip()]
        result = run_eval_compare(strategies)
        json_path, md_path = save_eval_compare(result)
        st.success(f"Saved {json_path.name} and {md_path.name}")
        rows = [
            {
                "strategy": item["retrieval_strategy"],
                "route_accuracy": item["route_accuracy"],
                "hit@k": item["retrieval_hit_at_k"],
                "mrr": item["mrr"],
                "citation_rate": item["citation_rate"],
                "answer_hit": item["answer_contains_expected"],
            }
            for item in result["results"]
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        with st.expander("Full Compare JSON", expanded=False):
            st.json(result)
