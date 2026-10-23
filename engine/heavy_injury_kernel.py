"""Pure severe-injury proposals. No Engine hooks or source timing policy.

READY proves an outcome only under the explicit local interaction assumptions.
It does not authorize actions or mandate an after-event processing order.
"""
from dataclasses import dataclass, replace
from enum import Enum

class Kind(Enum):
    COST_RESERVED = "cost_reserved"
    ACTION_TAKEN = "action_taken"
    ATTACK_DAMAGE = "attack_damage"
    HP_LOSS = "hp_loss"

class Action(Enum):
    STANDARD = "standard"
    SHIFT = "shift"
    SWIFT = "swift"
    FREE = "free"
    FULL = "full"

class Context(Enum):
    UNKNOWN = "unknown"
    NO_OTHER_INTERACTIONS = "explicitly_no_other_interactions"

@dataclass(frozen=True)
class State:
    hp: int
    temporary_hp: int
    injuries: int
    real_max_hp: int
    actor_kind: str = "trainer"
    def __post_init__(self):
        for name in ("hp", "temporary_hp", "injuries", "real_max_hp"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be integer, not bool")
        if self.temporary_hp < 0 or self.injuries < 0 or self.real_max_hp <= 0:
            raise ValueError("invalid resources or maximum")
        if self.actor_kind not in ("trainer", "pokemon"):
            raise ValueError("source contract covers trainers and Pokemon")

@dataclass(frozen=True)
class Event:
    event_id: str
    kind: Kind
    before: State
    after: State
    action: Action | None = None
    paid_resource: Action | None = None
    in_combat: bool | None = None
    damage: int | None = None
    context: Context = Context.UNKNOWN
    prevention_or_cap: bool | None = None
    def __post_init__(self):
        if not isinstance(self.event_id, str) or not self.event_id:
            raise ValueError("stable caller-supplied event ID required")
        if not isinstance(self.kind, Kind) or not isinstance(self.context, Context):
            raise ValueError("typed event kind/context required")
        if not isinstance(self.before, State) or not isinstance(self.after, State):
            raise ValueError("typed state evidence required")
        if self.action is not None and not isinstance(self.action, Action):
            raise ValueError("typed action required")
        if self.paid_resource is not None and not isinstance(self.paid_resource, Action):
            raise ValueError("typed payment provenance required")
        if self.in_combat is not None and type(self.in_combat) is not bool:
            raise ValueError("combat evidence must be bool or unknown")
        if self.prevention_or_cap is not None and type(self.prevention_or_cap) is not bool:
            raise ValueError("prevention evidence must be bool or unknown")
        if self.damage is not None and (type(self.damage) is not int or self.damage < 0):
            raise ValueError("nonnegative integer damage required")

@dataclass(frozen=True)
class Snapshot:
    state: State
    applied_event_ids: frozenset[str] = frozenset()

@dataclass(frozen=True)
class Proposal:
    status: str
    reason: str
    snapshot: Snapshot
    loss: int = 0
    evidence: tuple[str, ...] = ()

def _subtract(state, amount):
    """Arithmetic only: temporary HP lost first for other effects (ch07:623)."""
    temporary = min(state.temporary_hp, amount)
    return replace(state, temporary_hp=state.temporary_hp-temporary,
                   hp=state.hp-(amount-temporary))

def _crosses_marker(before, after):
    # Doubled integer arithmetic avoids inventing odd-max-HP rounding rules.
    if after.hp >= before.hp:
        return False
    h = before.real_max_hp
    k = min(1, (2 * before.hp - 1) // h)
    return k * h >= 2 * after.hp

def evaluate(snapshot, event):
    """Pure proposal from observed post-event evidence, not a timing policy.

    Attack READY requires equal final states in both candidate local orders,
    with no marker/fainting boundary in either. Caller interaction/provenance
    claims remain unverified by this kernel. Pending does not consume the ID.
    """
    def result(status, reason, state=None, loss=0, evidence=()):
        out = snapshot if state is None else Snapshot(
            state, snapshot.applied_event_ids | frozenset((event.event_id,)))
        return Proposal(status, reason, out, loss, evidence)
    if event.event_id in snapshot.applied_event_ids:
        return result("not_applicable", "event_already_applied")
    if snapshot.state != event.after:
        return result("pending", "observed_state_does_not_match_event")
    if event.kind in (Kind.COST_RESERVED, Kind.HP_LOSS):
        return result("not_applicable", "not_a_source_trigger")
    before, after = event.before, event.after
    if (before.real_max_hp, before.actor_kind) != (after.real_max_hp, after.actor_kind):
        return result("pending", "actor_kind_or_maximum_changed")
    if before.injuries != after.injuries:
        return result("pending", "injury_count_sampling_unresolved")
    if before.injuries < 5:
        return result("not_applicable", "fewer_than_five_injuries")
    if event.kind is Kind.ACTION_TAKEN:
        if event.action is Action.FULL:
            return result("pending", "full_action_standard_consequence_unresolved")
        if event.action is None:
            return result("pending", "actual_action_kind_unknown")
        if event.action is not Action.STANDARD:
            if event.paid_resource is Action.STANDARD:
                return result("pending", "standard_paid_substitution_consequence_unresolved")
            if event.action in (Action.SHIFT, Action.SWIFT) and event.paid_resource is not event.action:
                return result("pending", "action_payment_provenance_unresolved")
            return result("not_applicable", "not_a_standard_action")
        if event.in_combat is None:
            return result("pending", "combat_context_unknown")
        if not event.in_combat:
            return result("not_applicable", "standard_branch_requires_combat")
    if event.kind is Kind.ATTACK_DAMAGE and event.in_combat is not True:
        return result("pending", "attack_outside_combat_scope_unresolved")
    if event.context is not Context.NO_OTHER_INTERACTIONS:
        return result("pending", "other_effect_interactions_unknown")
    if event.prevention_or_cap is not False:
        return result("pending", "prevention_or_cap_composition_unresolved")
    if before.hp <= 0 or after.hp <= 0 or before.injuries >= 10:
        return result("pending", "incapacitation_or_death_interaction_unresolved")
    loss = before.injuries
    if event.kind is Kind.ACTION_TAKEN:
        if before != after:
            return result("pending", "action_effect_changes_actor_state")
        final = _subtract(after, loss)
        if final.hp <= 0:
            return result("pending", "loss_would_incapacitate_actor")
        if _crosses_marker(after, final):
            return result("pending", "loss_crosses_injury_marker")
        return result("ready", "stable_local_standard_consequence", final, loss,
                      ("ch07:712", "ch07:623", "restricted_no_interaction_model"))
    if event.damage is None or event.damage == 0:
        return result("pending", "positive_attack_damage_not_established")
    predicted_damage = _subtract(before, event.damage)
    if predicted_damage != after:
        return result("pending", "attack_evidence_has_additional_state_changes")
    if after.hp == before.hp:
        return result("pending", "fully_absorbed_attack_trigger_unresolved")
    # Raw attack amount may meet Massive Damage despite temporary HP absorption.
    # Do not choose the injury-evaluation phase; retain the ambiguous boundary.
    if 2 * event.damage >= before.real_max_hp:
        return result("pending", "massive_damage_injury_evidence_unresolved")
    if _crosses_marker(before, after):
        return result("pending", "attack_crosses_injury_marker")
    loss_first = _subtract(before, loss)
    final_loss_first = _subtract(loss_first, event.damage)
    final_damage_first = _subtract(after, loss)
    paths = ((before, loss_first), (loss_first, final_loss_first),
             (before, after), (after, final_damage_first))
    if any(end.hp <= 0 for start, end in paths):
        return result("pending", "ordering_involves_incapacitation")
    if any(_crosses_marker(start, end) for start, end in paths):
        return result("pending", "ordering_involves_injury_marker")
    if final_loss_first != final_damage_first:
        return result("pending", "candidate_orders_disagree")
    return result("ready", "restricted_candidate_orders_agree", final_damage_first,
                  loss, ("ch07:712", "ch07:623", "both_local_orders_compared"))
