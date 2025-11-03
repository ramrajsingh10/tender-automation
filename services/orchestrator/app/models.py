from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PlaybookQuestion(BaseModel):
    id: str
    display: str = Field(alias="display")
    prompt: str
    page_size: int | None = Field(default=None, alias="pageSize")


class RagPlaybookRequest(BaseModel):
    tenderId: str
    gcsUris: List[str] = Field(default_factory=list)
    questions: Optional[List[PlaybookQuestion]] = None
    ragFileIds: List[str] | None = None
    forgetAfterRun: bool = False
    pageSize: int | None = None

    class Config:
        populate_by_name = True


class RagCitation(BaseModel):
    startIndex: int | None = None
    endIndex: int | None = None
    sources: List[Dict[str, str]] = Field(default_factory=list)


class AnswerEvidence(BaseModel):
    docId: str | None = None
    docTitle: str | None = None
    docUri: str | None = None
    pageLabel: str | None = None
    snippet: str | None = None
    distance: float | None = None


class RagAnswer(BaseModel):
    text: str
    citations: List[RagCitation] = Field(default_factory=list)
    evidence: List[AnswerEvidence] = Field(default_factory=list)


class RagDocument(BaseModel):
    id: str | None = None
    uri: str | None = None
    title: str | None = None
    snippet: str | None = None
    metadata: Dict[str, object] | None = None


class RagQueryResponse(BaseModel):
    answers: List[RagAnswer] = Field(default_factory=list)
    documents: List[RagDocument] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


class RagQueryRequest(BaseModel):
    tenderId: str
    question: str
    conversationId: str | None = None
    pageSize: int | None = None
    gcsUris: List[str] = Field(default_factory=list)
    ragFileIds: List[str] | None = None

    class Config:
        populate_by_name = True


class RagPlaybookResult(BaseModel):
    questionId: str
    question: str
    answers: List[RagAnswer]
    documents: List[RagDocument]


class RagPlaybookResponse(BaseModel):
    results: List[RagPlaybookResult]
    outputUri: Optional[str] = None
    ragFiles: List[Dict[str, Any]] = Field(default_factory=list)


class RagDeleteRequest(BaseModel):
    ragFileIds: List[str] = Field(default_factory=list)
