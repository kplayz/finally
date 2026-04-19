"""Chat endpoint. Thin route — all LLM logic lives in app.llm."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import ChatRequest, ChatResponse
from ..llm import handle_chat

router = APIRouter()


@router.post("/api/chat")
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    provider = getattr(request.app.state, "market", None)
    return await handle_chat(body.message, provider=provider)
