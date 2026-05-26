"""
main.py — FastAPI service for SHL Assessment Advisor
Endpoints:
  GET  /health   → {"status": "ok"}
  POST /chat     → {reply, recommendations, end_of_conversation}
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure catalog_store is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "catalog"))

sys.path.insert(0, str(Path(__file__).parent))

from agent import run_agent  # noqa: E402

# --------------------------------------------------------------------------- #
# Pydantic schemas (must match the assignment spec exactly)                   #
# --------------------------------------------------------------------------- #


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[Message] = Field(..., min_length=1)


class Recommendation(BaseModel):
    name: str
    url: str
    test_type: str


class ChatResponse(BaseModel):
    reply: str
    recommendations: list[Recommendation]
    end_of_conversation: bool


# --------------------------------------------------------------------------- #
# App                                                                          #
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="SHL Assessment Advisor",
    description="Conversational agent for SHL Individual Test Solutions",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # Convert Pydantic models to plain dicts for the agent
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    if not messages:
        raise HTTPException(status_code=400, detail="messages cannot be empty")

    result = run_agent(messages)

    return ChatResponse(
        reply=result["reply"],
        recommendations=[
            Recommendation(
                name=r["name"],
                url=r["url"],
                test_type=r.get("test_type", "A"),
            )
            for r in result.get("recommendations", [])
        ],
        end_of_conversation=result.get("end_of_conversation", False),
    )
