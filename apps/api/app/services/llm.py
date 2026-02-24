"""
LLM service for:
1. Clause explanation: {clause_plain, comment_plain, risk_plain}
2. doc_kind detection: classify document type from first-page text

Supports both Gemini (free tier) and OpenAI.
Set GEMINI_API_KEY in .env to use Gemini; otherwise falls back to OpenAI.
"""

from __future__ import annotations

import json
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

DOC_KINDS = ["T&Cs", "DPA", "AUP", "SLA", "Order Form", "NDA", "Others"]

EXPLANATION_SYSTEM_PROMPT = """You are a legal analyst assistant helping procurement teams understand contract clauses.
You will be given a clause excerpt (with surrounding context), the specific word or phrase the reviewer flagged, and their comment(s).
Respond ONLY with a JSON object (no markdown, no extra text) with exactly these three keys:
- "clause_plain": Plain English explanation of what the full clause means and requires, focusing on the flagged phrase in context (2-4 sentences)
- "comment_plain": Plain English summary of what the reviewer is flagging about the specific phrase (2-3 sentences)
- "risk_plain": Plain English explanation of the potential risk or impact to the organisation if this clause is accepted as-is (2-3 sentences)

Important: The FLAGGED PHRASE may be a single word or short phrase within a longer clause. Explain it in the context of the surrounding text. Do not give legal advice. Be concise and accessible to non-lawyers."""

DOCTYPE_SYSTEM_PROMPT = f"""You are a document classifier. Given the first few paragraphs of a legal/commercial document,
identify the document type. Respond ONLY with one of these exact strings (no quotes, no explanation):
{', '.join(DOC_KINDS)}

If unsure, respond with: Others"""


def _chat(model: str, system: str, user: str, temperature: float = 0.3, json_mode: bool = False) -> str:
    """
    Send a chat request and return the response text.
    Uses native Gemini SDK when GEMINI_API_KEY is set, otherwise OpenAI.
    """
    if settings.gemini_api_key:
        import google.generativeai as genai
        import google.generativeai.types as genai_types
        genai.configure(api_key=settings.gemini_api_key)
        gemini_model = genai.GenerativeModel(
            model_name=model,
            system_instruction=system,
        )
        cfg = genai_types.GenerationConfig(temperature=temperature)
        if json_mode:
            cfg = genai_types.GenerationConfig(
                temperature=temperature,
                response_mime_type="application/json",
            )
        response = gemini_model.generate_content(user, generation_config=cfg)
        return response.text or ""
    else:
        import openai
        client = openai.OpenAI(api_key=settings.openai_api_key)
        kwargs: dict = dict(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


def explain_clause(clause_text: str, comment_texts: list[str], anchor_text: str = "") -> dict:
    """
    Generate plain-English explanation for a clause + its comments.
    Returns {clause_plain, comment_plain, risk_plain}.
    anchor_text is the specific word/phrase the reviewer highlighted.
    """
    if settings.disable_llm:
        return {
            "clause_plain": "[LLM disabled]",
            "comment_plain": "[LLM disabled]",
            "risk_plain": "[LLM disabled]",
        }

    comments_block = "\n\n".join(
        f"Comment {i+1}: {c}" for i, c in enumerate(comment_texts)
    )
    flagged_line = f'\nFLAGGED PHRASE (the specific word or phrase the reviewer highlighted):\n"{anchor_text}"\n' if anchor_text.strip() else ""
    user_prompt = f"""CLAUSE (with surrounding context):
{clause_text}
{flagged_line}
REVIEWER COMMENT(S):
{comments_block}"""

    for attempt in range(2):
        try:
            raw = _chat(
                model=settings.explanation_model,
                system=EXPLANATION_SYSTEM_PROMPT,
                user=user_prompt,
                temperature=0.3,
                json_mode=True,
            )
            parsed = json.loads(raw)

            if all(k in parsed for k in ("clause_plain", "comment_plain", "risk_plain")):
                return {
                    "clause_plain": str(parsed["clause_plain"]),
                    "comment_plain": str(parsed["comment_plain"]),
                    "risk_plain": str(parsed["risk_plain"]),
                }
            if attempt == 0:
                logger.warning("LLM explanation missing keys, retrying...")
        except (json.JSONDecodeError, Exception) as exc:
            if attempt == 0:
                logger.warning("LLM explanation attempt %d failed: %s", attempt + 1, exc)
            else:
                logger.error("LLM explanation failed after retry: %s", exc)
                raise

    raise ValueError("LLM explanation returned invalid JSON after 2 attempts")


def detect_doc_kind(first_page_text: str) -> str | None:
    """
    Detect document kind from first-page text.
    Returns one of DOC_KINDS or None if DISABLE_LLM.
    """
    if settings.disable_llm:
        return None

    if not first_page_text or len(first_page_text.strip()) < 20:
        return None

    excerpt = first_page_text[:2000]
    try:
        result = _chat(
            model=settings.doctype_model,
            system=DOCTYPE_SYSTEM_PROMPT,
            user=excerpt,
            temperature=0.0,
        ).strip()
        if result in DOC_KINDS:
            return result
        return "Others"
    except Exception as exc:
        logger.warning("doc_kind detection failed: %s", exc)
        return None
