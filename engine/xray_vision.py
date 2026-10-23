"""Bounded X-Ray Vision through actual, source-bound sensory evidence.

The common perception owner proves the observer/target pair, selected source,
current capability, barrier observation, presence, and restoration.  This
adapter owns only the qualitative material policy and the deliberately narrow
white-silhouette result from ch10:160; it never turns X-Ray Vision into ordinary
identity, species, type, text, or position access.
"""
from copy import deepcopy

import perception_observe as OBSERVE
import state_grants as GRANTS


SOURCE = "capability/엑스레이-시야"
CAPABILITIES = ("엑스레이 시야", "X-Ray Vision")

# The source gives qualitative examples and no numeric threshold.  Keep the
# authored distinction qualitative; an unlisted material remains unresolved.
EASY = {
    "wood": "wood",
    "나무": "wood",
    "paper": "paper",
    "종이": "paper",
    "drywall": "drywall",
    "plaster": "drywall",
    "회벽": "drywall",
}
NEARLY_OPAQUE = {
    "lead": "lead",
    "납": "lead",
    "tungsten": "tungsten",
    "텅스텐": "tungsten",
}


def _key(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("actual nonempty barrier material required")
    return "".join(value.casefold().split()).replace("-", "").replace("_", "")


def material_policy(value):
    """Return the exact qualitative band without inventing a thickness DC."""
    key = _key(value)
    if key in EASY:
        return {"material": EASY[key], "penetration": "easy"}
    if key in NEARLY_OPAQUE:
        return {"material": NEARLY_OPAQUE[key], "penetration": "nearly_none"}
    return {"material": value.strip(), "penetration": "unresolved"}


def declaration(material):
    """A private presence-only declaration used by the common route.

    The observed material is admitted only as the current medium evidence.  It
    does not grant information; ``observe`` applies the fixed material policy
    after the common route has verified the signed/current observation.
    """
    return OBSERVE.declaration({
        "id": "native:" + SOURCE,
        "source": SOURCE,
        "capabilities": list(CAPABILITIES),
        "mode": "visual",
        "range": None,
        "path": None,
        "medium": [material],
        "vision": None,
        "provider": "entity",
        "information": ["presence"],
        "check": None,
    })


def _result(status, reason, *, values=None, unknown=()):
    return {
        "source": SOURCE,
        "mode": "visual",
        "status": status,
        "reason": reason,
        "values": {} if values is None else deepcopy(values),
        "unknown_fields": list(unknown),
    }


def _observed_material(engine, observer, target):
    """Read only enough to build the common medium gate.

    ``OBSERVE.observe`` below validates the evidence signature and current world
    context before this value can affect a result.
    """
    uid = target.get("entity_id", target.get("id")) if type(target) is dict else getattr(target, "entity_id", None)
    row = getattr(engine, OBSERVE.ENV, {}).get(OBSERVE.environment_key(observer.entity_id, uid))
    if row is None:
        return "xray-barrier-unobserved"
    material = row.get("facts", {}).get("medium")
    return material if isinstance(material, str) and material.strip() else "xray-barrier-unobserved"


def observe(engine, observer, target):
    """Observe at most an indistinct white silhouette through one barrier.

    Easy examples yield a silhouette, lead/tungsten yield no target detail, and
    any other material remains explicitly unresolved for a source-specific
    ruling.  No caller-supplied declaration or information list can widen the
    result.
    """
    material = _observed_material(engine, observer, target)
    common = OBSERVE.observe(engine, observer, target, declaration(material))
    if common["status"] != "observed":
        return common

    policy = material_policy(material)
    if policy["penetration"] == "easy":
        return _result(
            "observed",
            "xray_indistinct_white_silhouette",
            values={"presence": True, "silhouette": "indistinct_white"},
        )
    if policy["penetration"] == "nearly_none":
        return _result("not_observable", "xray_material_nearly_opaque")
    return _result("unknown", "xray_material_accuracy_unresolved", unknown=("silhouette",))


def available(actor):
    """Small projection for UIs; the actual consumer still rechecks ownership."""
    owned = {"".join(str(value).casefold().split()).replace("-", "").replace("_", "")
             for value in GRANTS.effective_capabilities(actor)}
    return any(_key(value) in owned for value in CAPABILITIES)
