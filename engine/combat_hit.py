"""Common hit comparison; callers own admission, dice and effect consumption."""
import math
from numbers import Real


def resolve(*, natural, modifier, accuracy, evasion, automatic=False,
            cannot_hit=None, auto_miss_natural=1, auto_hit_natural=20):
    """Compare one observed die against one target's declared defense."""
    for label, value in (("natural", natural), ("auto_miss_natural", auto_miss_natural),
                         ("auto_hit_natural", auto_hit_natural)):
        if type(value) is not int or not 1 <= value <= 20:
            raise ValueError(label + " must be a d20 face")
    if auto_miss_natural == auto_hit_natural:
        raise ValueError("natural hit and miss faces must differ")
    for label, value in (("modifier", modifier), ("accuracy", accuracy), ("evasion", evasion)):
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            raise ValueError(label + " must be finite numeric data")
    if type(automatic) is not bool:
        raise ValueError("automatic must be boolean")
    if cannot_hit is not None and (not isinstance(cannot_hit, str) or not cannot_hit.strip()):
        raise ValueError("cannot_hit requires a reason")
    total, threshold = natural + modifier, accuracy + evasion
    if cannot_hit is not None:
        hit, basis = False, "cannot_hit"
    elif automatic:
        hit, basis = True, "automatic"
    elif natural == auto_miss_natural:
        hit, basis = False, "natural_miss"
    elif natural == auto_hit_natural:
        hit, basis = True, "natural_hit"
    else:
        hit, basis = total >= threshold, "comparison"
    return {"hit": hit, "basis": basis, "natural": natural, "modifier": modifier,
            "accuracy": accuracy, "evasion": evasion, "total": total,
            "threshold": threshold, "cannot_hit": cannot_hit}
