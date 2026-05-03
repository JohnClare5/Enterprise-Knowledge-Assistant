from __future__ import annotations

from collections import defaultdict, deque

from eka.schemas import ConversationTurn, RouteType
from eka.text import normalize_question


class ConversationMemory:
    def __init__(self, max_turns: int = 6) -> None:
        self.max_turns = max_turns
        self._store: dict[str, deque[ConversationTurn]] = defaultdict(lambda: deque(maxlen=max_turns))

    def add(self, session_id: str, question: str, answer: str, route_type: RouteType) -> None:
        self._store[session_id].append(
            ConversationTurn(
                user=question,
                assistant=answer,
                route_type=route_type,
                topic_hint=self.topic_hint(session_id, fallback=question),
            )
        )

    def recent(self, session_id: str) -> list[ConversationTurn]:
        return list(self._store[session_id])

    def topic_hint(self, session_id: str, fallback: str | None = None) -> str | None:
        turns = self.recent(session_id)
        for turn in reversed(turns):
            if turn.route_type == RouteType.DOCUMENT_QA:
                return normalize_question(turn.user)[:80]
        return normalize_question(fallback)[:80] if fallback else None


memory = ConversationMemory()

