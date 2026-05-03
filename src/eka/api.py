from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from eka.router import EnterpriseAssistant


app = FastAPI(title="Enterprise Knowledge Assistant")
assistant: EnterpriseAssistant | None = None


class AskRequest(BaseModel):
    question: str
    session_id: str = "api"


@app.on_event("startup")
def startup() -> None:
    global assistant
    assistant = EnterpriseAssistant()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask")
def ask(req: AskRequest):
    assert assistant is not None
    return assistant.ask(req.question, req.session_id).model_dump()

