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
    "inform",
    "explain",
    "express",
    "express_interest",
    "suggest",
    "agree",
    "refuse",
    "thank",
    "apologize",
    "speak_to",
}
FREE_TYPES = {"look", "observe", "watch", "listen", "think", "consider", "none", "nothing"}
READ_TYPES = {"read", "study", "peruse", "read_document"}

# social actions: spoken to someone AND resolved with a skill check by the engine (play session
# 2026-10-05: "propose_participation", "negotiate", "express_interest" each became an improvised
# d20 and never reached the listener as speech). kind -> (skill, attribute, label)
SOCIAL_SKILLS: dict[str, tuple[str, str, str]] = {
    "persuade": ("skill.persuasion", "attr.presence", "Persuasion"),
    "deceive": ("skill.deception", "attr.presence", "Deception"),
    "intimidate": ("skill.intimidation", "attr.presence", "Intimidation"),
    "bribe": ("skill.persuasion", "attr.presence", "Persuasion (bribe)"),
    "perform": ("skill.performance", "attr.presence", "Performance"),
}
SOCIAL_SYNONYMS = {
    "convince": "persuade",
    "negotiate": "persuade",
    "bargain": "persuade",
    "haggle": "persuade",
    "propose": "persuade",
    "propose_deal": "persuade",
    "offer": "persuade",
    "plead": "persuade",
    "request": "persuade",
    "charm": "persuade",
    "flatter": "persuade",
    "lie": "deceive",
    "bluff": "deceive",
    "trick": "deceive",
    "threaten": "intimidate",
    "coerce": "intimidate",
    "menace": "intimidate",
    "demand": "intimidate",
    "pay_off": "bribe",
    "entertain": "perform",
    "sing": "perform",
}
# the closed list the interpreter is given (anything else is normalized below)
CANONICAL_TYPES = [
    *sorted(
        {
            "attack",
            "move",
            "travel",
            "sprint",
            "engage",
            "disengage",
            "withdraw",
            "take_cover",
            "search",
            "pick_up",
            "drop",
            "short_rest",
            "long_rest",
            "wait",
            "flee",
            "surrender",
            "defend",
            "protect",
        }
    ),
    "read",
    "say",
    "ask",
    "whisper",
    *sorted(SOCIAL_SKILLS),
    "look",
    "other",
]


def canonical_kind(word: str, channel: str) -> str:
    """One action word in the engine's vocabulary. Unknown words in speech are speech;
    unknown deeds stay as they are and go to the Rules Adjudicator."""
    w = word.lower().strip().replace(" ", "_").replace("-", "_")
    if w in SOCIAL_SKILLS:
        return w
    if w in SOCIAL_SYNONYMS:
        return SOCIAL_SYNONYMS[w]
    if w in ACTION_MAP or w in SPEECH_TYPES or w in FREE_TYPES or w in READ_TYPES:
        return w
    if w.startswith("action."):
        return w
    head = w.split("_", 1)[0]  # "propose_participation" -> propose, "threaten_him" -> threaten
    if head != w:
        if head in SOCIAL_SKILLS:
            return head
        if head in SOCIAL_SYNONYMS:
            return SOCIAL_SYNONYMS[head]
        if head in ACTION_MAP or head in READ_TYPES:
            return head
    if channel in ("say", "whisper"):
        return "say"
    return w


def action_key_for(word: str) -> str | None:
    w = word.lower().strip().replace(" ", "_")
    if w.startswith("action."):
        return w
    return ACTION_MAP.get(w)
