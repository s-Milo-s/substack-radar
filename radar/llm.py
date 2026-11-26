"""Anthropic wrapper: voice.md in every system prompt, schema-validated JSON out.

ask() never raises. Bad JSON, a schema mismatch, a failed `check`, a blocklisted
term, a refusal or an API error each get exactly one retry; after that the caller
gets None (or, for `check` problems only, the object so it can drop bad items).
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from . import blocklist

log = logging.getLogger("radar.llm")

MODEL = os.environ.get("RADAR_MODEL", "claude-sonnet-5-5")
VOICE = (Path(__file__).resolve().parent.parent / "voice.md").read_text()
SYSTEM = VOICE + "\n\nReply with valid JSON only, matching the requested schema. No prose, no code fences."

T = TypeVar("T", bound=BaseModel)
_client: anthropic.Anthropic | None = None


class Refused(Exception):
    pass


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    return _client


def _complete(prompt: str, schema: type[BaseModel], max_tokens: int) -> str:
    """One API call; returns the raw text. Tests replace this function."""
    msg = client().messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
    )
    if msg.stop_reason == "refusal":
        raise Refused("model declined")
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def _strip_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())


def _strings(obj: object) -> str:
    """All string values in a model, joined, for the blocklist scan."""
    if isinstance(obj, BaseModel):
        return _strings(obj.model_dump())
    if isinstance(obj, dict):
        return "\n".join(_strings(v) for v in obj.values())
    if isinstance(obj, list):
        return "\n".join(_strings(v) for v in obj)
    return obj if isinstance(obj, str) else ""


def ask(prompt: str, schema: type[T], *, check: Callable[[T], list[str]] | None = None,
        max_tokens: int = 4000, terms: list[str] | None = None) -> T | None:
    terms = blocklist.load() if terms is None else terms
    feedback = ""
    for attempt in (1, 2):
        try:
            text = _complete(prompt + feedback, schema, max_tokens)
        except (anthropic.APIError, Refused) as e:
            log.warning("LLM call failed (attempt %d): %s", attempt, e)
            feedback = ""
            continue
        try:
            obj = schema.model_validate_json(_strip_fences(text))
        except ValidationError as e:
            log.warning("LLM returned invalid %s (attempt %d): %s",
                        schema.__name__, attempt, str(e).splitlines()[0])
            feedback = ("\n\nYour previous reply was not valid JSON for the schema. "
                        "Return only the JSON object.")
            continue
        if blocklist.hits(_strings(obj), terms):
            # don't echo the terms back to the model: they're the secret
            log.warning("LLM draft hit the pseudonymity blocklist (attempt %d)", attempt)
            feedback = ("\n\nYour previous draft included a banned identifying term. Rewrite it "
                        "with nothing that could identify the writer (name, employer, its "
                        "industry, location).")
            continue
        problems = check(obj) if check else []
        if problems and attempt == 1:
            log.warning("LLM output failed checks, retrying: %s", "; ".join(problems))
            feedback = "\n\nFix these problems in your previous reply: " + "; ".join(problems)
            continue
        if problems:
            log.warning("LLM output still failing checks, dropping bad items: %s", "; ".join(problems))
        return obj
    log.error("LLM gave no usable %s after 2 attempts; dropping that section", schema.__name__)
    return None
