"""Shared intent vocabulary: how model-facing action words map to ruleset action keys.
Used by the orchestrator (human intents) and the AI actor service (AI intentions)."""

from __future__ import annotations

ACTION_MAP = {
    "attack": "action.attack",
    "strike": "action.attack",
    "hit": "action.attack",
    "stab": "action.attack",
    "shoot": "action.attack",
    "fire": "action.attack",
    "move": "action.move",
    "go": "action.move",
    "walk": "action.move",
    "run": "action.move",
    "approach": "action.move",
    "head": "action.move",
    "travel": "action.move",
    "enter": "action.move",
    "leave": "action.move",
    "visit": "action.move",
    "go_to": "action.move",
    "head_to": "action.move",
    "walk_to": "action.move",
    "sprint": "action.sprint",
    "engage": "action.engage",
    "close": "action.engage",
    "disengage": "action.disengage",
    "withdraw": "action.withdraw",
    "take_cover": "action.take_cover",
    "cover": "action.take_cover",
    "duck": "action.take_cover",
    "hide": "action.take_cover",
    "search": "action.search",
    "investigate": "action.search",
    "examine": "action.search",
    "look_for": "action.search",
    "pick_up": "action.pick_up",
    "take": "action.pick_up",
    "grab": "action.pick_up",
    "drop": "action.drop",
    "rest": "action.short_rest",
    "short_rest": "action.short_rest",
    "long_rest": "action.long_rest",
    "sleep": "action.long_rest",
    "wait": "action.wait",
    "flee": "action.flee",
    "escape": "action.flee",
    "surrender": "action.surrender",
    "yield": "action.surrender",
    "defend": "action.defend",
    "protect": "action.protect",
}
SPEECH_TYPES = {
    "say",
    "tell",
    "ask",
    "talk",
    "speak",
    "whisper",
    "shout",
    "yell",
    "call",
    "reply",
    "answer",
    "greet",
}
FREE_TYPES = {"look", "observe", "watch", "listen", "think", "consider", "none", "nothing"}
READ_TYPES = {"read", "study", "peruse", "read_document"}


def action_key_for(word: str) -> str | None:
    w = word.lower().strip().replace(" ", "_")
    if w.startswith("action."):
        return w
    return ACTION_MAP.get(w)
