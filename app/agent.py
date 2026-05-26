"""
agent.py — SHL Assessment Advisor
Google Gemini (free tier) + BM25 retrieval.

Key design: type-aware catalog ordering before LLM call, so even when
the model just picks the top items from context, it picks the right types.
Drop/exclude instructions are enforced post-LLM in code, not relying on the model.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent / "catalog"))
from catalog_store import get_store  # noqa: E402

# --------------------------------------------------------------------------- #
# Gemini setup                                                                 #
# --------------------------------------------------------------------------- #

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

genai.configure(api_key=GEMINI_API_KEY)

# --------------------------------------------------------------------------- #
# Prompt                                                                       #
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """You are an SHL Assessment Advisor. Help hiring managers pick SHL Individual Test Solutions.

RULES:
1. Only discuss SHL assessment selection. Refuse salary, legal, HR-process questions.
2. Only use items from CATALOG DATA. Never invent URLs.
3. If the first message is vague (no role/skill), ask ONE clarifying question. Set recommendations=[].
4. Once you have role + requirement, give 1-10 recommendations from the catalog.
5. For comparison questions ("difference between X and Y"), answer in text. Set recommendations=[].
6. Output ONLY raw JSON — no prose, no markdown fences.

OUTPUT FORMAT (required every time):
{"reply": "text here", "recommendations": [], "end_of_conversation": false}

With recommendations:
{"reply": "text", "recommendations": [{"name": "exact catalog name", "url": "exact catalog url", "test_type": "K"}], "end_of_conversation": false}

test_type: A=Ability K=Knowledge P=Personality B=Biodata/SJT M=Motivation S=Simulation E=Exercise C=Competency D=Development

CATALOG DATA (recommend ONLY from this list):
{catalog_text}
"""


def build_system(catalog_text: str) -> str:
    return SYSTEM_PROMPT.replace("{catalog_text}", catalog_text)


# --------------------------------------------------------------------------- #
# Regex guards                                                                 #
# --------------------------------------------------------------------------- #

REFUSAL_RE = re.compile(
    r"\b(salary|compens|pay range|offer letter|interview tips|interview guide|"
    r"legal advice|discriminat|gdpr|background check compliance|"
    r"ignore previous|disregard (all|your)|jailbreak|act as (a |an )?(?!shl)|"
    r"pretend you|forget your (instructions|rules)|"
    r"reveal (your )?(system|instructions)|output your (system|prompt))\b",
    re.I,
)

JD_ADVICE_RE = re.compile(
    r"\b(write|create|draft|make|structure)\b.{0,40}\b(job description|jd|job posting)\b",
    re.I,
)

COMPARE_RE = re.compile(
    r"\b(what.?s the difference|difference between|compare|versus|"
    r"how does .{1,40} differ|which is better between)\b",
    re.I,
)

DROP_RE = re.compile(
    r"\b(drop|remove|exclude|skip|without|don.t (?:include|add|use))\b"
    r".{0,50}?\b([A-Z][A-Za-z0-9+\-\s]{2,35}?)(?:\.|,|$|\band\b|\bfrom\b)",
    re.I | re.MULTILINE,
)

# --------------------------------------------------------------------------- #
# Type inference                                                                #
# --------------------------------------------------------------------------- #

TYPE_KW: dict[str, list[str]] = {
    "A": ["aptitude","cognitive","numerical","verbal","abstract","reasoning","verify g","g+","gmrt"],
    "K": ["java","python","sql","spring","aws","docker","excel","word","linux","networking",
          "angular","react","hipaa","medical terminology","accounting","statistics","rust",
          "knowledge test","skills test","coding test","technical test","programming test"],
    "P": ["personality","behaviour","behavioral","opq","opq32","dependability",
          "dsi","safety instrument","safety and dependability","hogan","hpi"],
    "B": ["situational judgment","situational judgement","sjt","biodata",
          "graduate scenarios","scenarios","situational"],
    "M": ["motivation","motivat","mq","drive","engagement"],
    "S": ["simulation","svar","call simulation","contact center simulation","call center"],
    "E": ["exercise","role play","inbox exercise"],
    "C": ["competency","competencies","leadership","360","global skills","ucf"],
    "D": ["development report","360 feedback","reskill","re-skill"],
}


def infer_types(text: str) -> list[str]:
    lo = text.lower()
    return [code for code, kws in TYPE_KW.items() if any(k in lo for k in kws)]


def user_query(messages: list[dict]) -> str:
    return " ".join(m["content"] for m in messages if m["role"] == "user")


def user_turns(messages: list[dict]) -> int:
    return sum(1 for m in messages if m["role"] == "user")


VAGUE_SKIP = {
    "i","a","an","the","need","want","get","some","please","help","me","us","our",
    "assessment","assessments","test","tests","tool","tools","solution","solutions",
    "something","use","with","for","find","good","can","you",
}

def is_vague(msg: str) -> bool:
    words = re.sub(r"[^\w\s]", "", msg.lower()).split()
    return len([w for w in words if w not in VAGUE_SKIP and len(w) > 1]) < 2


def extract_dropped_names(text: str) -> set[str]:
    """Extract item names the user wants removed from the shortlist."""
    dropped = set()
    for m in DROP_RE.finditer(text):
        name = m.group(2).strip().lower()
        if len(name) > 2:
            dropped.add(name)
    return dropped


# --------------------------------------------------------------------------- #
# Catalog ordering — put the right types at the TOP of context                 #
# --------------------------------------------------------------------------- #

def type_ordered_hits(
    store,
    query: str,
    type_filters: list[str],
    k: int = 10,
    excluded_names: set[str] | None = None,
) -> list[dict]:
    excluded_names = excluded_names or set()

    def is_excluded(p: dict) -> bool:
        name_lo = p["name"].lower()
        return any(ex in name_lo for ex in excluded_names)

    ordered: list[dict] = []
    seen: set[str] = set()

    for type_code in type_filters:
        type_hits = store.search(query, k=k, type_filter=[type_code])
        for p in type_hits:
            if p["url"] not in seen and not is_excluded(p):
                ordered.append(p)
                seen.add(p["url"])

    all_hits = store.search(query, k=k * 2)
    for p in all_hits:
        if p["url"] not in seen and not is_excluded(p):
            ordered.append(p)
            seen.add(p["url"])

    if not ordered:
        for p in store.get_all():
            if not is_excluded(p):
                ordered.append(p)
            if len(ordered) >= k:
                break

    return ordered[:k]


# --------------------------------------------------------------------------- #
# Gemini LLM call                                                              #
# --------------------------------------------------------------------------- #

def call_gemini(system: str, messages: list[dict], timeout: int = 25) -> str:
    """
    Call Google Gemini API.
    Converts the conversation history into Gemini's Content format.
    System prompt is prepended to the first user message since Gemini
    flash models handle system instructions this way most reliably.
    """
    gemini_history = []
    first_user_done = False

    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        content = msg["content"]

        if role == "user" and not first_user_done:
            content = f"{system}\n\n---\nUser: {content}"
            first_user_done = True

        gemini_history.append({"role": role, "parts": [content]})

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        generation_config=genai.types.GenerationConfig(
            temperature=0.05,
            max_output_tokens=900,
            top_p=0.9,
        ),
    )

    if len(gemini_history) == 1:
        response = model.generate_content(gemini_history[0]["parts"][0])
        return response.text

    # Multi-turn: pass all but last as history, send last as new message
    chat = model.start_chat(history=gemini_history[:-1])
    last = gemini_history[-1]["parts"][0]
    response = chat.send_message(last)
    return response.text


# --------------------------------------------------------------------------- #
# Parse + validate LLM output                                                  #
# --------------------------------------------------------------------------- #

def parse_response(raw: str, valid_urls: set[str]) -> dict:
    text = re.sub(r"```(?:json)?|```", "", raw).strip()
    start = text.find("{")
    if start == -1:
        return {"reply": text[:400] or "Could not format a response.",
                "recommendations": [], "end_of_conversation": False}

    depth, end = 0, -1
    for i, ch in enumerate(text[start:], start):
        if ch == "{":   depth += 1
        elif ch == "}": depth -= 1
        if depth == 0:  end = i; break

    json_str = text[start:end + 1] if end != -1 else text[start:]
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        m = re.search(r'"reply"\s*:\s*"(.*?)"(?:,|\})', json_str, re.DOTALL)
        return {"reply": m.group(1) if m else text[:400],
                "recommendations": [], "end_of_conversation": False}

    store = get_store()
    clean = []
    for rec in parsed.get("recommendations") or []:
        url = rec.get("url", "")
        if url in valid_urls:
            clean.append(rec)
        else:
            p = store.get_by_name(rec.get("name", ""))
            if p is None:
                p = store.get_by_url_slug(url)
            if p:
                clean.append({
                    "name": p["name"], "url": p["url"],
                    "test_type": rec.get("test_type", (p.get("test_types") or ["A"])[0]),
                })

    return {
        "reply": str(parsed.get("reply", "")),
        "recommendations": clean[:10],
        "end_of_conversation": bool(parsed.get("end_of_conversation", False)),
    }


def to_rec(p: dict) -> dict:
    return {"name": p["name"], "url": p["url"],
            "test_type": (p.get("test_types") or ["A"])[0]}


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

def run_agent(messages: list[dict]) -> dict:
    store     = get_store()
    valid     = {p["url"] for p in store.get_all()}
    n_turns   = user_turns(messages)
    last_msg  = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    query     = user_query(messages)

    # ── Hard refusals ───────────────────────────────────────────────────────
    if REFUSAL_RE.search(last_msg) or JD_ADVICE_RE.search(last_msg):
        return {"reply": "I can only help with selecting SHL assessments. "
                         "I'm not able to assist with that request.",
                "recommendations": [], "end_of_conversation": False}

    # ── Vague first message ─────────────────────────────────────────────────
    if n_turns == 1 and is_vague(last_msg):
        return {"reply": "Happy to help! Could you tell me more about the role — "
                         "job title, seniority level, or key skills you need to assess?",
                "recommendations": [], "end_of_conversation": False}

    # ── Comparison → answer only, never recommend ────────────────────────────
    is_compare = bool(COMPARE_RE.search(last_msg))

    # ── Extract explicit drop instructions ──────────────────────────────────
    dropped_names = extract_dropped_names(last_msg)

    # ── Type inference from full conversation ───────────────────────────────
    type_filters = infer_types(query)

    # ── Build type-ordered catalog context ──────────────────────────────────
    hits = type_ordered_hits(
        store, query,
        type_filters=type_filters if not is_compare else [],
        k=10,
        excluded_names=dropped_names,
    )

    catalog_text = store.summary_for_llm(hits)
    system = build_system(catalog_text)

    if n_turns >= 2 and not is_compare:
        system += (
            "\n\nIMPORTANT: You have sufficient context. "
            "Your JSON must include recommendations (not empty). "
            "Pick the most relevant items from CATALOG DATA above."
        )

    # ── LLM call ────────────────────────────────────────────────────────────
    llm_timeout = 25 if n_turns <= 2 else 28
    try:
        raw = call_gemini(system, messages, timeout=llm_timeout)
    except Exception as e:
        # On any LLM error, fall back to BM25 results directly
        fallback_recs = [to_rec(p) for p in hits[:5]]
        return {"reply": "Here are the most relevant assessments based on your requirements.",
                "recommendations": fallback_recs, "end_of_conversation": False}

    result = parse_response(raw, valid)

    # ── Post-process: enforce comparison = no recs ──────────────────────────
    if is_compare:
        result["recommendations"] = []
        return result

    # ── Post-process: enforce drop instructions on whatever LLM returned ────
    if dropped_names and result["recommendations"]:
        result["recommendations"] = [
            r for r in result["recommendations"]
            if not any(d in r["name"].lower() for d in dropped_names)
        ]

    # ── Post-process: if LLM returned recs but wrong types, re-rank ─────────
    if type_filters and result["recommendations"]:
        llm_types = {r.get("test_type", "") for r in result["recommendations"]}
        missing   = [t for t in type_filters if t not in llm_types]
        if missing:
            result_urls = {r["url"] for r in result["recommendations"]}
            additions = [
                to_rec(p) for p in hits
                if (p.get("test_types") or [""])[0] in missing
                and p["url"] not in result_urls
            ][:3]
            result["recommendations"] = (additions + result["recommendations"])[:10]

    # ── Fallback: if LLM returned nothing, use top of type-ordered hits ─────
    if not result["recommendations"]:
        result["recommendations"] = [to_rec(p) for p in hits[:5]]
        if not result["reply"]:
            result["reply"] = "Based on your requirements, here are the most relevant assessments."

    return result
