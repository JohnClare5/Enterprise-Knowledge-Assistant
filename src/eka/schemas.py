from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RouteType(str, Enum):
    DOCUMENT_QA = "document_qa"
    SQL = "sql"
    CLARIFY = "clarify"
    REFUSE = "refuse"


class RawDocument(BaseModel):
    doc_id: str
    doc_name: str
    source: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    doc_name: str
    section: str
    source: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    chunk: Chunk
    score: float
    rank: int
    retrieval_method: str


class Citation(BaseModel):
    doc_name: str
    section: str
    source: str
    chunk_id: str
    source_type: str | None = None
    url: str | None = None


class AssistantResponse(BaseModel):
    answer: str
    route_type: RouteType
    citations: list[Citation] = Field(default_factory=list)
    retrieved_chunks: list[Evidence] = Field(default_factory=list)
    needs_clarification: bool = False
    refusal_reason: str | None = None
    confidence: float = 0.0
    grounded: bool = False
    sql: str | None = None
    raw_result: Any | None = None
    trace: dict[str, Any] = Field(default_factory=dict)


class ConversationTurn(BaseModel):
    user: str
    assistant: str
    route_type: RouteType
    topic_hint: str | None = None


class WorkflowState(BaseModel):
    question: str
    session_id: str = "default"
    rewritten_query: str | None = None
    route_type: RouteType | None = None
    evidences: list[Evidence] = Field(default_factory=list)
    response: AssistantResponse | None = None
    needs_clarification: bool = False
    refusal_reason: str | None = None
    sql: str | None = None
    sql_result: Any | None = None
