"""请求 / 响应模型（Day 1：先对齐真实项目字段语义）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: str = Field(..., description="user | assistant")
    content: str


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户问题")
    session_id: str = Field(default="", description="多轮会话 ID，空则服务端生成")
    history: list[ChatTurn] = Field(default_factory=list, description="可选历史轮次")


class SourceItem(BaseModel):
    content: str = ""
    source: str = ""
    score: float = 0.0
    retrieval_type: str = "mock"


class QuestionResponse(BaseModel):
    answer: str
    confidence: float = 0.0
    sources: list[SourceItem] = Field(default_factory=list)
    session_id: str = ""
    grounded: bool = False
    intent: str = "unknown"
    mock: bool = True
    note: str = ""


class HealthResponse(BaseModel):
    status: str
    phase: str
    day: int
    components: dict[str, str]
