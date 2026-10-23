"""Shared check arithmetic and explicit adjudication boundaries.
Ordinary ranks only. Specialized dice, multiple helpers, and effect composition
must be resolved through a sourced extension before calling this base procedure.
"""
if __package__:
    from . import arithmetic_policy as M
else:
    import arithmetic_policy as M
from dataclasses import dataclass
from copy import deepcopy
from typing import Optional


def integer(value, name, minimum=None, maximum=None):
    if type(value) is not int or (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ValueError('invalid '+name)
    return value


def dice(values, count=None):
    values=tuple(values)
    if count is not None and len(values)!=count:raise ValueError('dice count mismatch')
    for value in values:integer(value,'d6 face',1,6)
    return values


def validate_request(rank, mods=0, helper_rank=0, penalty_count=0, helper_bonus=None):
    integer(rank,'ordinary rank',1,6)
    integer(mods,'modifier')
    integer(helper_rank,'effective helper rank',0,8)
    if helper_rank in (1,2,7):raise ValueError('helper must be at least Novice (rank 3)')
    integer(penalty_count,'penalty count',0)
    if helper_bonus is not None:
        integer(helper_bonus,'resolved assistance bonus',0)
        if helper_bonus not in (M.ratio(helper_rank,2),helper_rank):raise ValueError('unresolved assistance formula')


@dataclass(frozen=True)
class SkillRoll:
    rank: int
    faces: tuple
    modifier: int=0
    helper_rank: int=0
    penalties: tuple=()
    helper_bonus: Optional[int]=None

    def __post_init__(self):
        validate_request(self.rank,self.modifier,self.helper_rank,len(self.penalties),self.helper_bonus)
        object.__setattr__(self,'faces',dice(self.faces,self.rank))
        object.__setattr__(self,'penalties',dice(self.penalties))

    @property
    def total(self):
        return sum(self.faces)+self.modifier+(M.ratio(self.helper_rank,2) if self.helper_bonus is None else self.helper_bonus)-sum(self.penalties)


@dataclass(frozen=True)
class AdjustedSkillRoll(SkillRoll):
    """A sourced adapter supplies a changed pool; base rank remains separate."""
    dice_count: int=0

    def __post_init__(self):
        validate_request(self.rank,self.modifier,self.helper_rank,len(self.penalties),self.helper_bonus)
        integer(self.dice_count,'resolved skill pool dice count',0)
        object.__setattr__(self,'faces',dice(self.faces,self.dice_count))
        object.__setattr__(self,'penalties',dice(self.penalties))


@dataclass(frozen=True)
class CheckResult:
    total: int
    dc: int
    margin: int
    passed: bool


def against_dc(roll, dc):
    integer(dc,'DC')
    return CheckResult(roll.total,dc,roll.total-dc,roll.total>=dc)


def opposed(challenger, defender):
    """Defender is the actor maintaining the status quo (ch06:33-34)."""
    return 'challenger' if challenger.total>defender.total else 'defender'


def team(rolls, ordinary_dc, required_people):
    """Default equal contributions; GM-specific weighting is an external override."""
    rolls=tuple(rolls)
    if not rolls:raise ValueError('team needs participants')
    integer(ordinary_dc,'DC');integer(required_people,'required people',1)
    total=sum(r.total for r in rolls);dc=ordinary_dc*required_people
    return CheckResult(total,dc,total-dc,total>=dc)


def weighted_team(rolls,ordinary_dc,required_people,weights):
    """GM-selected contribution weights; threshold still uses required people."""
    rolls,weights=tuple(rolls),tuple(weights)
    if not rolls or len(weights)!=len(rolls):raise ValueError('one weight per participant required')
    for value in weights:integer(value,'explicit contribution multiplier',1)
    integer(ordinary_dc,'DC');integer(required_people,'required people',1)
    total=sum(r.total*w for r,w in zip(rolls,weights));dc=ordinary_dc*required_people
    return CheckResult(total,dc,total-dc,total>=dc)


@dataclass(frozen=True)
class ExtendedResult:
    total: int
    dc: int
    attempts_used: int
    attempt_limit: Optional[int]
    status: str


def extended(rolls, ordinary_dc, complexity, rank, limited, *, effective_rank=None):
    """Evaluate recorded interval rolls; scheduling/interval duration is GM-owned.
    Completion may occur on the final allowed attempt. A finished history cannot
    accept later rolls, which would improperly spend time or consume randomness.
    """
    rolls=tuple(rolls)
    integer(ordinary_dc,'DC');integer(complexity,'complexity',2,5)
    integer(rank,'ordinary rank',1,6)
    if type(limited) is not bool:raise ValueError('limit policy requires a GM decision')
    if effective_rank is None:effective_rank=rank
    integer(effective_rank,'rank-dependent effect rank',1,8)
    if effective_rank not in (rank,8) or (effective_rank==8 and rank!=6):
        raise ValueError('effective rank requires a sourced Master-rank extension')
    limit=M.ratio(effective_rank,2) if limited else None
    dc=ordinary_dc*complexity;total=0
    for i,roll in enumerate(rolls):
        if total>=dc or (limit is not None and i>=limit):raise ValueError('roll after terminal extended check')
        if roll.rank!=rank:raise ValueError('rank change requires an explicit extension')
        total+=roll.total
    status='complete' if total>=dc else ('exhausted' if limit is not None and len(rolls)>=limit else 'in_progress')
    return ExtendedResult(total,dc,len(rolls),limit,status)


@dataclass(frozen=True)
class PendingDecision:
    required: str
    check: Optional[CheckResult]=None
    declaration: Optional[dict]=None
    basis: Optional[dict]=None


@dataclass(frozen=True)
class ActionOutcome:
    """Ordinary GM decision with the raw check and any explicit cost retained."""
    outcome: str
    description: str
    check: Optional[CheckResult]=None
    cost: Optional[str]=None
    failure_margin_accepted: bool=False
    declaration: Optional[dict]=None
    basis: Optional[dict]=None


def validate_adjudication(outcome=None,description=None,cost=None,failure_margin_accepted=False):
    if outcome is not None and outcome not in ('success','failure','success_with_cost','other'):
        raise ValueError('unknown outcome')
    for value in (description,cost):
        if value is not None and (not isinstance(value,str) or not value.strip()):
            raise ValueError('nonempty decision text required')
    if type(failure_margin_accepted) is not bool:raise ValueError('GM margin decision must be boolean')


def adjudicate(check=None, *, outcome=None, description=None, cost=None, failure_margin_accepted=False, declaration=None):
    declaration=deepcopy(declaration)
    validate_adjudication(outcome,description,cost,failure_margin_accepted)
    if outcome is None or description is None:
        return PendingDecision('GM world response / consequences',check,declaration)
    if outcome=='success_with_cost' and cost is None:
        return PendingDecision('explicit cost of success',check,declaration)
    if check is not None:
        if not check.passed and outcome=='success_with_cost' and not failure_margin_accepted:
            return PendingDecision('GM acceptance of the narrow failure margin',check,declaration)
        if (not check.passed and outcome not in ('failure','success_with_cost')) or (check.passed and outcome not in ('success','success_with_cost')):
            return PendingDecision('external ruling beyond ordinary check outcome',check,declaration)
    return ActionOutcome(outcome,description,check,cost,failure_margin_accepted,declaration)
