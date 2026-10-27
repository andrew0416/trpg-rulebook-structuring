"""Selected printed and Homebrew Fashion contracts through their native consumers.

The CSV rows combine two independent lifetimes: one contest reroll on a
Pokemon, and one scene activation in battle when the crafted item is worn by
its maker or a Pokemon currently owned by that maker.  Registration only
establishes the physical source.  Each native consumer below owns its actual
trigger and expiry.
Printed Core items grant only the holder's battle branch.  Their accessory,
held and sourced Fashionista projections use those same native consumers.
"""
from copy import deepcopy
import hashlib
import json
import os

POLICY_FILE = "fashion-item-contract-policy.json"
STATE = "fashion_item_state"
HOMEBREW_ITEM_IDS = frozenset({
    "item/귀여운-패션-1",
    "item/아름다운-패션-1",
    "item/근사한-패션-1",
    "item/강인한-패션-1",
    "item/슬기로운-패션-1",
})
CORE_ITEM_IDS = frozenset({
    "item/귀여운-패션", "item/우아한-패션", "item/기막힌-패션",
    "item/거친-패션", "item/번지르르한-패션",
})
ITEM_IDS = HOMEBREW_ITEM_IDS | CORE_ITEM_IDS


BOOK_ITEMS = {
    'item/귀여운-패션': ('cute', '매력'),
    'item/우아한-패션': ('beauty', '직감'),
    'item/기막힌-패션': ('cool', '명령'),
    'item/거친-패션': ('tough', '협박'),
    'item/번지르르한-패션': ('smart', '교활'),
}
FOCUS_ITEMS = frozenset({'item/기합의머리띠', 'item/기합의띠'})
CONTEST_FASHION = 'item/콘테스트-옷'
CONTEST_STATS = frozenset({'귀여움', '아름다움', '근사함', '강인함', '슬기로움'})
ITEM_SOURCE_SHA256 = 'f78d72f768c4e7bdfcbc406db33be6201ff6d072787a9179fbb1653c43fe98b8'


def _equipment_definition(rules, item_id):
    if item_id not in FOCUS_ITEMS | {CONTEST_FASHION}:
        return None
    from source_context import verified_source
    verified_source(rules, {'file':'input/db/item-data.csv', 'sha256':ITEM_SOURCE_SHA256}, label='Fashion equipment')
    if rules._selected_rule(item_id) != item_id:
        raise ValueError('selected Fashion equipment required')
    return {'item_id':item_id, 'contract':'equipment'}


def book_definition(rules, item_id):
    if item_id not in BOOK_ITEMS:
        return None
    import fashionista as FA
    source = os.path.join(rules.root, FA._data['source_file'])
    with open(source, 'rb') as handle:
        if hashlib.sha256(handle.read()).hexdigest() != FA._data['source_sha256']:
            raise ValueError('Basic Fashion Book source changed')
    if rules._selected_rule(item_id) != item_id:
        raise ValueError('selected Book Basic Fashion source required')
    kind, skill = BOOK_ITEMS[item_id]
    return dict(item_id=item_id, kind=kind, fashionista_skill=skill, contract='book',
                clause_id='input/ch04-trainer-classes.md:2043', range_m=5)




def _projection(engine, actor, item_id, projection):
    import fashionista as FA
    import world_entities as WORLD
    FA.validate_projection(projection)
    maker = WORLD.actor_index(engine).get(projection['owner_id'])
    if maker is None:
        raise ValueError('Fashion projection owner must be an actual acquired Trainer')
    FA.require(engine, maker, projection['rule_id'])
    if projection['rule_id'] == FA.MAKEOVER:
        expected = FA.MAKEOVER_PREFIX + maker.entity_id + ':' + actor.entity_id
        if (projection['source_id'] != expected or projection['registration_key'] != 'makeover:' + maker.entity_id
                or not any(row['output']['item_id'] == item_id and FA.qualifies(engine, maker, row['id'])
                           for row in FA.RECIPES)):
            raise ValueError('Fashion Makeover needs its actual craftable recipe and projection source')
    else:
        return FA.dress_item_origin(engine, actor, item_id, projection,
                                    preparing=FA.dress_record(actor) is None)
    return None


def _path(rules):
    canonical = os.path.join(rules.root, "data", POLICY_FILE)
    staged = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", POLICY_FILE))
    return canonical if os.path.exists(canonical) else staged


def policy(rules):
    with open(_path(rules), encoding="utf-8") as handle:
        value = json.load(handle)
    rows = value.get("rows")
    if value.get("schema_version") != 1 or value.get("contract") != "crafted fashion item source contract":
        raise ValueError("fashion item policy schema changed")
    if not isinstance(rows, dict) or len(rows) != 5:
        raise ValueError("fashion policy must contain the exact five reviewed rows")
    source = os.path.join(rules.root, "input", "db", "inventory.csv")
    with open(source, "rb") as handle:
        source_sha = hashlib.sha256(handle.read()).hexdigest()
    if source_sha != value.get("source_file_sha256"):
        raise ValueError("fashion inventory source changed")
    with open(os.path.join(rules.root, "data", "verification", "category2-item-table-status.json"), encoding="utf-8") as handle:
        status = json.load(handle)
    indexed = {row["clause_id"]: row for row in status.get("new_clauses", ())}
    kinds = {"cute", "beauty", "cool", "tough", "smart"}
    seen = set()
    for item_id, row in rows.items():
        if item_id != row.get("item_id") or row.get("kind") not in kinds:
            raise ValueError("fashion item identity or kind changed")
        if row.get("contest_stat") not in {"귀여움", "아름다움", "근사함", "강인함", "슬기로움"}:
            raise ValueError("fashion contest stat changed")
        clause = row.get("clause_id")
        if not isinstance(clause, str) or clause in seen:
            raise ValueError("fashion clause identity changed")
        seen.add(clause)
        registered = indexed.get(clause)
        if registered is None or len(registered.get("source", ())) != 1:
            raise ValueError("fashion source row is missing")
        src = registered["source"][0]
        expected = (row.get("source_file"), row.get("source_row"), row.get("source_columns"), row.get("source_row_sha256"))
        actual = (src.get("file"), src.get("row"), src.get("columns"), src.get("raw_cells_sha256"))
        if expected != actual:
            raise ValueError("fashion source provenance changed: " + clause)
        effects, header = rules.item_effects(item_id)
        if header.get("id") != item_id or rules._selected_rule(item_id) != item_id or len(effects) != 2:
            raise ValueError("fashion selected item or reviewed effects changed: " + item_id)
    return value


def _core_rows(rules):
    with open(_path(rules), encoding="utf-8") as handle:
        value = json.load(handle)
    source = value["core_source"]
    with open(os.path.join(rules.root, source["file"]), "rb") as handle:
        if hashlib.sha256(handle.read()).hexdigest() != source["sha256"]:
            raise ValueError("printed Fashion source changed")
    rows = value["core_rows"]
    if (set(rows) != CORE_ITEM_IDS or any(row.get("item_id") != key for key, row in rows.items())
            or {row.get("kind") for row in rows.values()} != {"cute", "beauty", "cool", "tough", "smart"}):
        raise ValueError("printed Fashion requires its exact five selected items")
    return rows


def core_header(rules, item_id, header):
    if item_id not in CORE_ITEM_IDS:
        return header
    row = _core_rows(rules)[item_id]
    return dict(header, category="패션 도구", slot="장신구", use="held", price=None, desc=row["desc"])


def definition(rules, item_id):
    if item_id not in ITEM_IDS:
        return None
    if item_id in CORE_ITEM_IDS:
        row = deepcopy(_core_rows(rules)[item_id])
        effects, header = rules.item_effects(item_id)
        if (rules._selected_rule(item_id) != item_id or header.get("id") != item_id
                or len(effects) != 1 or effects[0].get("type") != row["effect_type"]
                or effects[0].get("if")):
            raise ValueError("printed Fashion selected effect changed: " + item_id)
        return dict(row, **book_definition(rules, item_id))
    return deepcopy(policy(rules)["rows"].get(item_id))


def prepare_register(engine, actor, item_id, source_instance_id=None, *, projection=None):
    equipment = _equipment_definition(engine.r, item_id)
    if equipment is not None:
        obj = _projection(engine, actor, item_id, projection) if projection is not None else getattr(engine, '_physical_objects', {}).get(source_instance_id)
        if item_id == CONTEST_FASHION:
            stat = projection.get('contest_stat') if projection and projection['rule_id'] == __import__('fashionista').MAKEOVER else __import__('fashionista').contest_assignment(engine, obj)
            if stat not in CONTEST_STATS:
                raise ValueError('Contest Fashion requires its actual assigned contest stat')
            equipment['contest_stat'] = stat
        return equipment
    if item_id not in ITEM_IDS:
        return None
    row = definition(engine.r, item_id)
    if row is None:
        return None
    obj = getattr(engine, '_physical_objects', {}).get(source_instance_id)
    projected_obj = _projection(engine, actor, item_id, projection) if projection is not None else None
    if item_id in BOOK_ITEMS:
        # The current selected catalog separates Core items from the five HB IDs.
        return row
    if projection is not None:
        # Homebrew projections retain the actual stored product's maker condition.
        if projected_obj is None:
            raise ValueError('homebrew Fashion projection requires an actual crafted stored item')
        obj = projected_obj
    elif not isinstance(source_instance_id, str) or not source_instance_id:
        raise ValueError("fashion item requires its actual crafted physical instance")
    origin = obj.get("crafting_origin") if isinstance(obj, dict) else None
    if (not isinstance(origin, dict) or not isinstance(origin.get("maker_id"), str)
            or not origin.get("maker_id")):
        raise ValueError("fashion item requires actual maker provenance")
    import world_entities as WORLD
    maker = WORLD.actor_index(engine).get(origin["maker_id"])
    if maker is None or maker.kind != "trainer":
        raise ValueError("fashion item maker must resolve to an actual Trainer")
    return dict(row, contract='inventory')


def consumes_effect(plan, effect):
    return bool(plan)


def install(engine, actor, source_id, plan):
    if plan:
        import state_grants as GRANTS
        GRANTS.state(actor)['sources'][source_id]['fashion_contract'] = deepcopy(plan)
    return [], 0


def _active(engine, actor, kind=None):
    registrations = tuple(getattr(actor, "_item_reg", {}).values())
    if not any(registration.get("item_id") in ITEM_IDS for registration in registrations):
        return []
    sources = actor.spec.get("state_grants", {}).get("sources", {})
    found = []
    for registration in registrations:
        source = sources.get(registration.get('state_source'))
        if source is None:
            continue
        row = source.get('fashion_contract')
        if row is None and registration.get('item_id') in HOMEBREW_ITEM_IDS:
            row = definition(engine.r, registration['item_id'])  # historical CSV registrations
        if row is None and registration.get('item_id') in CORE_ITEM_IDS:
            row = prepare_register(engine, actor, registration['item_id'], registration.get('instance_id'), projection=registration.get('projection'))
        if row is None or row.get('contract') == 'equipment' or (kind is not None and row["kind"] != kind):
            continue
        uid = registration.get("instance_id")
        obj = getattr(engine, "_physical_objects", {}).get(uid)
        if registration.get('projection') is not None:
            obj = _projection(engine, actor, row['item_id'], registration['projection'])
        if row.get('contract') == 'book':
            legacy = uid is None and registration.get('projection') is None
            if legacy and (source.get('identity_evidence') != 'legacy_actor_rule' or source.get('rule_id') != row['item_id']):
                raise ValueError('legacy Core Fashion needs its actual selected item source')
            if not legacy and registration.get('projection') is None and (not isinstance(obj, dict)
                    or obj.get('kind') != 'item_instance' or obj.get('item_rule_id') != row['item_id']
                    or obj.get('equipped_by') != actor.entity_id):
                raise ValueError('fashion registration and physical instance disagree')
            expected = prepare_register(engine, actor, row['item_id'], uid, projection=registration.get('projection'))
            if expected != row:
                raise ValueError('Book Fashion source contract changed')
            found.append((row, registration, source))
            continue
        if (not isinstance(obj, dict) or obj.get("kind") != "item_instance"
                or obj.get("item_rule_id") != row["item_id"]
                or (registration.get('projection') is None and obj.get('equipped_by') != actor.entity_id)):
            raise ValueError("fashion registration and physical instance disagree")
        origin = obj.get("crafting_origin")
        if not isinstance(origin, dict) or not isinstance(origin.get("maker_id"), str):
            raise ValueError("fashion physical instance lost its maker")
        found.append((row, registration, obj))
    return found


def _maker_eligible(engine, actor, obj):
    maker_id = obj["crafting_origin"]["maker_id"]
    import world_entities as WORLD
    maker = WORLD.actor_index(engine).get(maker_id)
    if maker is None or maker.kind != "trainer":
        raise ValueError("fashion maker no longer resolves to an actual Trainer")
    return actor.entity_id == maker_id or (actor.kind == "pokemon" and actor.spec.get("trainer_id") == maker_id)


def registration_header(header, plan):
    return dict(header, trainer_slot='장신구') if plan and plan.get('contract') == 'book' else header


def _identity(registration):
    return registration.get('instance_id') or (registration.get('projection') or {}).get('wardrobe_instance_id') or registration['state_source']


def _scene(engine, actor):
    import frequency as FREQ
    return FREQ.state(actor)["scene"]


def _choose_instance(candidates, instance_id, purpose):
    if instance_id is not None:
        candidates = [entry for entry in candidates if _identity(entry[1]) == instance_id]
        if not candidates:
            raise ValueError("selected Fashion physical instance is unavailable for " + purpose)
    if not candidates:
        raise ValueError("selected equipped Fashion source is unavailable or its maker condition is not met")
    if len(candidates) != 1:
        raise ValueError("multiple matching Fashion instances require explicit instance_id")
    return candidates[0]


def _available(engine, actor, kind, instance_id=None, *, item_id=None):
    candidates = [entry for entry in _active(engine, actor, kind)
                  if (item_id is None or entry[0]["item_id"] == item_id)
                  and (entry[0].get('contract') == 'book' or _maker_eligible(engine, actor, entry[2]))]
    row, registration, obj = _choose_instance(candidates, instance_id, "battle activation")
    used = obj.get(STATE, {}).get("scene_activation")
    if row.get('contract') == 'book' and not __import__('frequency').activation_allowed(
            actor, 'fashion:' + row['item_id'], {'kind':'scene', 'uses':1}, engine=engine, action_actor=actor):
        raise ValueError('this Fashion item was already activated this scene')
    if isinstance(used, dict) and used.get("scene", -1) >= _scene(engine, actor):
        raise ValueError("this physical Fashion item was already activated in this scene")
    return row, registration, obj


def _can_free_action(engine, actor):
    import action_lifecycle as ACTION
    import turn as TURN
    engine.r.mech("combat/action-economy")
    return TURN.can_act(engine, actor) and ACTION.status_permission(engine, actor, "free")


def _free_action(engine, actor, source):
    import action_lifecycle as ACTION
    if not _can_free_action(engine, actor):
        raise ValueError("Fashion Free Action is unavailable")
    ACTION.record_action(engine, actor, "free")
    engine.log("  " + actor.name + ": 패션 자유 행동 활성화", source)


def _consume_scene(engine, actor, row, registration, obj, *, target_id=None, trigger):
    import frequency as FREQ
    key = "fashion:" + (row['item_id'] if row.get('contract') == 'book' else _identity(registration))
    declaration = {"kind": "scene", "uses": 1}
    if not FREQ.activation_allowed(actor, key, declaration, engine=engine, action_actor=actor):
        raise ValueError("Fashion scene activation is exhausted")
    _free_action(engine, actor, row["item_id"])
    FREQ.consume_activation(actor, key, declaration, engine=engine, action_actor=actor)
    state = obj.setdefault(STATE, {})
    receipt = {"item_id": row["item_id"], "clause_id": row["clause_id"],
               "instance_id": _identity(registration), "wearer_id": actor.entity_id,
               "maker_id": obj.get('crafting_origin', {}).get('maker_id'), "scene": _scene(engine, actor),
               "round": engine.round_no, "at": engine.elapsed_seconds, "trigger": trigger}
    if target_id is not None:
        receipt["target_id"] = target_id
    state["scene_activation"] = receipt
    state.setdefault("history", []).append(deepcopy(receipt))
    return receipt


def _round_record(engine, target, row, registration, field, value, receipt):
    import combat_timing as TIMING
    if not engine.encounter_active:
        raise ValueError("one-round Fashion effect requires an active encounter")
    count = TIMING.current(engine)
    record = {"source": row["item_id"], "effect_contract": True, "fashion_contract": True,
              "fashion_clause": row["clause_id"], "fashion_instance": _identity(registration),
              field: value, "count_deadline": (engine.round_no + 1, count),
              "encounter_end": True, "activation_receipt": deepcopy(receipt)}
    TIMING.install(engine, target, record)
    return record


def activate(engine, actor, item_id, *, target=None, instance_id=None):
    row = definition(engine.r, item_id)
    if row is None:
        raise ValueError("selected item is not a printed or Homebrew Fashion contract")
    if row["kind"] in {"beauty", "smart"}:
        raise ValueError("this Fashion activates only at its actual reaction trigger")
    row, registration, obj = _available(engine, actor, row["kind"], instance_id, item_id=item_id)
    if not engine.encounter_active:
        raise ValueError("battle Fashion requires an active encounter")
    if row["kind"] in {"cute", "tough"}:
        import combat_timing as TIMING
        TIMING.current(engine)
    if row["kind"] == "tough":
        import world_entities as WORLD
        if target is None:
            raise ValueError("Tough Fashion requires an actual enemy target")
        WORLD.require_actors(engine, actor, target)
        if getattr(actor, "side", None) == getattr(target, "side", None):
            raise ValueError("Tough Fashion target must be an enemy")
        distance = WORLD.distance_known(actor, target)
        if distance is None or distance > row["range_m"]:
            raise ValueError("Tough Fashion target must be within 5m on observed geometry")
        receipt = _consume_scene(engine, actor, row, registration, obj, target_id=target.entity_id,
                                 trigger="selected enemy within 5m")
        _round_record(engine, target, row, registration, "fashion_all_roll_modifier", -2, receipt)
    else:
        receipt = _consume_scene(engine, actor, row, registration, obj,
                                 trigger="voluntary battle activation")
        if row["kind"] == "cute":
            _round_record(engine, actor, row, registration, "evasion_modifier", 2, receipt)
        elif row["kind"] == "cool":
            actor.spec["fashion_next_save"] = {"source": row["item_id"],
                                                "clause_id": row["clause_id"],
                                                "instance_id": _identity(registration),
                                                "value": 4, "activation_receipt": deepcopy(receipt)}
    return deepcopy(receipt)


def arm_reaction(engine, actor, item_id, *, instance_id=None):
    """Explicitly accept the next eligible optional Fashion reaction.

    Arming selects an exact physical source but spends no action and no scene
    use.  The native trigger consumes both only after it actually occurs.
    """
    row = definition(engine.r, item_id)
    if row is None or row["kind"] not in {"beauty", "smart"}:
        raise ValueError("only optional reaction Fashion can be armed")
    if not engine.encounter_active:
        raise ValueError("Fashion reaction arming requires an active encounter")
    row, registration, _ = _available(engine, actor, row["kind"], instance_id, item_id=item_id)
    armed = actor.spec.setdefault("fashion_reaction_armed", {})
    receipt = {"item_id": row["item_id"], "clause_id": row["clause_id"],
               "kind": row["kind"], "instance_id": _identity(registration),
               "scene": _scene(engine, actor), "armed_at": engine.elapsed_seconds}
    armed[row["kind"]] = receipt
    return deepcopy(receipt)


def _armed_instance(actor, kind):
    armed = actor.spec.get("fashion_reaction_armed", {})
    receipt = armed.get(kind) if isinstance(armed, dict) else None
    if receipt is None:
        return None
    expected = {"item_id", "clause_id", "kind", "instance_id", "scene", "armed_at"}
    if not isinstance(receipt, dict) or set(receipt) != expected or receipt.get("kind") != kind:
        raise ValueError("Fashion reaction arming receipt changed")
    return receipt["instance_id"]


def _consume_arm(actor, kind, instance_id):
    armed = actor.spec.get("fashion_reaction_armed")
    if not isinstance(armed, dict) or armed.get(kind, {}).get("instance_id") != instance_id:
        raise ValueError("Fashion reaction source changed before its trigger")
    del armed[kind]
    if not armed:
        actor.spec.pop("fashion_reaction_armed", None)


def all_roll_modifier(actor):
    import combat_timing as TIMING
    return TIMING.all_roll_modifier(actor)


def consume_save_bonus(engine, actor):
    row = actor.spec.get("fashion_next_save")
    if row is None:
        return 0
    if (not isinstance(row, dict) or set(row) != {"source", "clause_id", "instance_id", "value", "activation_receipt"}
            or row.get("value") != 4):
        raise ValueError("Fashion next-save receipt changed")
    source = definition(engine.r, row["source"])
    if source is None or source["kind"] != "cool" or source["clause_id"] != row["clause_id"]:
        raise ValueError("Fashion next-save source changed")
    actor.spec.pop("fashion_next_save")
    actor.spec.setdefault("fashion_save_history", []).append({**deepcopy(row), "consumed_at": engine.elapsed_seconds})
    engine.log("    " + actor.name + ": 근사한 패션 내성 +4 소비", row["source"])
    return 4


def _admitted_reaction(engine, actor, kind):
    """Acceptance selects a source; current Free Action permission still applies."""
    instance_id = _armed_instance(actor, kind)
    if instance_id is None:
        return None
    try:
        candidate = _available(engine, actor, kind, instance_id)
    except ValueError as exc:
        if "already activated" in str(exc):
            return None
        if not _active(engine, actor, kind):
            return None
        raise
    return candidate if _can_free_action(engine, actor) else None


def blocks_stage_loss(engine, target, source_actor, context, *, source_side=None):
    if ((source_actor is target or getattr(source_actor, "side", None) == getattr(target, "side", None))
            if source_side is None else source_side == target.side):
        return False
    candidate = _admitted_reaction(engine, target, "beauty")
    if candidate is None:
        return False
    row, registration, obj = candidate
    _consume_scene(engine, target, row, registration, obj, target_id=source_actor.entity_id,
                   trigger="enemy combat-stage loss")
    _consume_arm(target, "beauty", _identity(registration))
    return True


def prevents_opportunity(engine, mover, why, enemies):
    if not enemies:
        return False
    candidate = _admitted_reaction(engine, mover, "smart")
    if candidate is None:
        return False
    row, registration, obj = candidate
    _consume_scene(engine, mover, row, registration, obj,
                   trigger="would provoke opportunity attack: " + str(why))
    _consume_arm(mover, "smart", _identity(registration))
    engine.log("  " + mover.name + ": 슬기로운 패션으로 기회 공격 유발 1회 방지", row["item_id"])
    return True


def contest_plan(engine, pokemon, stat, used, *, instance_id=None):
    if pokemon.kind != "pokemon":
        raise ValueError("Fashion contest reroll is Pokemon-only")
    matches = [(row, registration) for row, registration, _ in _active(engine, pokemon)
               if row.get("contest_stat") == stat]
    matches.extend((row, registration) for row, registration, _ in _equipment(engine, pokemon, {CONTEST_FASHION})
                   if row['contest_stat'] == stat)
    if not matches:
        raise ValueError("matching equipped Fashion contest stat required")
    selected = _choose_instance([(row, registration, None) for row, registration in matches],
                                instance_id, "contest reroll")
    row, registration = selected[:2]
    key = (pokemon.entity_id, _identity(registration), row["item_id"])
    if key in used:
        raise ValueError("this Fashion item was already used once in this contest")
    return key, row


def _equipment(engine, actor, identities):
    sources = actor.spec.get('state_grants', {}).get('sources', {})
    for registration in getattr(actor, '_item_reg', {}).values():
        item_id = registration.get('item_id')
        if item_id not in identities:
            continue
        source = sources.get(registration.get('state_source'), {})
        row = source.get('fashion_contract')
        if not row:
            continue
        expected = prepare_register(engine, actor, item_id, registration.get('instance_id'), projection=registration.get('projection'))
        if row != expected:
            raise ValueError('Fashion equipment source contract changed')
        yield row, registration, source


def focus_interested(engine, actor):
    def equipped(subject):
        return any(row.get('item_id') in FOCUS_ITEMS for row in getattr(subject, '_item_reg', {}).values())
    if equipped(actor):
        return True
    # The native faint owner also crosses its actual As One partner's HP.
    import csv_item_form_contracts as FORMS
    relation = FORMS._relation(actor, 'as_one')
    marker = actor.spec.get('off_field_reason', {})
    partner_id = relation['mount_id'] if relation else marker.get('owner_id') if marker.get('kind') == 'as_one_mount' else None
    if partner_id is None:
        return False
    import world_entities as WORLD
    return equipped(WORLD.actor_index(engine).get(partner_id))


def replace_hp(engine, actor, before, proposed, *, move_damage=False):
    """Replace final HP only; the native producer still owns damage and injuries."""
    if before <= 0 or proposed > 0 or actor.dead or '기절' in actor.conditions:
        return proposed
    import frequency as FREQ
    for row, registration, source in _equipment(engine, actor, FOCUS_ITEMS):
        item_id = row['item_id']
        if item_id == 'item/기합의띠':
            # A selected, live native Move application, not a caller's damage label.
            native = any(frame['target'] is actor for frame in getattr(engine, '_attack_history_scopes', {}).values())
            if not move_damage or not native or before < actor.base_max_hp:
                continue
        # Printed once/Scene is this user's item rule, not a fresh item copy.
        key = 'focus:' + item_id
        quota = {'kind':'scene', 'uses':1}
        if not FREQ.activation_allowed(actor, key, quota, engine=engine):
            continue
        face = engine.d20() if item_id == 'item/기합의머리띠' else None
        source.setdefault('focus_attempts', []).append({'before':before, 'proposed':proposed,
            'face':face, 'scene':_scene(engine, actor), 'at':engine.elapsed_seconds,
            'instance_id':registration.get('instance_id'), 'state_source':registration['state_source'], 'item_id':item_id})
        if face is not None and face < 16:
            engine.log('  '+actor.name+': 기합의머리띠 '+str(face)+' < 16', item_id)
            continue
        FREQ.consume_activation(actor, key, quota, engine=engine)
        engine.log('  '+actor.name+': '+item_id+' — 기절 대신 HP 1 (장면 1회)', item_id)
        return 1
    return proposed

