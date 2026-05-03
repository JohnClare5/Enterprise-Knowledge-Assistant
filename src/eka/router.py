from __future__ import annotations

from langgraph.graph import END, StateGraph

from eka.generation import answer_from_evidence
from eka.memory import memory
from eka.retrieval import HybridRetriever
from eka.schemas import AssistantResponse, RouteType, WorkflowState
from eka.sql_tool import run_sql_question


SQL_HINTS = ("销售额", "报销最多", "报销最高", "哪个部门报销", "blocked", "阻塞", "项目状态")
CLARIFY_HINTS = ("这个", "那个", "这些", "他们", "它", "怎么办", "怎么处理")
OUT_OF_SCOPE_HINTS = ("天气", "股票", "彩票", "娱乐新闻")
DESTRUCTIVE_SQL_HINTS = ("删除", "删掉", "drop", "truncate", "update", "insert", "alter")


def classify_question(question: str) -> RouteType:
    stripped = question.strip()
    if not stripped or len(stripped) < 3:
        return RouteType.CLARIFY
    if any(hint in stripped.lower() for hint in DESTRUCTIVE_SQL_HINTS):
        return RouteType.REFUSE
    if any(hint in stripped for hint in OUT_OF_SCOPE_HINTS):
        return RouteType.REFUSE
    if any(hint in stripped for hint in SQL_HINTS):
        return RouteType.SQL
    if stripped in CLARIFY_HINTS:
        return RouteType.CLARIFY
    return RouteType.DOCUMENT_QA


class EnterpriseAssistant:
    def __init__(self, retrieval_strategy: str | None = None) -> None:
        self.retriever = HybridRetriever(strategy=retrieval_strategy)
        self.graph = self._build_graph()

    def ask(self, question: str, session_id: str = "default") -> AssistantResponse:
        state = WorkflowState(question=question, session_id=session_id)
        final = self.graph.invoke(state)
        if isinstance(final, dict):
            response = final["response"]
        else:
            response = final.response
        memory.add(session_id, question, response.answer, response.route_type)
        return response

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("route", self._route)
        graph.add_node("document_qa", self._document_qa)
        graph.add_node("sql", self._sql)
        graph.add_node("clarify", self._clarify)
        graph.add_node("refuse", self._refuse)
        graph.set_entry_point("route")
        graph.add_conditional_edges(
            "route",
            lambda state: state.route_type.value,
            {
                RouteType.DOCUMENT_QA.value: "document_qa",
                RouteType.SQL.value: "sql",
                RouteType.CLARIFY.value: "clarify",
                RouteType.REFUSE.value: "refuse",
            },
        )
        graph.add_edge("document_qa", END)
        graph.add_edge("sql", END)
        graph.add_edge("clarify", END)
        graph.add_edge("refuse", END)
        return graph.compile()

    def _route(self, state: WorkflowState) -> WorkflowState:
        state.route_type = classify_question(state.question)
        return state

    def _document_qa(self, state: WorkflowState) -> WorkflowState:
        state.rewritten_query = self.retriever.rewrite_query(state.question, state.session_id)
        state.evidences = self.retriever.retrieve(state.question, state.session_id)
        state.response = answer_from_evidence(state.question, state.evidences)
        state.response.trace = {
            **state.response.trace,
            "rewritten_query": state.rewritten_query,
            "retrieval_strategy": self.retriever.strategy,
            "evidence_count": len(state.evidences),
            "retriever": self.retriever.last_trace,
        }
        return state

    def _sql(self, state: WorkflowState) -> WorkflowState:
        state.response = run_sql_question(state.question)
        state.response.trace = {**state.response.trace, "router": "sql_tool"}
        return state

    def _clarify(self, state: WorkflowState) -> WorkflowState:
        state.response = AssistantResponse(
            answer="我需要再确认一下：你想查询哪一类制度、时间范围或业务指标？",
            route_type=RouteType.CLARIFY,
            needs_clarification=True,
            refusal_reason="ambiguous_question",
        )
        state.response.trace = {"router": "clarify"}
        return state

    def _refuse(self, state: WorkflowState) -> WorkflowState:
        state.response = AssistantResponse(
            answer="我无法回答这个问题。它不属于当前企业知识库或结构化业务数据范围。",
            route_type=RouteType.REFUSE,
            refusal_reason="out_of_scope",
        )
        state.response.trace = {"router": "refuse"}
        return state
