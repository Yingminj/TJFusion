"""The closed label set + prompt/output contract for the gift-packaging verifier.

Vendored verbatim from the training repo (test_vlm/test_training/src/gift_ft/ontology.py)
so VlmDocker is self-contained. This is the single source of truth for label ids, the
prompt text, and the output JSON shape -- it MUST stay in sync with the adapter the
server loads (gift_v1 was trained against exactly this ontology). Only stdlib imports.
"""
from __future__ import annotations

import json
import re
from typing import Dict, Optional

# Canonical ontology (matches data/test_0605/gift.txt + the NAS json_labels class_id).
# Class 12 ("rubbish") is an explicit reject class for irrelevant / garbage frames so the
# model says "not a valid task state" instead of hallucinating a phase.
CLASSES: Dict[int, str] = {
    1: "box free and closed",
    2: "box fixed and closed",
    3: "box fixed and opening",
    4: "box open and toy free",
    5: "toy in hand and outside box",
    6: "toy in box and box opened",
    7: "toy in box and box closing",
    8: "toy in box and box on table",
    9: "right hand holding red bag, left hand holding green box",
    10: "toy in box and box in hand",
    11: "gift has been packaged",
    12: "rubbish",
}

# Label 0 in the raw per-frame txt is an unlabeled gap (treated as noise, dropped in build).
IGNORE_LABEL = 0
TERMINAL_STATE = 11  # "gift has been packaged" -> task done
REJECT_STATE = 12    # "rubbish"

NAME_TO_ID = {v: k for k, v in CLASSES.items()}


def load_ontology(gift_txt: Optional[str] = None) -> Dict[int, str]:
    """Load the ontology. If a gift.txt (``C1:name`` per line) is given, it overrides
    the built-in names (kept in sync with whatever the annotators used)."""
    if not gift_txt:
        return dict(CLASSES)
    out: Dict[int, str] = {}
    with open(gift_txt, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            tag, name = line.split(":", 1)
            tag = tag.strip().upper()
            if tag.startswith("C") and tag[1:].isdigit():
                out[int(tag[1:])] = name.strip()
    return out or dict(CLASSES)


def build_prompt(classes: Dict[int, str], task: str = "pack the toy into the gift box") -> str:
    """The user-turn text shown alongside the frame window. Kept short + explicit; the
    closed list and the 'ONLY JSON' instruction are what make the output stable."""
    lines = [f"  {i}: {classes[i]}" for i in sorted(classes)]
    states = "\n".join(lines)
    return (
        "You are a real-time state verifier for a robot performing this task: "
        f"\"{task}\".\n"
        "You are shown the most recent video frames (oldest first, newest last). "
        "Report the CURRENT state of the scene in the newest frame.\n\n"
        "Valid states:\n"
        f"{states}\n\n"
        "Rules:\n"
        "- Pick exactly one state id from the list above.\n"
        "- Use 12 (rubbish) if the frame shows no valid task state.\n"
        "- Answer with ONLY a compact JSON object, no other text:\n"
        '  {"state": <id>, "name": "<exact state name>"}'
    )


def format_answer(state_id: int, classes: Dict[int, str]) -> str:
    """The assistant-turn target string. Fixed key order -> deterministic to learn/parse."""
    return json.dumps({"state": int(state_id), "name": classes[int(state_id)]}, ensure_ascii=False)


# Constrained-decoding / parsing regex. Matches the canonical answer shape.
ANSWER_REGEX = re.compile(r'\{\s*"state"\s*:\s*(\d{1,2})\s*,\s*"name"\s*:\s*"([^"]*)"\s*\}')


def parse_answer(text: str, classes: Optional[Dict[int, str]] = None) -> Optional[dict]:
    """Parse a model generation back into {'state': int, 'name': str}. Returns None if no
    valid JSON state object is found (so callers can count format failures)."""
    classes = classes or CLASSES
    m = ANSWER_REGEX.search(text)
    if not m:
        return None
    sid = int(m.group(1))
    if sid not in classes:
        return None
    # Trust the id; normalise the name to the canonical one.
    return {"state": sid, "name": classes[sid]}
