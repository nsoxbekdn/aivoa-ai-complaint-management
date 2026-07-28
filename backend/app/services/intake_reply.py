"""Natural-language phrasing for the intake assistant's replies.

Every decision in an intake turn — what was recorded, what was rejected, what to ask next — is
made deterministically before this module runs. This layer only chooses the *words*, so the
assistant can sound like a person without ever being trusted to change the record.

Two things can send a turn back to the deterministic sentence: the provider being unavailable,
and a reply that states a number nobody supplied. Both are handled here, so the caller always
gets a usable string.
"""

from __future__ import annotations

import logging
import re

from app.config import get_settings
from app.llm.groq_client import LLMError, complete_text
from app.llm.prompts import INTAKE_REPLY_SYSTEM

logger = logging.getLogger(__name__)

MAX_REPLY_CHARS = 420
# Two digits or more: a hallucinated batch number, quantity, year or date shows up here. Single
# digits are too common in ordinary prose ("1 more detail") to be worth policing.
_NUMBERISH = re.compile(r"\d{2,}")
_MARKDOWN = re.compile(r"[*_`#>]+")


def phrase_reply(
    reporter_message: str,
    facts: dict[str, str],
    next_question: str | None,
    fallback: str,
) -> str:
    """Say ``facts`` in natural language, or return ``fallback`` unchanged if that is not safe.

    ``facts`` must already be human-readable and must contain every value the reply is allowed
    to mention: the model is told to state nothing else, and the grounding check below enforces
    that for anything numeric.
    """
    brief = "\n".join(f"{key}: {value}" for key, value in facts.items() if value)
    if next_question:
        brief = f"{brief}\nNEXT QUESTION: {next_question}".strip()
    if not brief:
        return fallback

    user_prompt = (
        f"FACTS:\n{brief}\n\n"
        f"THE REPORTER JUST SAID:\n<complaint>{reporter_message}</complaint>\n\n"
        "Write the assistant's reply now."
    )
    try:
        reply = complete_text(
            INTAKE_REPLY_SYSTEM,
            user_prompt,
            max_tokens=400,
            model=get_settings().groq_reply_model or None,
        )
    except LLMError:
        # The turn itself already succeeded; only the wording failed. Nothing is lost.
        logger.warning("Intake reply phrasing unavailable; using the deterministic sentence.")
        return fallback

    reply = _tidy(reply)
    if not reply or not _is_grounded(reply, brief, reporter_message):
        logger.warning("Intake reply phrasing rejected; using the deterministic sentence.")
        return fallback
    return reply


def _tidy(reply: str) -> str:
    """Strip the formatting a chat model reaches for, and cap the length."""
    reply = _MARKDOWN.sub("", reply).strip().strip('"').strip()
    reply = re.sub(r"\s+", " ", reply)
    if len(reply) <= MAX_REPLY_CHARS:
        return reply
    cut = reply[:MAX_REPLY_CHARS]
    stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[: stop + 1].strip() if stop > 0 else cut.rstrip() + "…"


def _is_grounded(reply: str, brief: str, reporter_message: str) -> bool:
    """Reject a reply that states a number nobody supplied.

    The same principle as ``_ground_fields`` on the extraction path: the prompt asks the model
    not to invent, and code is what guarantees it. A wrong batch number read back to a reporter
    is worse than a plain sentence.
    """
    source = f"{brief} {reporter_message}"
    return all(number in source for number in _NUMBERISH.findall(reply))


def demo() -> None:  # pragma: no cover - runnable self-check, no network
    assert _tidy("**Got it.**  \nI recorded 6 bottles.") == "Got it. I recorded 6 bottles."
    assert _is_grounded("I recorded batch CC26045.", "RECORDED: batch CC26045", "")
    assert _is_grounded("I recorded that batch.", "", "batch is CC26045")
    assert not _is_grounded("I recorded batch CC99999.", "RECORDED: batch CC26045", "")
    long_reply = "One sentence here. " * 40
    assert len(_tidy(long_reply)) <= MAX_REPLY_CHARS
    print("intake_reply self-check passed")


if __name__ == "__main__":  # pragma: no cover
    demo()
