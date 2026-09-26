"""Optional EARS syntax for acceptance criteria (roadmap item 11).

EARS — Easy Approach to Requirements Syntax — recognised in English and
Portuguese, case-insensitive, tolerant of trailing punctuation and list
markers:

    ubiquitous  The <system> shall <response>
                O|A <sistema> deve <resposta>
    event       When <trigger>, the <system> shall <response>
                Quando <gatilho>, o <sistema> deve <resposta>
    state       While <state>, the <system> shall <response>
                Enquanto <estado>, o <sistema> deve <resposta>
    unwanted    If <condition>, then the <system> shall <response>
                Se <condição>, então o <sistema> deve <resposta>
    optional    Where <feature>, the <system> shall <response>
                Onde <recurso>, o <sistema> deve <resposta>
    complex     any combination, e.g. While <state>, when <trigger>, the ...

The syntax is *optional*: `validate()` is advisory by default (plain
criteria stay valid, hints are informational); only `strict=True` makes a
non-EARS criterion invalid. Pure functions, stdlib only.
"""
from __future__ import annotations

import os
import re
import unicodedata

PATTERNS = ("ubiquitous", "event", "state", "unwanted", "optional", "complex")

# keyword -> (pattern, clause key, language)
PRECONDITIONS = {
    "when": ("event", "trigger", "en"),
    "while": ("state", "state", "en"),
    "if": ("unwanted", "condition", "en"),
    "where": ("optional", "feature", "en"),
    "quando": ("event", "trigger", "pt"),
    "enquanto": ("state", "state", "pt"),
    "se": ("unwanted", "condition", "pt"),
    "onde": ("optional", "feature", "pt"),
}
MODALS = {"shall": "en", "deve": "pt", "deverá": "pt", "devera": "pt",
          "devem": "pt", "deverão": "pt", "deverao": "pt"}
WEAK_MODALS = {"must": "en", "should": "en", "will": "en",
               "deveria": "pt", "precisa": "pt", "irá": "pt"}
VAGUE_TERMS = {
    "en": ["fast", "quickly", "quick", "user-friendly", "easy", "easily", "intuitive",
           "efficient", "efficiently", "appropriate", "robust", "seamless", "as soon as possible"],
    "pt": ["rápido", "rápida", "rapidamente", "amigável", "fácil", "facilmente", "intuitivo",
           "intuitiva", "eficiente", "adequado", "adequada", "robusto", "o mais rápido possível"],
}
TEMPLATES = {
    "en": {
        "ubiquitous": "The <system> shall <response>",
        "event": "When <trigger>, the <system> shall <response>",
        "state": "While <state>, the <system> shall <response>",
        "unwanted": "If <condition>, then the <system> shall <response>",
        "optional": "Where <feature>, the <system> shall <response>",
        "complex": "While <state>, when <trigger>, the <system> shall <response>",
    },
    "pt": {
        "ubiquitous": "O <sistema> deve <resposta>",
        "event": "Quando <gatilho>, o <sistema> deve <resposta>",
        "state": "Enquanto <estado>, o <sistema> deve <resposta>",
        "unwanted": "Se <condição>, então o <sistema> deve <resposta>",
        "optional": "Onde <recurso>, o <sistema> deve <resposta>",
        "complex": "Enquanto <estado>, quando <gatilho>, o <sistema> deve <resposta>",
    },
}

_ARTICLES = r"(?:the|an|a|os|as|o|um|uma)"
_THEN = r"(?:then|então|entao)"
_KEYWORD_RE = re.compile(r"^(" + "|".join(PRECONDITIONS) + r")\b[\s,]*", re.IGNORECASE)
_MODAL_RE = re.compile(r"\b(" + "|".join(sorted(MODALS, key=len, reverse=True)) + r")\b", re.IGNORECASE)
_WEAK_RE = re.compile(r"\b(" + "|".join(WEAK_MODALS) + r")\b", re.IGNORECASE)
_THEN_PREFIX_RE = re.compile(r"^" + _THEN + r"\b[\s,]*", re.IGNORECASE)
_ARTICLE_PREFIX_RE = re.compile(r"^" + _ARTICLES + r"\s+", re.IGNORECASE)
_LAST_ARTICLE_RE = re.compile(r"\s(?:" + _THEN + r"\s+)?" + _ARTICLES + r"\s+(?!.*\s" + _ARTICLES + r"\s)",
                              re.IGNORECASE)
_LIST_MARKER_RE = re.compile(r"^(?:[-*•]\s+|\d+[.)]\s+)?(?:\[[ xX]\]\s+)?")
_ID_PREFIX_RE = re.compile(r"^(?:AC|CA|FR|NFR|REQ|RF|RNF)[-_ ]?\d+\s*[:.)\-–—]\s*", re.IGNORECASE)
_VAGUE_RES = [(term, lang, re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", re.IGNORECASE))
              for lang, terms in VAGUE_TERMS.items() for term in terms]


def _hint(code: str, message: str, **extra) -> dict:
    return {"code": code, "message": message, **extra}


def normalize(text) -> str:
    """Collapse whitespace, drop list markers/ids and trailing punctuation."""
    t = unicodedata.normalize("NFC", str(text or ""))
    t = re.sub(r"\s+", " ", t).strip()
    t = _LIST_MARKER_RE.sub("", t, count=1)
    t = _ID_PREFIX_RE.sub("", t, count=1)
    return t.rstrip(" .;:!").strip()


def _vague_hints(text: str) -> list[dict]:
    hints, seen = [], set()
    for term, lang, regex in _VAGUE_RES:
        if term not in seen and regex.search(text):
            seen.add(term)
            hints.append(_hint("vague_term", f"vague term: '{term}' — replace it with a measurable, "
                                             "testable threshold", term=term, lang=lang))
    return hints


def _split_keyword(segment: str) -> tuple[str | None, str]:
    match = _KEYWORD_RE.match(segment)
    if not match:
        return None, segment
    return match.group(1).lower(), segment[match.end():].strip()


def _split_at_last_article(body: str) -> tuple[str, str] | None:
    """'the user logs in the system' -> ('the user logs in', 'the system')."""
    match = _LAST_ARTICLE_RE.search(body)
    if not match or not body[: match.start()].strip():
        return None
    return body[: match.start()].strip(), body[match.start():].strip()


def _structure(text: str, modal: re.Match) -> dict:
    """Analyse `<preconditions>, <system> <modal> <response>` around `modal`."""
    hints: list[dict] = []
    ok = True
    preamble = text[: modal.start()].strip().rstrip(",").strip()
    response = text[modal.end():].strip(" ,")
    if not response:
        ok = False
        hints.append(_hint("missing_response", f"missing response after '{modal.group(1)}'"))

    segments = [s.strip() for s in preamble.split(",") if s.strip()] if preamble else []
    preconditions: list[dict] = []
    system_segment = ""
    if segments:
        system_segment = segments[-1]
        for segment in segments[:-1]:
            keyword, rest = _split_keyword(segment)
            if keyword:
                preconditions.append({"keyword": keyword, "text": rest})
            elif preconditions:
                preconditions[-1]["text"] += ", " + segment  # a comma inside the clause
            else:
                ok = False
                hints.append(_hint("unknown_precondition",
                                   f"precondition '{segment}' does not start with When/While/If/Where "
                                   "(PT: Quando/Enquanto/Se/Onde)"))
        keyword, rest = _split_keyword(system_segment)
        if keyword:  # "When X the system shall" — no comma before the system
            split = _split_at_last_article(rest)
            if split:
                preconditions.append({"keyword": keyword, "text": split[0]})
                system_segment = split[1]
                hints.append(_hint("missing_comma", "separate the precondition from the system with a comma"))
            else:
                preconditions.append({"keyword": keyword, "text": rest})
                system_segment = ""

    has_then = bool(_THEN_PREFIX_RE.match(system_segment))
    system = _ARTICLE_PREFIX_RE.sub("", _THEN_PREFIX_RE.sub("", system_segment, count=1), count=1).strip()
    if not system:
        ok = False
        hints.append(_hint("missing_system", "missing system — name who responds before "
                                             f"'{modal.group(1)}' (e.g. 'the <system> shall')"))

    for pre in preconditions:
        pattern, key, lang = PRECONDITIONS[pre["keyword"]]
        pre.update({"type": pattern, "clause": key, "lang": lang})
        if not pre["text"]:
            ok = False
            hints.append(_hint("empty_precondition", f"'{pre['keyword']}' has no {key} text"))

    if not ok:
        pattern = None
    elif not preconditions:
        pattern = "ubiquitous"
    elif len(preconditions) == 1:
        pattern = preconditions[0]["type"]
    else:
        pattern = "complex"
    if ok and any(p["type"] == "unwanted" for p in preconditions) and not has_then:
        hints.append(_hint("missing_then", "unwanted-behaviour criteria read 'If <condition>, then the "
                                           "<system> shall ...' (PT: 'Se <condição>, então o <sistema> deve')"))

    clauses: dict[str, str] = {}
    for pre in preconditions:
        clauses[pre["clause"]] = f"{clauses[pre['clause']]}; {pre['text']}" if pre["clause"] in clauses \
            else pre["text"]
    clauses["system"] = system
    clauses["response"] = response
    return {"pattern": pattern, "clauses": clauses, "preconditions": preconditions, "hints": hints}


def parse(text) -> dict:
    """Classify one criterion. `pattern` is None when it is not EARS."""
    norm = normalize(text)
    vague = _vague_hints(norm)
    if not norm:
        return {"text": norm, "pattern": None, "lang": None, "clauses": {}, "preconditions": [],
                "hints": [_hint("empty", "empty criterion")]}

    modals = list(_MODAL_RE.finditer(norm))
    if not modals:
        weak = _WEAK_RE.search(norm)
        if weak:
            structure = _structure(norm, weak)
            word = weak.group(1)
            hints = [_hint("weak_modal", f"uses '{word}' — EARS requires 'shall' (PT: 'deve'); "
                                         "must/should/will are ambiguous about obligation", term=word.lower())]
            hints += [h for h in structure["hints"] if h["code"] != "missing_then"]
            return {"text": norm, "pattern": None, "lang": WEAK_MODALS[word.lower()],
                    "clauses": structure["clauses"], "preconditions": structure["preconditions"],
                    "hints": hints + vague}
        return {"text": norm, "pattern": None, "lang": None, "clauses": {}, "preconditions": [],
                "hints": [_hint("no_modal", "no 'shall' (PT: 'deve') — not an EARS statement; e.g. "
                                            f"'{TEMPLATES['en']['event']}'")] + vague}

    first = modals[0]
    lang = MODALS[first.group(1).lower()]
    structure = _structure(norm, first)
    hints = list(structure["hints"])
    if len(modals) > 1:
        hints.append(_hint("multiple_shall", f"multiple '{first.group(1).lower()}' — split the criterion "
                                             "into one requirement per statement"))
    if any(p["lang"] != lang for p in structure["preconditions"]):
        hints.append(_hint("mixed_language", "mixes English and Portuguese EARS keywords"))
    return {"text": norm, "pattern": structure["pattern"], "lang": lang, "clauses": structure["clauses"],
            "preconditions": structure["preconditions"], "hints": hints + vague}


def _criterion_text(item) -> str:
    if isinstance(item, dict):
        return str(item.get("text") or item.get("criterion") or item.get("description") or "")
    return str(item)


def validate(criteria, strict: bool = False) -> dict:
    """Check a list of criteria. Advisory unless `strict` (then non-EARS fails)."""
    items = []
    for index, criterion in enumerate(criteria or []):
        parsed = parse(_criterion_text(criterion))
        items.append({"index": index, "ears": parsed["pattern"] is not None, **parsed})
    total = len(items)
    ears_count = sum(1 for item in items if item["ears"])
    return {
        "strict": bool(strict),
        "total": total,
        "ears": ears_count,
        "non_ears": total - ears_count,
        "coverage": round(ears_count / total, 4) if total else 1.0,
        "items": items,
        "valid": (total - ears_count == 0) if strict else True,
    }


def check_state(state: dict, feature_id: str | None = None, strict: bool = False) -> dict:
    """Run `validate` over every feature's (or one feature's) acceptance_criteria."""
    features = [f for f in state.get("features") or [] if isinstance(f, dict)]
    if feature_id is not None:
        features = [f for f in features if f.get("id") == feature_id]
        if not features:
            raise ValueError(f"unknown feature id: {feature_id}")
    reports = []
    for feature in features:
        result = validate(feature.get("acceptance_criteria") or [], strict=strict)
        reports.append({"id": feature.get("id"), "name": feature.get("name"), **result})
    total = sum(r["total"] for r in reports)
    ears_count = sum(r["ears"] for r in reports)
    return {
        "strict": bool(strict),
        "features": reports,
        "total": total,
        "ears": ears_count,
        "non_ears": total - ears_count,
        "coverage": round(ears_count / total, 4) if total else 1.0,
        "valid": all(r["valid"] for r in reports),
    }


def resolve_state_path(path: str) -> str:
    """Accept a state.json path or a project directory."""
    if os.path.isdir(path):
        return os.path.join(path, ".spec-master", "state.json")
    return path
