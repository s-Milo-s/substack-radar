"""Pydantic schemas for every LLM response. Anything that doesn't validate is retried once."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Comment(BaseModel):
    post: int = Field(description="index of the post in the list")
    why: str = Field(description="one line: why this post, for the writer's audience")
    comment: str = Field(description="draft comment, 1-3 sentences, adds one specific thing")


class Restack(BaseModel):
    post: int
    take: str = Field(description="one-line opinion to restack with")


class NewsHook(BaseModel):
    news: int = Field(description="index of the news item")
    note: str = Field(description="Note that re-shares the essay off this news, under 280 chars")


class DailyPlan(BaseModel):
    comments: list[Comment] = Field(default_factory=list)
    restack: Restack | None = None
    reactive_note: str | None = None
    news_hooks: list[NewsHook] = Field(default_factory=list)


class NoteList(BaseModel):
    notes: list[str]


class Reply(BaseModel):
    comment: str = Field(description="first 80 chars of the reader's comment")
    reply: str


class Replies(BaseModel):
    replies: list[Reply]


class Pick(BaseModel):
    i: int = Field(description="candidate index")
    fit: int = Field(description="topical fit 1-10")
    tier: Literal["anchor", "peer", "news"]
    lane: str = Field(description="one of the configured lanes, or 'other'")
    why: str = Field(description="one line")


class Picks(BaseModel):
    picks: list[Pick]
