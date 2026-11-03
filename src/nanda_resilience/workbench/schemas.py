from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunRequest(StrictModel):
    mode: Literal["research", "evaluation"]
    question: str = Field(min_length=12, max_length=4000)
    sources: list[str] = Field(default_factory=list, max_length=4)
    reference: str = Field(default="", max_length=12000)
    rubric: str = Field(default="", max_length=4000)
    cases: int = Field(default=2, ge=1, le=3)
    policy: Literal["price", "dependency", "load", "random"] = "dependency"
    consent: Literal[True]

    @field_validator("consent", mode="before")
    @classmethod
    def require_consent(cls, value):
        if value is not True:
            raise ValueError("Explicit approval of model calls and possible charges or quota usage is required.")
        return value

    @field_validator("question")
    @classmethod
    def meaningful_question(cls, value):
        if len(value.strip()) < 12:
            raise ValueError("Provide a specific task of at least 12 characters.")
        return value.strip()


class SourceNotes(StrictModel):
    summary: str
    claims: list[str] = Field(max_length=8)
    quotes: list[str] = Field(max_length=5)


class Brief(StrictModel):
    title: str
    answer: str
    findings: list[str] = Field(max_length=12)
    limitations: list[str] = Field(max_length=8)
    source_ids: list[str]


class Review(StrictModel):
    assessment: Literal["supported", "mixed", "unsupported"]
    issues: list[str] = Field(max_length=10)
    explanation: str


class Challenge(StrictModel):
    name: str
    prompt: str
    failure_type: str
    expected_behavior: str


class Challenges(StrictModel):
    cases: list[Challenge] = Field(min_length=1, max_length=3)


class Answer(StrictModel):
    answer: str


class Judgment(StrictModel):
    verdict: Literal["pass", "fail", "uncertain"]
    failure_type: str
    explanation: str
    evidence_quote: str


class ResourceControl(StrictModel):
    resource: str
    disabled: bool


class Draft(StrictModel):
    text: str = Field(max_length=30000)
