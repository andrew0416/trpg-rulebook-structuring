"""Native transitions for the selected Chapter 11 boss template.

``actor.spec['encounter_template']`` remains the only durable owner.  This
module derives the boss slots and mutates that owner only from actual round,
turn, HP, condition, frequency and capture consumers.
"""
import arithmetic_policy as NUMERIC
from copy import deepcopy


SUPPORTED_ORDINARY_OPERATIONS = {
    "start_round", "start_of_turn", "use_move", "use_move target",
    "use_move_on", "use_move_on target", "take_damage", "lose_hp",
    "boss capture and normal-form restoration",
}
VARIANTS = {"잠듦": ("졸음", "drowsy"), "얼음": ("냉각", "chilled")}
VARIANT_SOURCES = {stored: source for source, (stored, _) in VARIANTS.items()}
SLOT_CONDITIONS = {"마비", "혼란", "풀죽음"}
STAGES = {"atk", "def", "spa", "spd", "spe"}
BAR_EFFECTS = {
    "vulnerable_until_damaged", "skip_next_turn", "refresh_scene_move",
    "cure_volatile", "raise_stage",
}
FINAL_EFFECTS = {"set_attack_stage_6", "unlock_move", "clear_debuffs"}


def state(actor):
    row = actor.spec.get("encounter_template")
    if isinstance(row, dict) and row.get("active") is True and row.get("kind") == "boss":
        return row
    return None


def supports(actor, operation):
    return state(actor) is not None and operation in SUPPORTED_ORDINARY_OPERATIONS


def require_periodic_round(actor, event):
    """Bind round ticks to the boss boundary that actually issued them."""
    candidates=[state(actor)]+[
        row.get('state') for row in actor.spec.get('retired_encounter_templates',[])
        if row.get('source_id')=='C11-137']
    round_no=event.get('round')
    for row in candidates:
        if not isinstance(row,dict) or row.get('kind')!='boss':continue
        receipt=row.get('round_trigger_receipts',{}).get('boss-round:'+str(round_no))
        if (isinstance(receipt,dict) and receipt.get('kind')=='boss_round_start'
                and receipt.get('round')==round_no and receipt.get('source_id')=='C11-129'
                and event.get('source_id')=='C11-129'):
            return
    raise ValueError('periodic round tick requires its actual boss round-start receipt')


def _integer(value, label, low=0):
    if type(value) is not int or value < low:
        raise ValueError(label + " must be an integer at least " + str(low))
    return value


def action_count(*, pokemon_turns, combat_trainers, focused_command_extra=0):
    """C11-117's full-boss baseline from explicit party observations."""
    return (_integer(pokemon_turns, "Pokemon turns", 1)
            + _integer(combat_trainers, "combat-focused Trainers")
            + _integer(focused_command_extra, "Focused Command extra turns"))


def _initiative_policy(actor):
    import json
    from pathlib import Path
    from source_context import verified_source
    value=json.loads((Path(actor.r.root)/'data/boss-initiative-source-policy.json').read_text(encoding='utf-8'))
    if value.get('schema_version')!=1 or value.get('source')!='ch11-running-the-game/보스-인카운터/일반-보스-템플릿':
        raise ValueError('known boss initiative source policy required')
    verified_source(actor.r,value['source_reference'],label='boss initiative')
    for definition in value['definitions'].values():
        ref=definition['source']
        verified_source(actor.r,ref,label='boss initiative definition',
                        source_root='source-audit' if ref['file'].startswith('source-audit/') else 'input')
    return value


def _initiative_document(value):
    return {'schema':1,'id':'native/boss-initiative-floor','variants':[{
        'rule_id':value['source'],'source':value['source_reference'],
        'values':{'variant':{'$input':'source_text'},'definitions':value['definitions']},
        'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
            'choices':list(value['definitions']),
            'question':'Boss downward Initiative slots: Korean stays above 1; English permits 1. Which complete derivation applies?'}}}]}


def initiative_choices(actor):
    import source_policy as POLICY
    return POLICY.resolve(actor.r,_initiative_document(_initiative_policy(actor)))


def initiative_slots(base_initiative, count, *, downward_minimum=1):
    """C11-118 slot derivation; never imports the contradictory C11-119 sixth slot."""
    base = _integer(base_initiative, "base initiative", 1)
    count = _integer(count, "boss action count", 1)
    values = [base]
    below = base - 5
    if type(downward_minimum)is not int or downward_minimum not in (1,2):
        raise ValueError('known downward Initiative floor required')
    while len(values) < count and below >= downward_minimum:
        values.append(below)
        below -= 5
    above = base + 5
    while len(values) < count:
        values.append(above)
        above += 5
    return [{"id": "boss-action-" + str(index + 1), "initiative": value}
            for index, value in enumerate(values)]


def prepare_configuration(actor, *, total_bars, action_slots, action_basis,
                          base_initiative, capture_level, transition_effects,
                          initiative_source_choice=None):
    if action_basis is not None:
        if not isinstance(action_basis, dict) or set(action_basis) != {
                "pokemon_turns", "combat_trainers", "focused_command_extra"}:
            raise ValueError("boss action basis needs the three explicit party counts")
        count = action_count(**action_basis)
        basis = dict(action_basis, result=count, source_id="C11-117")
    elif action_slots is not None:
        count = len(action_slots)
        basis = {"kind": "explicit_gm_selection", "result": count,
                 "source_id": "C11-117"}
    else:
        raise ValueError("boss actions need explicit party counts or selected action slots")
    if action_slots is None:
        if base_initiative is None:
            base_initiative = actor.staged("spe")
        import source_policy as POLICY
        value=_initiative_policy(actor);document=_initiative_document(value)
        result=POLICY.resolve(actor.r,document,decisions={} if initiative_source_choice is None else {'source_text':initiative_source_choice})
        variant=value['default'] if initiative_source_choice is None else result['values']['variant']
        basis['initiative_derivation']={'base':base_initiative,'variant':variant,
            'choice':deepcopy(initiative_source_choice),'scope':deepcopy(result['decision_scope']),
            'binding':deepcopy(result['source_policy_binding'])}
        action_slots = initiative_slots(base_initiative, count,downward_minimum=value['definitions'][variant]['downward_minimum'])
    elif len(action_slots) != count:
        raise ValueError("boss party basis and action-slot count disagree")
    elif initiative_source_choice is not None:
        raise ValueError('source floor choice applies only to newly derived boss slots')
    if total_bars is None:
        total_bars = count
        bar_basis = "one_per_action"
    else:
        _integer(total_bars, "boss HP bars", 1)
        bar_basis = "one_per_action" if total_bars == count else "explicit_gm_selection"
    if capture_level is not None:
        _integer(capture_level, "captured boss level", 1)
        if capture_level > actor.level:
            raise ValueError("captured boss level cannot exceed its encounter level")
    effects = deepcopy(list(transition_effects))
    runtime = {
        "version": 1, "action_basis": basis, "hp_bar_basis": bar_basis,
        "half_bar_injury_awarded": False, "pending_skip_turns": 0,
        "vulnerable_until_damaged": False, "capture_level": capture_level,
        "flinch_rounds": {}, "damage_roll_penalty": 0,
    }
    return total_bars, deepcopy(action_slots), effects, runtime


def _validate_effect(actor, effect):
    if not isinstance(effect, dict) or not {"when", "kind"} <= set(effect):
        raise ValueError("boss transition effect needs when and kind")
    when, kind = effect["when"], effect["kind"]
    if when == "bar_lost" and kind not in BAR_EFFECTS:
        raise ValueError("unknown selected stagger effect")
    if when == "final_bar" and kind not in FINAL_EFFECTS:
        raise ValueError("unknown selected final-bar effect")
    if when not in ("bar_lost", "final_bar"):
        raise ValueError("unknown boss transition timing")
    expected = {"when", "kind"}
    if kind in ("refresh_scene_move", "unlock_move"):
        expected.add("move_id")
        move_id = effect.get("move_id")
        if not isinstance(move_id, str) or move_id not in actor.r.moves:
            raise ValueError("selected transition Move must be canonical")
        if kind == "refresh_scene_move" and move_id not in actor.moves:
            raise ValueError("only a possessed Scene Move can be refreshed")
        if kind == "refresh_scene_move":
            import frequency as FREQUENCY
            raw = actor.r.moves_mech.get(move_id, {}).get("header", {}).get("frequency")
            if FREQUENCY.parse(raw or actor.r.move(move_id).get("frequency"))[0] != "scene":
                raise ValueError("only a possessed Scene Move can be refreshed")
    elif kind == "cure_volatile":
        expected.add("condition")
        if not isinstance(effect.get("condition"), str):
            raise ValueError("selected volatile condition identity required")
    elif kind == "raise_stage":
        expected.add("stage")
        if effect.get("stage") not in STAGES:
            raise ValueError("selected combat stage required")
    if set(effect) != expected:
        raise ValueError("unexpected boss transition effect fields")


def validate(actor, row=None):
    row = state(actor) if row is None else row
    if not isinstance(row, dict) or row.get("kind") != "boss":
        return True
    runtime = row.get("boss_runtime")
    if not isinstance(runtime, dict) or runtime.get("version") != 1:
        raise ValueError("versioned boss runtime state required")
    required = {"version", "action_basis", "hp_bar_basis",
                "half_bar_injury_awarded", "pending_skip_turns",
                "vulnerable_until_damaged", "capture_level", "flinch_rounds",
                "damage_roll_penalty"}
    if set(runtime) != required:
        raise ValueError("boss runtime state shape changed")
    basis = runtime["action_basis"]
    if not isinstance(basis, dict) or basis.get("source_id") != "C11-117":
        raise ValueError("boss action basis source required")
    _integer(basis.get("result"), "boss action result", 1)
    if basis["result"] != len(row["action_slots"]):
        raise ValueError("boss action basis and slots disagree")
    if 'initiative_derivation' in basis:
        import source_selection as SELECTION
        value=_initiative_policy(actor);document=_initiative_document(value)
        record=basis['initiative_derivation']
        if type(record)is not dict or set(record)!={'base','variant','choice','scope','binding'}:
            raise ValueError('actual producing boss initiative derivation required')
        SELECTION.policy_values(record['binding'],document['variants'])
        scope=record['scope'];choice=record['choice'];variant=record['variant']
        if (type(scope)is not dict or scope.get('policy_id')!=document['id']
                or scope.get('definition_hash')!=SELECTION.fingerprint(document)
                or scope.get('selected_id')!=value['source'] or scope.get('selected_version') is not None):
            raise ValueError('producing boss source scope changed')
        if choice is None:
            if variant!=value['default']:raise ValueError('authored default boss source changed')
        elif (type(choice)is not dict or set(choice)!={'value','reason','scope'}
              or choice['value']!=variant or choice['scope']!=scope
              or not isinstance(choice['reason'],str) or not choice['reason'].strip()):
            raise ValueError('actual scoped boss source choice required')
        if variant not in value['definitions'] or row['action_slots']!=initiative_slots(
                record['base'],basis['result'],downward_minimum=value['definitions'][variant]['downward_minimum']):
            raise ValueError('boss slots differ from their producing source derivation')
    if runtime["hp_bar_basis"] not in ("one_per_action", "explicit_gm_selection"):
        raise ValueError("boss HP-bar basis required")
    for key in ("half_bar_injury_awarded", "vulnerable_until_damaged"):
        if type(runtime[key]) is not bool:
            raise ValueError("boss runtime flags must be explicit booleans")
    _integer(runtime["pending_skip_turns"], "pending skipped turns")
    if runtime["damage_roll_penalty"] not in (0, -10):
        raise ValueError("boss drowsy/chilled damage penalty must be zero or -10")
    level = runtime["capture_level"]
    if level is not None:
        _integer(level, "captured boss level", 1)
    capture=row.get('capture_form')
    if level is not None and level!=row['normal_form_baseline']['level']:
        if (not isinstance(capture,dict) or capture.get('source_id')!='C11-136'
                or capture.get('sheet',{}).get('level')!=level
                or capture.get('sheet',{}).get('species')!=actor.spec['species']):
            raise ValueError('lowered boss capture requires its selected normal-form sheet')
        choices=capture.get('choices',{});sheet=capture['sheet']
        if (not isinstance(choices,dict) or set(choices)!={'strategy','moves','abilities'}
                or not isinstance(choices['moves'],list) or not isinstance(choices['abilities'],list)):
            raise ValueError('captured sheet needs its actual explicit GM choices')
        # build_pokemon always supplies innate Struggle; it is not a learned
        # Move choice and must not be retroactively inserted into GM evidence.
        expected_moves=list(choices['moves'])
        if 'struggle' not in expected_moves:expected_moves.append('struggle')
        if (choices.get('strategy')!=sheet.get('strategy') or expected_moves!=sheet.get('moves')
                or choices.get('abilities')!=sheet.get('abilities')):
            raise ValueError('captured sheet must retain its actual GM choices')
    elif capture is not None:raise ValueError('capture reallocation requires a lowered capture level')
    if not isinstance(runtime["flinch_rounds"], dict):
        raise ValueError("boss flinch receipt map required")
    for round_key, disposition in runtime["flinch_rounds"].items():
        _integer(int(round_key), "flinch round", 0)
        if disposition not in ("scheduled", "consumed"):
            raise ValueError("boss flinch round disposition changed")
    turn = row.get("boss_turn")
    if turn is not None:
        expected = {"round", "slot_id", "initiative", "key", "skip", "skip_reason"}
        if not isinstance(turn, dict) or set(turn) != expected:
            raise ValueError("boss turn receipt shape changed")
        _integer(turn["round"], "boss turn round", 0)
        _integer(turn["initiative"], "boss turn initiative")
        if turn["slot_id"] not in {slot["id"] for slot in row["action_slots"]}:
            raise ValueError("boss turn refers to an unknown action slot")
        if type(turn["skip"]) is not bool or turn["skip_reason"] not in (None, "stagger", "flinch"):
            raise ValueError("boss skipped-turn state changed")
    for effect in row.get("chosen_transition_effects", ()):
        _validate_effect(actor, effect)
    return True


def _slot(row, initiative_count):
    slots = row["action_slots"]
    if initiative_count is None:
        return slots[0]
    matches = [slot for slot in slots if slot["initiative"] == initiative_count]
    if len(matches) != 1:
        raise ValueError("boss turn requires one selected initiative slot")
    return matches[0]


def _next_slot(engine, row):
    slots = sorted(row["action_slots"], key=lambda value: value["initiative"], reverse=True)
    turn = row.get("boss_turn")
    if isinstance(turn, dict):
        index = next(i for i, slot in enumerate(slots) if slot["id"] == turn["slot_id"])
        return slots[(index + 1) % len(slots)]
    cursor = getattr(engine, "_initiative_cursor", None)
    if isinstance(cursor, dict) and type(cursor.get("count")) is int:
        return next((slot for slot in slots if slot["initiative"] < cursor["count"]), slots[0])
    return slots[0]


def start_round(engine, actor):
    row = state(actor)
    if row is None:
        return None
    key = "boss-round:" + str(engine.round_no)
    if key in row["round_trigger_receipts"]:
        return deepcopy(row["round_trigger_receipts"][key])
    receipt = {"kind": "boss_round_start", "round": engine.round_no,
               "source_id": "C11-129", "hp_loss": []}
    row["round_trigger_receipts"][key] = receipt
    # Weather HP loss shares the same once-per-round boss boundary.
    before = actor.hp
    import turn as TURN
    TURN.weather_turn_start(engine, actor, _boss_round=True)
    if actor.hp != before:
        receipt["hp_loss"].append({"source": "weather", "amount": before - actor.hp})
    import vortex_state as VORTEX
    import custom_condition_effects as CUSTOM
    VORTEX.turn_start(engine, actor, _boss_round=True)
    CUSTOM.turn_start(engine, actor, _boss_round=True)
    for condition in sorted(actor.conditions):
        for effect in actor.r.condition_effects(VARIANT_SOURCES.get(condition, condition)):
            if effect.get("type") != "tick_damage" or effect.get("when") != "end_of_turn":
                continue
            import persistent_conditions as PERSISTENT
            amount = PERSISTENT.loss(engine, actor, condition, effect["ticks"])
            receipt["hp_loss"].append({"source": condition, "amount": amount})
            # C11-122: percentage loss consumes only the current HP bar.
            engine.lose_hp(actor, amount, source=condition, loss_kind="percentage")
    validate(actor, row)
    return deepcopy(receipt)


def start_turn(engine, actor, initiative_count=None):
    row = state(actor)
    if row is None:
        return None
    slot = _slot(row, initiative_count)
    runtime = row["boss_runtime"]
    skip = False; reason = None
    if runtime["pending_skip_turns"]:
        runtime["pending_skip_turns"] -= 1
        skip = True; reason = "stagger"
        runtime["flinch_rounds"][str(engine.round_no)] = "consumed"
    binding = row["condition_bindings"].get("풀죽음")
    if (binding and binding.get("slot_id") == slot["id"]
            and runtime["flinch_rounds"].get(str(engine.round_no)) == "scheduled"):
        runtime["flinch_rounds"][str(engine.round_no)] = "consumed"
        skip = True; reason = "flinch"
    key = "round:" + str(engine.round_no) + ":boss-slot:" + slot["id"]
    old = row["round_trigger_receipts"].get(key)
    if isinstance(old, dict) and old.get("lifecycle") in ("open", "closed"):
        raise ValueError("boss action slot already consumed this round")
    row["own_turn_key"] = key
    row["boss_turn"] = {"round": engine.round_no, "slot_id": slot["id"],
                        "initiative": slot["initiative"], "key": key,
                        "skip": skip, "skip_reason": reason}
    row["round_trigger_receipts"].setdefault(key, {
        "kind": "boss_turn", "round": engine.round_no, "slot_id": slot["id"],
        "initiative": slot["initiative"], "skipped": skip, "reason": reason,
    })
    validate(actor, row)
    return deepcopy(row["boss_turn"])


def begin_action_lifecycle(engine, actor, initiative_count=None):
    """Admit exactly one ordinary lifecycle per selected boss slot."""
    row = state(actor)
    if row is None:
        return False
    start_turn(engine, actor, initiative_count)
    receipt = row["round_trigger_receipts"][row["boss_turn"]["key"]]
    if receipt.get("lifecycle") is not None:
        raise ValueError("boss action slot already has an action lifecycle")
    receipt["lifecycle"] = "open"
    return True


def close_action_lifecycle(engine, actor):
    row = state(actor)
    if row is None:
        return False
    turn = row.get("boss_turn")
    if not isinstance(turn, dict):
        raise ValueError("boss lifecycle close needs its actual action slot")
    receipt = row["round_trigger_receipts"].get(turn["key"])
    if not isinstance(receipt, dict) or receipt.get("lifecycle") != "open":
        raise ValueError("boss action lifecycle is not open")
    receipt["lifecycle"] = "closed"
    return True


def condition_applies_this_turn(actor, condition):
    if __import__('blessing_effects').ignored(actor,condition):return False
    row = state(actor)
    if row is None:
        return True
    binding = row["condition_bindings"].get(condition)
    if binding is None or binding.get("variant") in ("drowsy", "chilled"):
        return True
    turn = row.get("boss_turn")
    return isinstance(turn, dict) and binding.get("slot_id") == turn.get("slot_id")


def action_permission(actor):
    row = state(actor)
    return not (row and isinstance(row.get("boss_turn"), dict) and row["boss_turn"]["skip"])


def defer_end_tick(actor, condition, effect):
    return bool(state(actor) and effect.get("type") == "tick_damage"
                and effect.get("when") == "end_of_turn")


def end_turn(engine, actor):
    row = state(actor)
    if row is None or not isinstance(row.get("boss_turn"), dict):
        return None
    # Drowsy/Chilled preserve actions, halve Evasion, and replace the ordinary
    # cure-on-damage branch with an end-turn save and one next-roll penalty.
    for stored, binding in list(row["condition_bindings"].items()):
        if binding.get("variant") not in ("drowsy", "chilled") or stored not in actor.conditions:
            continue
        source = binding["source_condition"]
        save = next((effect for effect in actor.r.condition_effects(source)
                     if effect.get("type") == "save" and effect.get("timing") == "end_of_turn"), None)
        if save is None:
            raise ValueError("boss condition variant needs its ordinary save DC")
        import condition_recovery as RECOVERY
        result = RECOVERY.saving_check(engine, actor, source, save["dc"])
        if result["passed"] and save.get("on_success") == "cure":
            engine.cure_status(actor, stored)
        else:
            row["boss_runtime"]["damage_roll_penalty"] = -10
    binding = row["condition_bindings"].get("풀죽음")
    if binding and row["boss_turn"]["slot_id"] == binding.get("slot_id"):
        engine.cure_status(actor, "풀죽음")
    validate(actor, row)
    return deepcopy(row["boss_turn"])


def evasion(actor, value):
    row = state(actor)
    if row is None:
        return value
    if row["boss_runtime"]["vulnerable_until_damaged"]:
        return 0
    if any(binding.get("variant") in ("drowsy", "chilled")
           and condition in actor.conditions
           for condition, binding in row["condition_bindings"].items()):
        return NUMERIC.ratio(value,2)
    return value


def consume_damage_roll_modifier(actor):
    row = state(actor)
    if row is None:
        return 0
    value = row["boss_runtime"]["damage_roll_penalty"]
    row["boss_runtime"]["damage_roll_penalty"] = 0
    return value


def condition_variant(actor, condition):
    return VARIANTS.get(condition, (condition, None))[0] if state(actor) else condition


def condition_source(condition):
    return VARIANT_SOURCES.get(condition, condition)


def preflight_condition(engine, actor, condition, parameters=None):
    row = state(actor)
    if row is None:
        return True
    if condition == "사슬묶기":
        move_id = (parameters or {}).get("move_id")
        if not isinstance(move_id, str) or move_id not in actor.moves:
            raise ValueError("boss Disabled needs one possessed Move")
        existing = [value.get("disabled_move_id") for value in row["condition_bindings"].values()
                    if value.get("disabled_move_id") is not None]
        if existing and move_id not in existing:
            raise ValueError("boss can have only one Disabled Move")
    if condition == "풀죽음" and str(engine.round_no) in row["boss_runtime"]["flinch_rounds"]:
        return False
    return True


def condition_applied(engine, actor, condition, stored_condition, parameters=None, source=None):
    row = state(actor)
    if row is None:
        return
    if condition not in SLOT_CONDITIONS and condition not in VARIANTS and condition != "사슬묶기":
        return
    binding = {"source_id": "C11-131" if condition in VARIANTS else "C11-133" if condition in ("사슬묶기", "풀죽음") else "C11-130",
               "source_condition": condition, "slot_id": None,
               "variant": VARIANTS.get(condition, (None, "ordinary"))[1] or "ordinary",
               "disabled_move_id": None, "producer": source or "condition/" + condition}
    if condition in SLOT_CONDITIONS:
        binding["slot_id"] = _next_slot(engine, row)["id"]
    if condition == "사슬묶기":
        binding["disabled_move_id"] = (parameters or {})["move_id"]
    row["condition_bindings"][stored_condition] = binding
    if condition == "풀죽음":
        row["boss_runtime"]["flinch_rounds"][str(engine.round_no)] = "scheduled"
    validate(actor, row)


def condition_cured(actor, stored_condition):
    row = state(actor)
    if row is not None:
        row["condition_bindings"].pop(stored_condition, None)


def move_allowed(engine, actor, move_id, frequency_kind, cap):
    row = state(actor)
    if row is None:
        return None
    if frequency_kind in ("every_other_turn", "scene") and not isinstance(row.get("boss_turn"), dict):
        return False, "보스 빈도 기술은 실제 보스 행동 슬롯이 필요"
    return None


def record_move_use(engine, actor, move_id, frequency_kind):
    row = state(actor)
    if row is None:
        return
    turn = row.get("boss_turn")
    row["frequency_ledger"][move_id] = {
        "kind": frequency_kind,
        "turn_key": None if turn is None else turn["key"],
        "round": engine.round_no,
        "frequency_turn": actor.spec.get("frequency_state", {}).get("turn", 0),
        "used": actor.move_uses.get(move_id, 0),
    }
    validate(actor, row)


def _apply_effect(engine, actor, effect):
    kind = effect["kind"]
    if kind == "vulnerable_until_damaged":
        actor.spec["encounter_template"]["boss_runtime"]["vulnerable_until_damaged"] = True
    elif kind == "skip_next_turn":
        runtime = actor.spec["encounter_template"]["boss_runtime"]
        # Stagger's printed Flinch shares the ordinary once-per-round pool.
        if str(engine.round_no) not in runtime["flinch_rounds"]:
            runtime["flinch_rounds"][str(engine.round_no)] = "scheduled"
            runtime["pending_skip_turns"] = 1
    elif kind == "refresh_scene_move":
        import frequency as FREQUENCY
        FREQUENCY.restore_scene_use(engine, actor, effect["move_id"])
    elif kind == "cure_volatile":
        condition = effect["condition"]
        if condition in actor.conditions:
            if actor.r.condition_class(condition) not in (None, "volatile"):
                raise ValueError("selected stagger cure must target one volatile condition")
            engine.cure_status(actor, condition)
    elif kind == "raise_stage":
        engine.change_stage(actor, effect["stage"], 1)
    elif kind == "set_attack_stage_6":
        import combat_stage_sources as STAGE_SOURCES
        actor.spec["encounter_template"]["baseline_stages"]["atk"] = 6
        STAGE_SOURCES.assign_combat(actor, {"atk": 6})
    elif kind == "unlock_move":
        move_id = effect["move_id"]
        if move_id not in actor.moves:
            actor.moves.append(move_id)
    elif kind == "clear_debuffs":
        import combat_stage_sources as STAGE_SOURCES
        STAGE_SOURCES.assign_combat(actor, {
            stage: max(0, value) for stage, value in actor.stages.items()})
        import status_sets as STATUS
        STATUS.cure_group(engine, actor)
    return deepcopy(effect)


def after_hp_change(engine, actor, before, source, *, carry_over=True, attack=False):
    row = state(actor)
    if row is None:
        return None
    runtime = row["boss_runtime"]
    if attack and before > actor.hp and runtime["vulnerable_until_damaged"]:
        runtime["vulnerable_until_damaged"] = False
    if actor.hp > 0:
        validate(actor, row)
        return None
    bars = row["hp_bars"]; receipts = []
    while actor.hp <= 0 and bars["spent"] < bars["total"]:
        depleted = actor.hp; overflow = max(0, -depleted)
        bars["spent"] += 1
        remaining = bars["total"] - bars["spent"]
        receipt = {"source_id": "C11-126", "bar": bars["spent"],
                   "before_hp": before, "depleted_hp": depleted,
                   "carried_over": overflow if carry_over and remaining else 0,
                   "discarded_overflow": overflow if not carry_over else 0,
                   "remaining_bars": remaining, "source": source, "effects": []}
        row["bar_transition_receipts"].append(receipt); receipts.append(receipt)
        if (not runtime["half_bar_injury_awarded"]
                and bars["spent"] * 2 >= bars["total"]):
            import precise_actions as PRECISE
            retained=PRECISE.gain_injury(engine,actor,1,'C11-126')
            runtime["half_bar_injury_awarded"] = True
            receipt["half_bar_injury"] = bool(retained)
        if remaining:
            actor.hp = actor.max_hp - overflow if carry_over else actor.max_hp
            for effect in row["chosen_transition_effects"]:
                if effect["when"] == "bar_lost":
                    receipt["effects"].append(_apply_effect(engine, actor, effect))
            if remaining == 1:
                for effect in row["chosen_transition_effects"]:
                    if effect["when"] == "final_bar":
                        receipt["effects"].append(_apply_effect(engine, actor, effect))
        before = actor.max_hp
    validate(actor, row)
    return deepcopy(receipts)


def _rebase_capture_milestones(actor, level):
    """Keep a lowered captured form internally valid without inventing choices.

    A freshly built Pokemon records its creation ability offer at its observed
    creation level.  C11-136 can replace that level at capture, so the same
    unspent offer belongs to the captured form's selected level.  Later
    milestone offers above that level are no longer attained; preserve them in
    the capture receipt instead of leaving impossible live entitlements.
    """
    records = actor.spec.get("growth_milestone_choices")
    if not isinstance(records, dict):
        return []
    removed = []
    for identity in list(records):
        row = records[identity]
        offered = row.get("offered", {}) if isinstance(row, dict) else {}
        stage = offered.get("stage", {}) if isinstance(offered, dict) else {}
        if identity == "ability:creation" and stage.get("kind") == "creation":
            stage["level"] = level
        elif stage.get("kind") == "level" and isinstance(stage.get("level"), int) and stage["level"] > level:
            removed.append({"identity": identity, "record": deepcopy(row)})
            del records[identity]
    return removed


def prepare_capture_form(actor, level, choices):
    """Lowering a catch requires the GM's actual normal-sheet choices first."""
    if level is None or level == actor.level:
        if choices is not None:
            raise ValueError('capture choices require an explicitly changed capture level')
        return None
    if (not isinstance(choices,dict) or set(choices) != {'strategy','moves','abilities'}
            or not isinstance(choices['moves'],list) or not isinstance(choices['abilities'],list)):
        raise ValueError('lowered boss capture requires explicit GM capture_choices: strategy, moves, abilities')
    import builder
    if choices['strategy'] not in builder.STRATEGY:
        raise ValueError('captured normal form needs an actual allocation strategy')
    if len(choices['abilities']) > 1 + (level >= 20) + (level >= 40):
        raise ValueError('captured normal form exceeds its level ability milestones')
    # The complete selected native sheet is retained as evidence; it never
    # inherits the encounter's high-level allocation or selected abilities.
    form = builder.build_pokemon(actor.r,actor.spec['species'],level,
        nature=actor.spec.get('nature'),strategy=choices['strategy'],
        moves=choices['moves'],abilities=choices['abilities'])
    import growth_milestones as MILESTONES
    chosen=[]
    for index, ability in enumerate(choices['abilities']):
        milestone=('creation',20,40)[index]
        options=MILESTONES.ability_options(actor.r,dict(form,abilities=chosen),milestone)
        if ability not in options:
            raise ValueError('captured normal-form ability is not an eligible milestone choice')
        chosen.append(ability)
    import growth_stats as GROWTH
    import pokemon_stat_edges as EDGES
    import arithmetic_policy as M
    inherited=deepcopy(actor.spec)
    inherited.update(level=level,moves=deepcopy(form['moves']),abilities=chosen)
    plan=builder.allocation_plan(builder.species_lookup(actor.r,inherited['species'])['base_stats'],
        M.floor(builder.calc(actor.r.mech('pokemon/stat-build')['stat_points'],{'level':level})),
        choices['strategy'],inherited.get('nature'),actor.r,
        base_sources=EDGES.base_sources(actor.r,inherited),
        fixed_point_sources=EDGES.point_sources(actor.r,inherited),
        relation_exempt=EDGES.exemptions(actor.r,inherited))
    form['initial_allocation']=plan
    form['stats']={stat:value+inherited.get('vitamin_bonus',{}).get(stat,0) for stat,value in plan['stats'].items()}
    form['vitamin_bonus']=deepcopy(inherited.get('vitamin_bonus',{}))
    form['learned_poke_edges']=deepcopy(inherited.get('learned_poke_edges',[]))
    for key in ('underdog','baby_template','researcher_training'):
        if key in inherited:form[key]=deepcopy(inherited[key])
    # Validate against the individual's actual permanent-source declarations.
    inherited.update(stats=deepcopy(form['stats']),initial_allocation=deepcopy(plan),
                     growth_investment_events=[],allocation_migrations=[])
    inherited.pop('form_growth_allocations',None)
    GROWTH.project(actor.r,inherited)
    builder.record_allocation(actor.r,inherited,'boss_capture_reallocation')
    form['stat_allocation']=deepcopy(inherited['stat_allocation'])
    form['stat_history']=deepcopy(inherited['stat_history'][-1:])
    return {'source_id':'C11-136','choices':deepcopy(choices),'sheet':form}


def after_capture(engine, actor):
    row = state(actor)
    if row is None:
        return None
    if row["hp_bars"]["total"] - row["hp_bars"]["spent"] > 1:
        raise ValueError("boss capture transition requires the visible final HP bar")
    baseline = deepcopy(row["normal_form_baseline"])
    runtime = row["boss_runtime"]
    previous_level = actor.level
    actor.level = runtime["capture_level"] or baseline["level"]
    selected = row.get('capture_form')
    if actor.level != baseline['level']:
        if selected is None:
            raise ValueError('lowered boss capture requires an explicit GM normal-form reallocation')
        baseline = deepcopy(selected['sheet'])
        row['capture_reallocation_previous']={field:deepcopy(actor.spec[field]) for field in (
            'initial_allocation','stat_allocation','stat_history','growth_investment_events',
            'allocation_migrations','form_growth_allocations','growth_milestone_choices',
            'move_natural_history') if field in actor.spec}
        # Preserve the individual's earned history in the retired template;
        # live allocation and learning projections belong to the selected form.
        for field in ('initial_allocation','stat_allocation','stat_history','growth_investment_events',
                      'allocation_migrations','form_growth_allocations','growth_milestone_choices',
                      'move_natural_history'):
            actor.spec.pop(field,None)
            if field in baseline:actor.spec[field]=deepcopy(baseline[field])
        actor.spec['strategy']=baseline['strategy']
    actor.stats = deepcopy(baseline["stats"]); actor.spec["stats"] = deepcopy(baseline["stats"])
    actor.moves = deepcopy(baseline["moves"] or []); actor.spec["moves"] = deepcopy(actor.moves)
    actor.abilities = deepcopy(baseline["abilities"] or []); actor.spec["abilities"] = deepcopy(actor.abilities)
    actor.types = deepcopy(baseline["types"] or []); actor.spec["types"] = deepcopy(actor.types)
    removed_milestones = _rebase_capture_milestones(actor, actor.level)
    actor.spec.setdefault("boss_capture_progression_rebases", []).append({
        "source_id": "C11-136", "before_level": previous_level,
        "after_level": actor.level, "removed_unattained_milestones": removed_milestones})
    actor.hp = min(actor.hp, actor.max_hp)
    retired = deepcopy(row); retired["active"] = False
    actor.spec.setdefault("retired_encounter_templates", []).append({
        "source_id": "C11-137", "reason": "captured_normal_form", "state": retired})
    actor.spec.pop("encounter_template", None)
    actor._state_revision += 1
    engine.log(f"    {actor.name}: 포획 후 보스 템플릿 제거, 일반 폼 복원", "C11-136/C11-137")
    return {"level": actor.level, "template_active": False}
