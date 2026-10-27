"""Typed attack observation and explicit pending boundary.

Only the explicitly certified native single-attack subset can use the kernel's
NO_OTHER_INTERACTIONS. All other resolution is an explicit external
ruling receipt, not source-conformance proof or a restored Python continuation.
"""
import copy, math
from enum import Enum
import heavy_injury_kernel as K

class Producer(Enum):
    RESOLVED_HIT = "Engine.resolve_attack_damage"
    EFFECT_DAMAGE = "HISTORY.effect_loss.fixed_damage"
    SECOND_HIT = "EXT.after_move.second_hit"
    DELAYED_HIT = "EXT.end_of_turn.delayed_attack"

class ContinuationDisposition(Enum):
    RESOLVED_EXTERNALLY = "remaining_effects_resolved_externally"
    CANCELLED_BY_RULING = "remaining_effects_cancelled_by_explicit_ruling"

class HeavyPending(RuntimeError):
    def __init__(self, event_id):
        self.event_id = event_id
        super().__init__(f"unresolved heavy injury event {event_id}")

def copy_move(engine, move):
    """Copy a move receipt while retaining references to actual world actors."""
    anchors = engine.gm._snapshot_actors({"move": move})
    return copy.deepcopy(move, anchors)


def initialize(engine, *, native_types=None):
    engine._heavy_native_types = native_types
    engine._heavy_sequence = 0
    engine._heavy_events = {}
    engine._heavy_pending = None
    engine._heavy_resolution_history = []
    engine._heavy_native_receipts = {}
    engine._heavy_activation_sequence = 0
    engine._heavy_driver_result = None
    engine._heavy_standard_receipts = {}
    engine._heavy_standard_sequence = 0

def ensure_clear(engine):
    pending = getattr(engine, "_heavy_pending", None)
    if pending is not None:
        raise HeavyPending(pending)
    import environmental_effects as ENVIRONMENT
    ENVIRONMENT.ensure_clear(engine)

def observe(c):
    return dict(hp=c.hp, temporary_hp=c.temp_hp, injuries=c.injuries,
                real_max_hp=c.base_max_hp, actor_kind=c.kind,
                conditions=sorted(c.conditions), dead=c.dead,
                form=copy.deepcopy(getattr(c,"form",None)))

def _kernel_state(state):
    return K.State(**{k:state[k] for k in
        ("hp","temporary_hp","injuries","real_max_hp","actor_kind")})

@__import__('channeler').native_move
def apply_attack_damage(engine, attacker, target, amount, move, *, producer, remainder, native_context=None, actual_damage_type=None):
    """Retain the original hit and halt before caller's remaining effects.

    take_damage's existing own primitive/hook behavior is observed, not certified
    as the right phase relative to heavy loss. The remainder description is not
    executable and must never be treated as a resumable stack.
    """
    ensure_clear(engine)
    import temporary_hp as TEMP_HP
    TEMP_HP.ensure_certain(engine, attacker)
    TEMP_HP.ensure_certain(engine, target)
    if not isinstance(producer, Producer):
        raise ValueError("reviewed attack producer enum required")
    if type(amount) is not int or amount < 0:
        raise ValueError("nonnegative integral attack damage required")
    certificate = None
    receipt = validate_native_receipt(engine,native_context,attacker,target,move)
    if receipt is not None:
        engine._heavy_native_receipts.pop(native_context)
        diagnostic = receipt["diagnostic"]
        current_mm,_ = engine.r.move_mech(move.get("id"))
        certificate = certify_native_context(engine,attacker,target,move,current_mm,
                                              ordinary_single=diagnostic.ordinary_single)
        certified = not certificate.failures and not diagnostic.failures
    else:
        certified = False
    import channeler as CHANNEL
    replacement=CHANNEL.replace_attack(engine,attacker,target,amount,move,actual_damage_type)
    if replacement is not None:return replacement
    before = observe(target)
    cap = copy.deepcopy(getattr(target,"damage_cap",None))
    import attack_damage_history as HISTORY
    with HISTORY.damage_source(engine,target,move), __import__('focus_punch').damage_scope(engine,target) as focus_damage:
        if receipt is None:
            original_result = engine.take_damage(target, amount)
        else:
            # Keep the existing native damage transaction even for awake actors.
            import state_grants as GRANTS
            original_result=GRANTS.transition(engine,target,
                lambda staged,actual:staged.take_damage(actual,amount))
    import taskmaster as TASK
    hardened=TASK.active(target) is not None
    hardened_loss=0
    if hardened and amount>0 and target.injuries>=5 and not TASK.immune_loss(target):
        hardened_loss=target.injuries
        engine.lose_hp(target,hardened_loss,source='heavily_injured_attack')
    import persistent_conditions as PERSISTENT
    PERSISTENT.attack_hit(engine,target,move if actual_damage_type is None else dict(move,type=actual_damage_type))
    after = observe(target)
    engine._heavy_sequence += 1
    event_id = f"heavy-attack-{engine._heavy_sequence}"
    event = K.Event(event_id, K.Kind.ATTACK_DAMAGE, _kernel_state(before),
                    _kernel_state(after), in_combat=bool(engine.encounter_active),
                    damage=amount, context=K.Context.NO_OTHER_INTERACTIONS if certified else K.Context.UNKNOWN,
                    prevention_or_cap=False if certified else True if cap else None)
    proposal = K.evaluate(K.Snapshot(event.after), event)
    # Raw Massive Damage could cross the heavy threshold even when the current
    # primitive evaluated its injury after temp absorption. Do not certify that
    # primitive's injury accounting by merely copying its after-count.
    # A raw massive hit is not a second potential injury when the primitive
    # already evaluated the same unabsorbed damage. Preserve uncertain caps,
    # temp absorption and overridden thresholds; do not double-count the normal
    # massive injury in a below-five before/after transition.
    same_massive_basis = (not cap and before["temporary_hp"] == 0
                          and before["hp"] - after["hp"] == amount
                          and float(engine.formula("massive_damage")) == 0.5)
    potential_threshold = (max(before["injuries"],after["injuries"]) >= 4
                           and 2*amount >= before["real_max_hp"]
                           and not same_massive_basis)
    import taskmaster as TASK
    relevant = (max(before["injuries"],after["injuries"]) >= 5 or potential_threshold) and not hardened and not __import__('berserker').lessons(target)
    issues = []
    if relevant:
        if not certified:issues.append("production_effect_interactions_not_proven")
        if not engine.encounter_active:issues.append("noncombat_attack_scope_unresolved")
        if cap:issues.append("cap_composition_unresolved")
        if before["injuries"] != after["injuries"]:issues.append("injury_count_sampling_unresolved")
        if potential_threshold:issues.append("raw_massive_damage_threshold_requires_review")
        if after["hp"] <= 0 or after["dead"]:issues.append("incapacitation_order_unresolved")
        if proposal.status == "pending":issues.append(proposal.reason)
    packet = dict(event_id=event_id, kind="attack_damage", producer=producer.value,
                  attacker=attacker, target=target, move=copy_move(engine, move),
                  amount=amount, before=before, observed_after=after,
                  original_primitive_result=original_result, cap_observed=cap,
                  round=engine.round_no, elapsed_seconds=engine.elapsed_seconds,
                  context="certified_native_single" if certified else "unknown",
                  context_evidence=dict(checked=list(certificate.checked),failures=list(certificate.failures)) if certificate else None,
                  kernel_status=proposal.status,
                  kernel_reason=proposal.reason, issues=list(dict.fromkeys(issues)),
                  unexecuted_remainder=remainder, continuation_reified=False,
                  status="pending" if relevant else "not_applicable")
    if focus_damage is not None:packet['focus_punch_damage']=copy.deepcopy(focus_damage)
    engine._heavy_events[event_id] = packet
    if hardened:
        packet['status']='applied'
        packet['heavy_consequence']=dict(kind='hp_loss',amount=hardened_loss,
            source=TASK.CLASS,acting_exemption=False,immune=TASK.immune_loss(target),
            order_claim='actual attack damage then current Hardened HP-loss policy')
        return original_result
    if relevant and certified and proposal.status == "ready":
        # The kernel established both local orders agree and no marker/faint
        # boundary. Caps/interactions are absent by the concrete certificate.
        # This typed HP-loss consequence is not another attack-damage event.
        final = proposal.snapshot.state
        import temporary_hp as TEMP_HP
        TEMP_HP.absorb(engine, target, target.temp_hp - final.temporary_hp)
        target.hp = final.hp
        import bandages as BANDAGES
        BANDAGES.on_hp_change(engine,target,after["hp"],target.hp)
        packet["status"] = "applied"
        packet["heavy_consequence"] = dict(kind="hp_loss", amount=proposal.loss,
            before=after, after=observe(target), recursive_attack=False,
            order_claim="both_restricted_orders_agree")
        engine.log(f"[중상] {event_id}: 검증된 국소 공격 문맥, 체력 손실 {proposal.loss}","common/heavy-injury")
        return original_result
    if relevant:
        engine._heavy_pending = event_id
        engine.log(f"[중상 보류] {event_id}: 원래 공격 피해 보존; 추가 손실/후속 순서 미정",
                   "common/heavy-injury")
        raise HeavyPending(event_id)
    return original_result

def acknowledge_ruling(engine, event_id, target, *, expected_current_state,
                       ruling, disposition, continuation_reason):
    """Acknowledge already adjudicated state; do not calculate/apply HP changes.

    This requires an explicit external decision about both heavy consequences
    and the abandoned caller continuation. It is NOT automatic resume or proof
    the ruling follows an otherwise unresolved source condition.
    """
    packet = engine._heavy_events.get(event_id)
    if packet is None or packet["status"] != "pending" or engine._heavy_pending != event_id:
        raise ValueError("event is not the current unresolved event")
    if packet["target"] is not target:
        raise ValueError("event target identity mismatch")
    if not isinstance(disposition, ContinuationDisposition):
        raise ValueError("explicit continuation disposition required")
    if not isinstance(ruling,str) or not ruling.strip():
        raise ValueError("explicit ruling required")
    if not isinstance(continuation_reason,str) or not continuation_reason.strip():
        raise ValueError("unexecuted continuation must be explicitly accounted for")
    actual = observe(target)
    if expected_current_state != actual:
        raise ValueError("adjudicated state drift; no resolution applied")
    receipt = dict(event_id=event_id,target=target,ruling=ruling,
                   disposition=disposition.value,continuation_reason=continuation_reason,
                   adjudicated_state=copy.deepcopy(actual),original_after=copy.deepcopy(packet["observed_after"]),
                   source_conformance_proven=False)
    packet["status"] = "resolved_by_external_ruling"
    packet["resolution"] = receipt
    engine._heavy_resolution_history.append(receipt)
    engine._heavy_pending = None
    return receipt

# This small whitelist proves only the native, ordinary, single-target Struggle
# path. Unknown/extra state rejects the certificate instead of being ignored.
from dataclasses import dataclass

@dataclass(frozen=True)
class NativeContext:
    engine: object
    attacker: object
    target: object
    move_id: str
    ordinary_single: bool
    failures: tuple
    checked: tuple

def _passive(value,stack=None):
 # Exact builtins only: no __bool__/__iter__/numeric/format callbacks.
 kind=type(value)
 if kind in (str,int,bool,type(None)):return True
 if kind is float:return math.isfinite(value)
 if kind not in (list,tuple,set,frozenset,dict):return False
 stack=set() if stack is None else stack
 if id(value) in stack:return False
 stack.add(id(value))
 try:
  if kind is dict:return all(_passive(k,stack) and _passive(v,stack) for k,v in value.items())
  return all(_passive(v,stack) for v in value)
 finally:stack.remove(id(value))

def passive_prefix_failures(engine,actor,target,*,require_actor_budget=False):
 failures=[]
 canonical=getattr(engine,'_heavy_native_types',())
 if type(canonical) is not tuple:canonical=()
 if len(canonical)!=3 or type(engine) is not canonical[0] or type(engine.r) is not canonical[1] or type(actor) is not canonical[2] or type(target) is not canonical[2]:
  failures.append('noncanonical_runtime_type')
 for label,c in [('actor',actor),('target',target)]:
  for field,value in vars(c).items():
   if field=='r':
    if value is not engine.r:failures.append(label+':foreign_rules_reference')
   elif field=='last_target':
    if value is not None and (len(canonical)!=3 or type(value) is not canonical[2] or value.r is not engine.r):
     failures.append(label+':noncanonical_last_target')
   elif not _passive(value):failures.append(label+':nonpassive_state:'+field)
  budget=getattr(c,'budget',None)
  if budget is not None and (type(budget) is not dict or any(type(k) is not str or type(v) is not int for k,v in budget.items())):
   failures.append(label+':nonplain_budget')
  if require_actor_budget and label=='actor' and type(budget) is not dict:failures.append('actor:missing_native_budget')
  if hasattr(c,'_ap_bound_effects') and not __import__('bound_ap').inert_history(c):
   failures.append(label+':bound_effect_not_inert_history')
 # These containers are read by native use, accuracy, damage and no-effect
 # after_move/fire_event paths. Token/identity ledgers remain trusted internals.
 for field in ('zones','zone_cells','_smoke_regions','weather','field','taunt','effect_stats','gm_prompts',
               'delayed','hazards','hazards_nogrid','_hazard_sequence','_hazard_region_sequence','zone_rules','condition_params',
               'session_frequency','session_epoch','encounter_active','round_no',
               'round_start_seconds','death_enabled','friendly_battle'):
  if not _passive(getattr(engine,field,None)):failures.append('engine:nonpassive_state:'+field)
 for field in ('everyone','_time_actors'):
  value=getattr(engine,field,None)
  if type(value) is not list or len(canonical)!=3 or any(type(c) is not canonical[2] or c.r is not engine.r for c in value):
   failures.append('engine:noncanonical_actor_list:'+field)
 for label,obj in [('rulings',engine.rulings),('rules.rulings',engine.r.rulings)]:
  for field,value in vars(obj).items():
   if not _passive(value):failures.append(label+':nonpassive_state:'+field)
 # Loaded lookup data is passive, separately from its semantic values below.
 for field,value in vars(engine.r).items():
  if field not in ('rulings','ruleset','selection') and not _passive(value):
   failures.append('rules:nonpassive_state:'+field)
 return failures

def inert_turn_bookkeeping(engine,actor):
    """Only reviewed turn markers and a certain ordinary barrier are passive."""
    import temporary_hp as TEMP_HP
    value=getattr(actor,'custom_conditions',None)
    if type(value) is not dict or set(value)-{'combat_turn_serial','blessing_ignore_turn_open',TEMP_HP.STATE}:return False
    serial=value.get('combat_turn_serial',0)
    if type(serial) is not int or serial<0:return False
    if 'blessing_ignore_turn_open' in value:
        if value['blessing_ignore_turn_open'] is not True or engine._active_turn_actor is not actor:return False
    state=value.get(TEMP_HP.STATE)
    if state is None:
        if type(actor.temp_hp) is not int or actor.temp_hp!=0:return False
    else:
        # A label alone is not expiry evidence; sourced/stacked/GM pools stay held.
        fields={'kind','source','clock_basis','minimum_seconds','maximum_seconds',
                'birth_round','uncertain_birth','contributions'}
        if type(state) is not dict or set(state)!=fields:return False
        if (state['kind']!='rule_grant' or state['clock_basis']!=TEMP_HP.CLOCK
                or state['uncertain_birth'] is not False):return False
        rows=state['contributions']
        if (type(rows) is not list or len(rows)!=1 or type(rows[0]) is not dict
                or set(rows[0])!={'amount','source','minimum_seconds','maximum_seconds'}
                or rows[0]['source'] is not None):return False
        birth=state['birth_round']
        if birth is not None and (type(birth) is not int or not 0<=birth<=engine.round_no):return False
        try:
            TEMP_HP.validate(actor)
            duration=TEMP_HP._policy(engine)
        except (ValueError,TypeError,KeyError):return False
        if not 0<state['minimum_seconds']==state['maximum_seconds']<=duration:return False
    # These exact flags gain behavior only with the corresponding live source.
    return not actor.spec.get('blessing_status_ignores')


def single_target_move_data(move,target):
    """Separate one native target binding from the source Move definition.

    Engine.use_move retains live actors in this field. It is not rule data or
    a receipt to ignore: only the exact current single target is reviewed here.
    A raw source Move remains usable for diagnostics, never occurrence authority.
    """
    if type(move) is not dict or any(type(key) is not str for key in move):return None
    if '_actual_targets' in move:
        targets=move['_actual_targets']
        if type(targets) is not tuple or len(targets)!=1 or targets[0] is not target:return None
    return {key:value for key,value in move.items() if key!='_actual_targets'}


def certify_native_context(engine, attacker, target, move, mm, *, ordinary_single):
    failures=[]
    checked=[]
    # Bind canonical classes from Engine.__init__'s own module, including CLI
    # __main__. Display names and inherited methods do not certify identity.
    native = getattr(engine,"_heavy_native_types",None)
    if not isinstance(native,tuple) or len(native)!=3:
        failures.append("native_type_binding_missing")
    else:
        if type(engine) is not native[0]:failures.append("engine_subclass_not_reviewed")
        if type(engine.r) is not native[1]:failures.append("rules_subclass_not_reviewed")
        for label,c in (("attacker",attacker),("target",target)):
            if type(c) is not native[2]:failures.append(label+":actor_subclass_not_reviewed")
            if getattr(c,"r",None) is not engine.r:failures.append(label+":different_rules_context")
    if failures:
        return NativeContext(engine,attacker,target,move.get("id"),ordinary_single,
                             tuple(failures),("canonical_type_identity_checked",))
    checked.append("canonical_type_identity_checked")
    # No READY consequence is needed for a below-threshold pair. A later
    # injury-count change or uncertain raw Massive crossing still reaches the
    # existing pending evaluator; this shortcut grants no native certificate.
    if (type(attacker.injuries) is int and type(target.injuries) is int
            and attacker.injuries<5 and target.injuries<5):
        return NativeContext(engine,attacker,target,move.get("id"),ordinary_single,
            ("below_threshold_pair_not_certified",),())
    for method in ('roll_damage', 'take_damage', 'resolve_attack_damage', 'marker_injuries', 'check_fainted', 'type_multiplier', 'formula', 'log'):
        if method in vars(engine):failures.append('overridden_engine_method:'+method)
    for method in ('move', 'move_mech', 'mech', 'formula'):
        if method in vars(engine.r):failures.append('overridden_rules_method:'+method)
    if failures:
        return NativeContext(engine,attacker,target,move.get("id"),ordinary_single,tuple(failures),tuple(checked))
    failures=passive_prefix_failures(engine,attacker,target)
    checked=[]
    if failures:
        return NativeContext(engine,attacker,target,move.get("id"),ordinary_single,tuple(failures),tuple(checked))
    if type(engine.log_lines) is not list or any(type(line) is not str for line in engine.log_lines):
        failures.append("noncanonical_log_sink")
    if ordinary_single is not True:failures.append("not_ordinary_single_activation")
    source_move=single_target_move_data(move,target)
    if (source_move is None or not _passive(source_move)
            or source_move.get("id")!="struggle" or source_move != engine.r.move("struggle") or mm != {}):
        failures.append("not_empty_mech_native_struggle")
    if not engine.encounter_active or engine._active_turn_actor is not attacker or engine.round_start_seconds is None:
        failures.append("ordinary_active_combat_context_missing")
    if attacker is target:failures.append("self_target_interaction")
    if attacker.injuries>=5:failures.append("attacker_standard_heavy_consequence_unresolved")
    for method in ("roll_damage","take_damage","resolve_attack_damage","marker_injuries",
                   "check_fainted","type_multiplier","formula","log"):
        if method in vars(engine):failures.append("overridden_engine_method:"+method)
    native_types = getattr(engine,"_heavy_native_types",None)
    if (not native_types or type(engine) is not native_types[0]
        or type(engine.r) is not native_types[1]
        or type(attacker) is not native_types[2] or type(target) is not native_types[2]):
        failures.append("noncanonical_runtime_type")
    for method in ("move","move_mech","mech","formula"):
        if method in vars(engine.r):failures.append("overridden_rules_method:"+method)
    for label,c in (("attacker",attacker),("target",target)):
        for field in ("stats","stages"):
            values=getattr(c,field,None)
            if (type(values) is not dict or any(type(k) is not str or type(v) is not int for k,v in values.items())):
                failures.append(label+":nonplain_"+field)
        for field in ("registry","ability_triggers","abilities","modifiers","conditions",
                      "buffs","coats","blessings","counters",
                      "item","shield","next_attack","reflect","damage_cap","form_rule",
                      "form","type_override_next","setup_move","locked_move"):
            if getattr(c,field,None):failures.append(label+":"+field)
        if not inert_turn_bookkeeping(engine,c):failures.append(label+':custom_conditions')
        for field in ("feats","edges","abilities","item"):
            if c.spec.get(field):failures.append(label+":spec."+field)
        if c.dead or c.hp<=0 or c.captured or not c.on_field:
            failures.append(label+":not_ordinary_conscious_on_field")
        checked.append(label+":registered-effects/statuses/items/reactions-empty")
    for field in ("weather","field","grid","zones","zone_cells","_smoke_regions","hazards","hazards_nogrid","_hazard_sequence","_hazard_region_sequence",
                  "delayed","zone_rules","taunt","condition_params","_action_grants"):
        if getattr(engine,field,None):failures.append("engine:"+field)
    for rules in (engine.rulings,engine.r.rulings):
        for field in ("formulas","mech","effects","situational","answers","provider"):
            if getattr(rules,field,None):failures.append("rulings:"+field)
        if any(rules.hooks.values()):failures.append("rulings:hooks")
    for roster in (getattr(engine,"everyone",None),engine.gm.everyone):
        if roster is None or {id(c) for c in roster}!={id(attacker),id(target)}:
            failures.append("extra_or_unknown_roster_interactions")
    checked += ["empty-native-struggle-mech","ordinary-single-activation",
                "no-field-GM-hook-or-registered-response","attacker-not-heavy",
                "two-actor-roster","unmodified-reviewed-engine-methods"]
    return NativeContext(engine,attacker,target,move.get("id"),ordinary_single,
                         tuple(dict.fromkeys(failures)),tuple(checked))


def validate_native_receipt(engine, token, attacker, target, move):
    """Only the live one-use token registered inside Engine.use_move is accepted.
    A diagnostic certificate is never authority. Validation precedes new rolls.
    """
    if token is None:return None
    receipt=engine._heavy_native_receipts.get(token)
    if receipt is None:raise ValueError("native receipt is absent, expired or consumed")
    import taskmaster as TASK
    epoch_current=(receipt["activation_epoch"]==engine._heavy_activation_sequence
                   or TASK.paired_receipt_current(engine,token)
                   or __import__('conquerors_march').paired_receipt_current(engine,token))
    if (receipt["attacker"] is not attacker or receipt["target"] is not target
        or not epoch_current
        or receipt["move_id"]!=move.get("id") or receipt["round"]!=engine.round_no
        or receipt["active_actor"] is not engine._active_turn_actor
        or receipt["move_uses"]!=attacker.move_uses.get(move.get("id"),0)
        or receipt["history_length"]!=len(getattr(attacker,"_action_history",[]))):
        raise ValueError("native receipt actor/target/move/activation epoch mismatch")
    return receipt

def report_driver_pending(engine, error):
    packet=engine._heavy_events.get(error.event_id,{})
    engine._heavy_driver_result=dict(status="incomplete",reason="heavy_injury_pending",
        event_id=error.event_id,producer=packet.get("producer"),
        continuation_reified=False,automatic_resume=False)
    engine.log(f"전투 미완료: 중상 사건 {error.event_id} 재정 필요; 후속 행동/시간/승패 확정 중단",
               "common/heavy-injury")
    return engine._heavy_driver_result
