"""Source-bounded feature action metadata; AP costs are a separate resource.

ch03:578 says the Frequency and Action label specifies the required action.
ch07:57 says triggered features are *usually* Free, not always.
ch03:592 gives only explicitly identified crafting features an Extended default.
A reviewed importer may mark feature_kind="crafting"; names, ingredients and
arbitrary effect text do not establish that classification here.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ActionCost:
    """One activation with conjunctive costs, not several action occurrences.

    Full remains its own sourced action type. Repeated tokens and mixed special
    timing are unsupported rather than deduplicated or inferred as grants.
    """
    components: tuple

    def __post_init__(self):
        if (type(self.components) is not tuple or not 2 <= len(self.components) <= 3
                or any(type(x) is not str or x not in ("standard", "shift", "swift") for x in self.components)
                or len(set(self.components)) != len(self.components)):
            raise ValueError("unsupported compound action cost")

    def __str__(self):
        return "+".join(self.components)


def supported_combat_action(action):
    return type(action) is ActionCost or (type(action) is str and action in ("free", "standard", "shift", "swift", "full"))

_ACTIONS = {
    "standard": "standard", "기본 행동": "standard", "Standard Action": "standard",
    "shift": "shift", "이동 행동": "shift", "Shift Action": "shift",
    "swift": "swift", "신속 행동": "swift", "Swift Action": "swift",
    "free": "free", "자유 행동": "free", "Free Action": "free",
    "full": "full", "완전 행동": "full", "Full Action": "full",
    "extended": "extended", "연장 행동": "extended", "Extended Action": "extended",
    "static": "static", "항상": "static", "Static": "static",
}
_FREQUENCY_ONLY = re.compile(
    r"(?:\d+\s*AP(?:\s*(?:지속|제거))?|(?:Bind|Drain)\s+\d+\s+AP|"
    r"임의|At-Will|일회용|One[ -]Time(?: Use)?|장면(?:\s*[xX]?\s*\d+)?|하루(?:\s*[xX]?\s*\d+)?|"
    r"Scene(?:\s*[xX]?\s*\d+)?|Daily(?:\s*[xX]?\s*\d+)?)"
)


def _parse_action_label(text):
    scalar = _ACTIONS.get(text)
    if scalar is not None:
        return scalar
    if "+" not in text:
        return None
    parts = text.split("+")
    components = tuple(_ACTIONS.get(part.strip()) for part in parts)
    try:
        return ActionCost(components)
    except ValueError:
        return None


def resolve_feature_action(header):
    """Return (action, reason), without mutating any runtime state.

    Structured extraction does not override conflicting raw text.
    The old extractor keeps only the first '+' component, so raw checking is
    mandatory whenever that source label is available. An exactly matching legacy
    first-component scalar is replaced by the complete, fully parsed raw cost.
    Other disagreement remains unresolved. Extended is resolved
    metadata, not evidence these combat callers implement its execution.
    """
    if not isinstance(header, dict):
        return None, "재주 행동 헤더 형식 미해석"
    frequency = header.get("frequency")
    if frequency is None:
        frequency = {}
    if not isinstance(frequency, (dict, str)):
        return None, "재주 빈도/행동 형식 미해석"
    raw = frequency.get("raw", "") if isinstance(frequency, dict) else frequency
    if not isinstance(raw, str):
        return None, "재주 행동 원문 형식 미해석"
    raw = raw.strip()
    raw_action = _parse_action_label(raw)
    if raw and raw_action is None:
        parts = re.split(r"\s+[–—-]\s*", raw, maxsplit=1)
        if len(parts) == 2:
            raw_action = _parse_action_label(parts[1].strip())
            if raw_action is None:
                return None, "재주 원문 행동 종류 또는 복합 행동 미해석"
        elif not _FREQUENCY_ONLY.fullmatch(raw):
            return None, "재주 빈도/행동 원문 미해석"
    if isinstance(frequency, dict) and "action" in frequency:
        declared = frequency["action"]
        if not isinstance(declared, str):
            return None, "재주 명시 행동 종류 미해석"
        action = _parse_action_label(declared.strip())
        if action is None:
            return None, "재주 명시 행동 종류 미해석"
        if type(raw_action) is ActionCost and action == raw_action.components[0]:
            # mechanize_feats.parse_frequency used act.split("+")[0]. Only
            # that exact lossy signature may be recovered from complete raw.
            return raw_action, ""
        if raw_action is not None and raw_action != action:
            return None, "재주 행동 원문/구조화 메타데이터 충돌"
        # Older extraction used action=static when any action label was missing.
        if action == "static" and raw_action != "static":
            if header.get("feature_kind") == "crafting":
                return "extended", ""  # Source-scoped default; discard only an unanchored extraction placeholder.
            return None, "재주 static 표식의 원문 근거 미확인"
        return action, ""
    if raw_action is not None:
        return raw_action, ""
    if header.get("feature_kind") == "crafting":
        return "extended", ""
    return None, "재주 행동 종류 누락: 일반 Free 기본값 없음"


def resolve_crafting_policy(header):
    """Reviewed crafting defaults only; preserve a specific action/frequency.

    Classification must come from the reviewed content adapter, never an item
    name, price, confidence field, or the absence of an ordinary action label.
    """
    if not isinstance(header,dict) or header.get('feature_kind')!='crafting':
        raise ValueError('reviewed crafting feature classification required')
    action,problem=resolve_feature_action(header)
    if problem:raise ValueError(problem)
    import frequency as FREQ
    frequency=header.get('frequency')
    if not frequency:kind,uses='at_will',1
    else:
        kind,uses=FREQ.parse(frequency)
        # An action label alone specifies no contrary frequency.
        raw=frequency.get('raw','') if isinstance(frequency,dict) else frequency
        if kind=='unknown' and _parse_action_label(raw.strip()) is not None:kind,uses='at_will',1
        if kind=='unknown':raise ValueError('explicit crafting frequency requires its own policy')
    return {'action':action,'frequency':{'kind':kind,'uses':uses}}
