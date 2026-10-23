"""PTK common arithmetic boundaries, separated from neutral exact arithmetic.

CORE-005: PTU 1.05 p219 / ch06:7 says round *down to the nearest whole
number*. That operator is floor, including negative values; it is not truncation.
CORE-006: ch06:9-10 adds percentages on the same base, including signed
adjustments. It does not identify independent stages or convert fixed factors
into percentages; those operands and stages require their own source rules.
The caller names the quantity/base/stage; this module never guesses grouping.
"""
from dataclasses import dataclass
from fractions import Fraction
if __package__:
    from . import arithmetic as A
else:
    import arithmetic as A

SOURCE = 'ch06-gameplay/시스템-기본-사항'
CLAUSES = ('C3-CORE-005', 'C3-CORE-006')



def validate_source(rules):
    """Check the currently selected policy at use time, never at import only."""
    if rules._selected_rule(SOURCE) != SOURCE:
        raise ValueError('selected arithmetic source needs its own numeric policy')
    rulings = getattr(rules, 'rulings', None)
    if rulings is not None and (getattr(rulings, 'mech', {}).get(SOURCE) or
                                getattr(rulings, 'effects', {}).get(SOURCE)):
        raise ValueError('overridden arithmetic source needs its own numeric policy')
    return SOURCE


def floor(value):
    return A.round_down(value)


def ratio(numerator, denominator):
    return floor(A.exact(numerator) / A.exact(denominator))


def product(*factors):
    return floor(A.multiply(*factors))


def ceil_ratio(numerator, denominator):
    """Only for a caller whose specific rule explicitly says round up."""
    return A.round_up(A.exact(numerator) / A.exact(denominator))


@dataclass(frozen=True)
class PercentageAdjustment:
    rate: object
    quantity: str
    base_id: str
    stage: str
    source: str

    def __post_init__(self):
        if any(not isinstance(v, str) or not v.strip() for v in (self.quantity, self.base_id, self.stage, self.source)):
            raise ValueError('percentage adjustment needs quantity, base, stage and source')
        rate = A.exact(self.rate)
        object.__setattr__(self, 'rate', rate)


@dataclass(frozen=True)
class PercentageIncrease(PercentageAdjustment):
    """Compatibility type for callers that explicitly have positive boosts."""
    def __post_init__(self):
        super().__post_init__()
        if self.rate < 0:
            raise ValueError('a decrease is a signed adjustment, not an increase')


def accumulate_adjustments(base, contributions, *, quantity, base_id, stage):
    """Add sourced, signed percentages of one established base before floor.

    No clamp or guessed stage identity: e.g. -120% yields -20% of the base.
    Domain-specific minimums and grouping must be supplied by their own rules.
    """
    contributions = tuple(contributions)
    if any(not isinstance(c, PercentageAdjustment) for c in contributions):
        raise ValueError('typed percentage adjustments required, not fixed factors')
    if any((c.quantity, c.base_id, c.stage) != (quantity, base_id, stage) for c in contributions):
        raise ValueError('different quantities, bases or stages cannot be percentage-pooled')
    return product(base, 1 + sum((c.rate for c in contributions), Fraction()))


def adjustment(base, *rates, quantity, base_id, stage, source=SOURCE):
    return accumulate_adjustments(base, (PercentageAdjustment(rate, quantity, base_id, stage, source) for rate in rates),
                                  quantity=quantity, base_id=base_id, stage=stage)


def accumulate_increases(base, contributions, *, quantity, base_id, stage):
    """One sourced same-base increase stage, summed before its final floor."""
    contributions = tuple(contributions)
    if any(not isinstance(c, PercentageIncrease) for c in contributions):
        raise ValueError('typed percentage increases required')
    if any((c.quantity, c.base_id, c.stage) != (quantity, base_id, stage) for c in contributions):
        raise ValueError('different quantities, bases or stages cannot be percentage-pooled')
    return accumulate_adjustments(base, contributions, quantity=quantity, base_id=base_id, stage=stage)


def increase(base, *rates, quantity, base_id, stage, source=SOURCE):
    return accumulate_increases(base, (PercentageIncrease(rate, quantity, base_id, stage, source) for rate in rates),
                                quantity=quantity, base_id=base_id, stage=stage)


def stage_stat(base, stage, table):
    """Source CS percentages: +20% per positive stage, -10% per negative.

    A selected/GM replacement table remains an explicit fixed-factor policy.
    Do not infer a new percentage meaning from that alternative table.
    """
    factor = A.exact(table[str(stage)])
    if stage > 0 and factor == 1 + Fraction(stage, 5):
        return increase(base, *([Fraction(1, 5)] * stage), quantity='combat_stat',
                        base_id='unstaged_stat', stage='combat_stages', source='combat/combat-stages')
    if stage < 0 and factor == 1 + Fraction(stage, 10):
        return adjustment(base, *([-Fraction(1, 10)] * -stage), quantity='combat_stat',
                          base_id='unstaged_stat', stage='combat_stages', source='combat/combat-stages')
    return product(base, factor)
