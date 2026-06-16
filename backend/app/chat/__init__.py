"""Chat assistant package.

This package implements the standalone REST-based chat service that allows
users to describe their portfolio optimization goals in natural language.

Sub-modules:
    schemas  — Pydantic v2 request/response models for the chat API.
    service  — ChatService: session lifecycle management and orchestration.
    llm      — LLMSlotFiller: GPT-4o structured-output slot extraction.
    router   — FastAPI router mounted at /api/v1/chat.
"""
