"""Source-selected actor template invariants; creation legality stays category6."""
SOULLESS = "capability/영혼없음"


def has_soulless(spec):
    return any(value in ("영혼없음", SOULLESS, "Soulless") for value in spec.get("capabilities", ()))


def soulless(actor):
    if not has_soulless(actor.spec):
        return False
    if actor.r._selected_rule(SOULLESS) != SOULLESS:
        raise ValueError("selected Soulless variant needs its own state contract")
    return True


def validate_soulless_default(rules, spec):
    """The original says default ability, not an unconditional live override."""
    if not has_soulless(spec):
        return True
    if rules._selected_rule(SOULLESS) != SOULLESS:
        raise ValueError("selected Soulless variant needs its own state contract")
    import ability_transitions as ABILITIES
    values=spec.get("abilities", [])
    if not isinstance(values,list) or not any(ABILITIES.ability_id(rules,name)=="ability/불가사의부적" for name in values):
        raise ValueError("Soulless default abilities must retain Wonder Guard")
    return True


def validate(actor):
    if soulless(actor):
        validate_soulless_default(actor.r, actor.spec)
        if actor.temp_hp != 0 or actor.injuries != 0 or actor.dead:
            raise ValueError("Soulless state cannot carry temporary HP, injuries or death")
        if actor.hp > 1 or actor.base_max_hp != 1 or actor.max_hp != 1:
            raise ValueError("Soulless maximum HP must be one")
    if SOULLESS_REST_CHOICE in actor.spec or SOULLESS_REST_TASKS in actor.spec:
        _soulless_rest_definition(actor);_soulless_rest_tasks(actor)
    validate_template(actor)
    return True


# This is a Soulless timing leaf; common rest clocks and revival remain owners.
SOULLESS_REST_CHOICE = 'soulless_rest_source_choice'
SOULLESS_REST_TASKS = 'soulless_rest_tasks'


def _soulless_rest_policy(actor):
    import json
    from pathlib import Path
    from source_context import verified_source
    if not soulless(actor):raise ValueError('actual selected Soulless actor required')
    value=json.loads((Path(actor.r.root)/'data/soulless-rest-policy.json').read_text(encoding='utf-8'))
    if value.get('schema_version')!=1 or value.get('source')!=SOULLESS:
        raise ValueError('known Soulless rest policy required')
    verified_source(actor.r,value['source_reference'],label='Soulless rest')
    return value


def _soulless_rest_document(value):
    return {'schema':1,'id':'native/soulless-rest','variants':[{
        'rule_id':SOULLESS,'source':value['source_reference'],
        'values':{'variant':{'$input':'source_text'},'definitions':value['definitions']},
        'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
            'choices':list(value['definitions']),
            'question':'Soulless: Korean requires an Extended Action spent resting; English requires four continuous hours of rest. Which complete timing definition applies?'}}}]}


def soulless_rest_choices(actor):
    import source_policy as POLICY
    return POLICY.resolve(actor.r,_soulless_rest_document(_soulless_rest_policy(actor)))


def _soulless_rest_definition(actor):
    import source_policy as POLICY
    from source_context import verified_source
    value=_soulless_rest_policy(actor);choice=actor.spec.get(SOULLESS_REST_CHOICE)
    variant=value['default']
    if choice is not None:
        result=POLICY.resolve(actor.r,_soulless_rest_document(value),decisions={'source_text':choice})
        if result['status']!='PolicyValuesReady':raise ValueError('actual Soulless rest source decision required')
        variant=result['values']['variant']
    definition=value['definitions'][variant];reference=definition['source']
    if 'action_source' in definition:
        action={key:definition['action_source'][key] for key in ('file','sha256')}
        verified_source(actor.r,action,label='Soulless Extended Action')
    verified_source(actor.r,reference,label='Soulless rest timing',
                    source_root='source-audit' if reference['file'].startswith('source-audit/') else 'input')
    return variant,definition


def _soulless_rest_tasks(actor):
    import common_checks as C
    rows=actor.spec.get(SOULLESS_REST_TASKS,{})
    if type(rows)is not dict:raise ValueError('Soulless rest tasks must be a mapping')
    for identity,row in rows.items():
        fields={'source','actor_id','rest_id','variant','choice','start','minutes','context','reason','status','finished_at'}
        if (type(row)is not dict or set(row)!=fields or not isinstance(identity,str) or not identity.strip()
            or row['rest_id']!=identity or row['source']!=SOULLESS or row['actor_id']!=actor.entity_id
            or row['variant']!='korean_extended_action' or row['status'] not in ('pending','complete','interrupted')
            or not isinstance(row['reason'],str) or not row['reason'].strip()):
            raise ValueError('actual source-bound Soulless rest task required')
        C.integer(row['start'],'Soulless rest start',0)
        C.integer(row['minutes'],'GM-established multi-minute rest task',2)
        if type(row['context'])is not dict or set(row['context'])!={'gap_count','round_no','day'}:
            raise ValueError('Soulless rest continuity context required')
        for key,value in row['context'].items():C.integer(value,'Soulless rest '+key,0)
        if row['status']=='pending':
            if row['finished_at'] is not None:raise ValueError('pending rest task cannot claim completion')
        else:
            C.integer(row['finished_at'],'Soulless rest finish',row['start'])
            if row['status']=='complete' and row['finished_at']!=row['start']+row['minutes']*60:
                raise ValueError('Soulless rest completion duration changed')
    if sum(row['status']=='pending' for row in rows.values())>1:raise ValueError('one actual Soulless rest task at a time')
    return rows


def select_soulless_rest(engine,actor,choice):
    import state_grants as G
    from copy import deepcopy
    import world_entities as WORLD
    if WORLD.actor_index(engine).get(actor.entity_id) is not actor:raise ValueError('registered Soulless actor required')
    if type(choice)is not dict:raise ValueError('actual scoped source decision required')
    def apply(e,c):
        c.spec[SOULLESS_REST_CHOICE]=deepcopy(choice)
        _soulless_rest_definition(c)
        for row in _soulless_rest_tasks(c).values():
            if row['status']=='pending':row.update(status='interrupted',finished_at=e.elapsed_seconds)
        return deepcopy(c.spec[SOULLESS_REST_CHOICE])
    return G.transition(engine,actor,apply)


def observe_soulless_rest_task(engine,actor,*,rest_id,minutes,reason):
    """GM establishes a current rest task; only real native rest can complete it."""
    import common_checks as C,pokemon_activities as ACTIVITIES,state_grants as G
    from copy import deepcopy
    import world_entities as WORLD
    if WORLD.actor_index(engine).get(actor.entity_id) is not actor:raise ValueError('registered Soulless actor required')
    C.integer(minutes,'GM-established multi-minute rest task',2)
    if not isinstance(rest_id,str) or not rest_id.strip():raise ValueError('actual rest task identity required')
    if not isinstance(reason,str) or not reason.strip():raise ValueError('actual Extended rest task reason required')
    def apply(e,c):
        ACTIVITIES._outside(e)
        variant,_=_soulless_rest_definition(c)
        if variant!='korean_extended_action':raise ValueError('selected Korean Extended-Action definition required')
        rows=_soulless_rest_tasks(c)
        if rest_id in rows or (c.spec.get('rest_interval') or {}).get('id')==rest_id:
            raise ValueError('rest task identity already used')
        for row in rows.values():
            if row['status']=='pending':row.update(status='interrupted',finished_at=e.elapsed_seconds)
        row={'source':SOULLESS,'actor_id':c.entity_id,'rest_id':rest_id,'variant':variant,
             'choice':deepcopy(c.spec.get(SOULLESS_REST_CHOICE)),'start':e.elapsed_seconds,
             'minutes':minutes,'reason':reason,'status':'pending','finished_at':None,
             'context':{'gap_count':len(e.unresolved_time_intervals),'round_no':e.round_no,
                        'day':c.spec.get('frequency_state',{}).get('day',0)}}
        c.spec.setdefault(SOULLESS_REST_TASKS,{})[rest_id]=row
        return deepcopy(row)
    return G.transition(engine,actor,apply)


def soulless_rest_recovery(engine,actor,record,before_total,milestone):
    """Read source timing and finish a real observed task inside the rest commit."""
    variant,_=_soulless_rest_definition(actor)
    rows=_soulless_rest_tasks(actor)
    pending=next((row for row in rows.values() if row['status']=='pending'),None)
    if pending is not None:
        context={key:record['context'][key] for key in ('gap_count','round_no','day')}
        matches=(variant==pending['variant'] and pending['choice']==actor.spec.get(SOULLESS_REST_CHOICE)
                 and pending['rest_id']==record['id'] and pending['context']==context
                 and pending['start']==record['end_seconds']-record['total_minutes']*60
                 and not engine.encounter_active)
        if not matches:
            pending.update(status='interrupted',finished_at=engine.elapsed_seconds)
        elif before_total<pending['minutes']<=record['total_minutes']:
            pending.update(status='complete',finished_at=pending['start']+pending['minutes']*60)
            return True
    return variant=='english_extended_rest' and before_total<milestone<=record['total_minutes']


# Template state is an explicit GM observation. It does not create extra turns
# or execute damage. Native ordinary-actor consumers reject incompatible state
# before spending resources until their category 3/4/5 adapters are provided.
def policy(actor):
    from pathlib import Path
    import hashlib, json
    root = Path(actor.r.root)
    value = json.loads((root / "data/category2-encounter-template-policy.json").read_text(encoding="utf-8"))
    for name, digest in value["source_hashes"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError("encounter template source changed; review its state contract")
    return value


def active(actor):
    row = actor.spec.get("encounter_template")
    if row is not None and not isinstance(row, dict):
        raise ValueError("encounter template must be a state map")
    return row if row and row.get("active") else None


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be explicit nonempty text")
    return value


def _integer(value, label, low=0, high=None):
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError(label + " is outside its integral range")
    return value


def validate_template(actor, row=None):
    row = actor.spec.get("encounter_template") if row is None else row
    if row is None:
        return True
    p = policy(actor)
    if not isinstance(row, dict) or row.get("version") != 1 or row.get("kind") not in ("swarm", "boss"):
        raise ValueError("known versioned encounter template required")
    if type(row.get("active")) is not bool:
        raise ValueError("template activation must be an explicit boolean")
    _text(row.get("reason"), "template observation reason")
    _text(row.get("source_id"), "template source")
    if row["source_id"] not in p["sources"][row["kind"]]:
        raise ValueError("template source does not describe this kind")
    bars = row.get("hp_bars", {})
    if not isinstance(bars, dict):
        raise ValueError("HP bars must be an explicit state map")
    total = _integer(bars.get("total"), "total HP bars", 1)
    spent = _integer(bars.get("spent"), "spent HP bars", 0, total)
    if spent == total and actor.hp > 0:
        raise ValueError("an exhausted HP-bar collection cannot have positive current HP")
    if bars.get("current_hp_authority") != "actor.hp" or bars.get("current_capacity_authority") != "actor.max_hp":
        raise ValueError("one current HP/capacity authority required")
    stages = row.get("baseline_stages")
    if not isinstance(stages, dict) or set(stages) != set(actor.stages):
        raise ValueError("all baseline combat stages required")
    for value in stages.values():
        _integer(value, "baseline stage", -6, 6)
    slots = row.get("action_slots")
    if not isinstance(slots, list) or not slots:
        raise ValueError("explicit action slots required; no example-derived count")
    seen = set()
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("each action slot must be a state map")
        uid = _text(slot.get("id"), "action slot identity")
        if uid in seen:
            raise ValueError("duplicate action slot")
        seen.add(uid)
        _integer(slot.get("initiative"), "initiative slot", 0)
    for name in ("frequency_ledger", "condition_bindings", "round_trigger_receipts"):
        if not isinstance(row.get(name), dict):
            raise ValueError(name + " must be a state map")
    for name in ("bar_transition_receipts", "chosen_transition_effects"):
        if not isinstance(row.get(name), list):
            raise ValueError(name + " must be an ordered state list")
    if row.get("own_turn_key") is not None:
        _text(row["own_turn_key"], "own turn key")
    for cond, binding in row["condition_bindings"].items():
        if not isinstance(binding, dict):
            raise ValueError("condition binding must be a state map")
        _text(cond, "bound condition")
        _text(binding.get("source_id"), "condition producer")
        if binding.get("slot_id") is not None and binding["slot_id"] not in seen:
            raise ValueError("condition initiative binding refers to a missing action slot")
        if binding.get("variant") not in (None, "ordinary", "drowsy", "chilled"):
            raise ValueError("unknown condition variant")
        if binding.get("disabled_move_id") is not None and binding["disabled_move_id"] not in actor.moves:
            raise ValueError("disabled move must be possessed by this actual actor")
    if sum(x.get("disabled_move_id") is not None for x in row["condition_bindings"].values()) > 1:
        raise ValueError("boss template permits only one disabled move")
    if row["kind"] == "swarm":
        if actor.kind != "pokemon" or total > 5:
            raise ValueError("ordinary swarm is a Pokemon with one through five initial bars")
        _text(row.get("member_count_or_band"), "observed swarm size")
        if row.get("multiplier") != total - spent:
            raise ValueError("current swarm multiplier must equal remaining HP bars")
        _integer(row.get("swarm_points"), "current swarm points", 0, row.get("multiplier"))
        if type(row.get("first_standard_used")) is not bool:
            raise ValueError("swarm first standard action state is required")
        if row.get("injury_policy") != "immune" or (row["active"] and actor.injuries):
            raise ValueError("swarm cannot carry injuries")
        import swarm_transitions as SWARM
        SWARM.validate(actor, row)
    elif row.get("injury_policy") != "massive_half_bars_explicit_effect":
        raise ValueError("boss injury triggers must stay distinct from ordinary HP markers")
    if row["kind"] == "boss":
        if not isinstance(row.get("normal_form_baseline"), dict):
            raise ValueError("boss needs a retained normal-form baseline")
        if row.get("capture_visibility") != "public":
            raise ValueError("boss capture immunity ending must be visible")
        import boss_transitions as BOSS
        BOSS.validate(actor, row)
    return True


def configure(engine, actor, *, kind, total_bars=None, action_slots=None, reason,
              member_count_or_band=None, baseline_stages=None,
              transition_effects=(), action_basis=None, base_initiative=None,
              capture_level=None, capture_choices=None, initiative_source_choice=None):
    import state_grants as G
    return G.transition(engine, actor, lambda e, c: _configure(
        e, c, kind=kind, total_bars=total_bars, action_slots=action_slots,
        reason=reason, member_count_or_band=member_count_or_band,
        baseline_stages=baseline_stages, transition_effects=transition_effects,
        action_basis=action_basis, base_initiative=base_initiative,
        capture_level=capture_level, capture_choices=capture_choices,
        initiative_source_choice=initiative_source_choice))


def _configure(engine, actor, *, kind, total_bars, action_slots, reason,
               member_count_or_band=None, baseline_stages=None,
               transition_effects=(), action_basis=None, base_initiative=None,
               capture_level=None, capture_choices=None, initiative_source_choice=None):
    from copy import deepcopy
    import world_entities as W
    if W.actor_index(engine).get(actor.entity_id) is not actor:
        raise ValueError("template applies only to an actual registered actor")
    if actor.spec.get("encounter_template") is not None:
        raise ValueError("template already exists; record a state update instead")
    if soulless(actor):
        raise ValueError("Soulless and multibar template interaction requires a selected rule decision")
    p = policy(actor)
    if kind not in ("swarm", "boss"):
        raise ValueError("unknown encounter template")
    boss_runtime = None
    if kind == "boss":
        import boss_transitions as BOSS
        total_bars, action_slots, transition_effects, boss_runtime = BOSS.prepare_configuration(
            actor, total_bars=total_bars, action_slots=action_slots,
            action_basis=action_basis, base_initiative=base_initiative,
            capture_level=capture_level, transition_effects=transition_effects,
            initiative_source_choice=initiative_source_choice)
    elif initiative_source_choice is not None:
        raise ValueError('boss initiative source choice requires a boss')
    elif total_bars is None or action_slots is None:
        raise ValueError("swarm bars and action slots must be explicit")
    if baseline_stages is None and kind=='boss':
        import combat_stage_sources as STAGE_SOURCES
        sources=STAGE_SOURCES.validate(actor)
        if sources is not None:baseline_stages=deepcopy(sources['combat'])
    row = {"version": 1, "kind": kind, "active": True, "reason": reason,
           "source_id": p["sources"][kind][0],
           "hp_bars": {"total": total_bars, "spent": 0, "current_hp_authority": "actor.hp", "current_capacity_authority": "actor.max_hp"},
           "baseline_stages": deepcopy(actor.stages if baseline_stages is None else baseline_stages),
           "action_slots": deepcopy(action_slots), "own_turn_key": None,
           "frequency_ledger": {}, "condition_bindings": {}, "round_trigger_receipts": {},
           "bar_transition_receipts": [], "chosen_transition_effects": deepcopy(list(transition_effects)),
           "normal_form_baseline": deepcopy({key: actor.spec.get(key) for key in ("level", "stats", "moves", "abilities", "types")}),
           "injury_policy": "immune" if kind == "swarm" else "massive_half_bars_explicit_effect"}
    if kind == "swarm":
        row.update(member_count_or_band=member_count_or_band, multiplier=total_bars,
                   swarm_points=0, first_standard_used=False)
    else:
        row["capture_visibility"] = "public"
        row["boss_runtime"] = boss_runtime
        import boss_transitions as BOSS
        row['capture_form'] = BOSS.prepare_capture_form(actor, capture_level, capture_choices)
    validate_template(actor, row)
    actor.spec["encounter_template"] = row
    actor._state_revision += 1
    engine.gm._rec("encounter template", None, deepcopy(row), reason, actor)
    return projection(actor)


def record(engine, actor, *, state, reason, request_id):
    import state_grants as G
    return G.transition(engine, actor, lambda e, c: _record(
        e, c, state=state, reason=reason, request_id=request_id))


def _record(engine, actor, *, state, reason, request_id):
    """Record an already adjudicated state; no new actions, damage or choices."""
    from copy import deepcopy
    import world_entities as W
    if W.actor_index(engine).get(actor.entity_id) is not actor:
        raise ValueError("actual registered actor required")
    _text(reason, "state observation reason"); _text(request_id, "observation identity")
    previous = actor.spec.get("encounter_template")
    if previous is None:
        raise ValueError("configure a template before observing transitions")
    receipts = actor.spec.get("encounter_template_observations", {})
    if request_id in receipts:
        if receipts[request_id]["state"] != state or receipts[request_id]["reason"] != reason:
            raise ValueError("observation identity reused with different state")
        return projection(actor)
    wanted = deepcopy(state)
    for name in ("version", "kind", "source_id", "normal_form_baseline", "capture_form"):
        if wanted.get(name) != previous.get(name):
            raise ValueError("observation cannot rewrite template identity or normal baseline")
    if wanted.get("hp_bars", {}).get("total") != previous["hp_bars"]["total"]:
        raise ValueError("observation cannot rewrite the original HP bar count")
    validate_template(actor, wanted)
    actor.spec["encounter_template"] = wanted
    actor.spec.setdefault("encounter_template_observations", {})[request_id] = {"state": deepcopy(state), "reason": reason}
    actor._state_revision += 1
    engine.gm._rec("encounter template state", previous, wanted, reason, actor)
    return projection(actor)


def projection(actor):
    from copy import deepcopy
    row = actor.spec.get("encounter_template")
    if row is None:
        return None
    validate_template(actor)
    result = deepcopy(row)
    result["entity_id"] = actor.entity_id
    result["current_hp"] = actor.hp
    result["current_capacity"] = actor.max_hp if row["hp_bars"]["spent"] < row["hp_bars"]["total"] else None
    result["remaining_bars"] = row["hp_bars"]["total"] - row["hp_bars"]["spent"]
    if row["kind"] == "swarm":
        bands = policy(actor)["swarm_size_bands"]
        result["initial_size_band"] = bands[str(row["hp_bars"]["total"])]
        result["current_size_band"] = bands.get(str(result["remaining_bars"]))
    result["capture_immune"] = row["active"] and row["kind"] == "boss" and result["remaining_bars"] > 1
    result["action_count"] = len(row["action_slots"])
    result["transition_automation"] = ("native_swarm_transition" if row["kind"] == "swarm"
                                       else "native_boss_transition")
    return result


def require_ordinary(actor, operation):
    if active(actor):
        validate_template(actor)
        import swarm_transitions as SWARM
        if SWARM.supports(actor, operation):
            return True
        import boss_transitions as BOSS
        if BOSS.supports(actor, operation):
            return True
        raise ValueError(operation + " requires the selected encounter-template transition adapter; ordinary actor rules cannot be used")


def injuries_immune(actor):
    return soulless(actor) or bool(active(actor) and active(actor)["kind"] == "swarm")


def marker_injuries_immune(actor):
    """Bosses keep massive/half-bars/explicit injuries but ignore HP markers."""
    return injuries_immune(actor) or bool(active(actor) and active(actor)["kind"] == "boss")


def multipart(engine, *, parent_id, part_ids, reason, spatial_profile=None, part_footprints=None):
    import state_grants as G
    return G.transition(engine, None, lambda e, _: _multipart(
        e, parent_id=parent_id, part_ids=part_ids, reason=reason,
        spatial_profile=spatial_profile, part_footprints=part_footprints))


def _multipart(engine, *, parent_id, part_ids, reason, spatial_profile=None, part_footprints=None):
    """Persist actual independent actor references in a world object."""
    import world_entities as W
    from copy import deepcopy
    _text(reason, "multipart observation reason")
    _text(parent_id, "multipart identity")
    if (not isinstance(part_ids, list) or len(part_ids) < 2
            or any(type(uid) is not str or not uid.strip() for uid in part_ids)
            or len(set(part_ids)) != len(part_ids)):
        raise ValueError("multipart needs distinct actual parts")
    index = W.actor_index(engine)
    entities = W.entity_index(engine)
    registry = getattr(engine, "_physical_objects", {})
    if (parent_id in entities and parent_id not in registry) or any(uid not in index for uid in part_ids):
        raise ValueError("multipart references must resolve, and parent must have its own identity")
    for uid in part_ids:
        policy(index[uid])
        if index[uid].spec.get("multipart_parent_id") not in (None, parent_id):
            raise ValueError("part already belongs to another multipart entity")
    if parent_id in registry and registry[parent_id].get("kind") != "multipart_actor":
        raise ValueError("multipart identity collides with an existing object")
    row = {"id": parent_id, "kind": "multipart_actor", "part_ids": list(part_ids),
           "location": {"kind": "unknown"}, "source_ids": ["C11-138", "C11-139", "C11-140"],
           "provenance": {"kind": "gm_observation", "reason": reason}}
    before = deepcopy(registry.get(parent_id))
    if before and before.get("spatial_profile"):
        if set(before["part_ids"]) != set(part_ids):
            raise ValueError("selected Hydreigon members cannot be replaced")
        row["spatial_profile"] = deepcopy(before["spatial_profile"])
    proposed = dict(registry); proposed[parent_id] = row
    for uid in registry.get(parent_id, {}).get("part_ids", []):
        if uid not in part_ids and uid in index:
            index[uid].spec.pop("multipart_parent_id", None)
    W.commit_objects(engine, proposed)
    row = engine._physical_objects[parent_id]
    for uid in part_ids:
        index[uid].spec["multipart_parent_id"] = parent_id
    _configure_multipart_space(engine, row, spatial_profile, part_footprints, reason)
    engine.gm._rec("multipart entity", before, row, reason, None)
    return multipart_projection(engine, parent_id)


def _head_shape(actor):
    """The printed 4x1 rectangle uses the existing observed grid anchor."""
    import body_state as BODY
    offsets = BODY.offsets(actor)
    if offsets is None or len(offsets) != 4:
        raise ValueError("Hydreigon head needs an observed cardinal 4x1 footprint")
    xs = {x for x, _ in offsets}; ys = {y for _, y in offsets}
    if not ((len(xs) == 4 and max(xs)-min(xs) == 3 and len(ys) == 1)
            or (len(ys) == 4 and max(ys)-min(ys) == 3 and len(xs) == 1)):
        raise ValueError("Hydreigon head needs an observed cardinal 4x1 footprint")


def _multipart_space(row):
    import state_fields as F
    space = row.get("spatial_profile")
    if space is None:
        return None
    if (type(space) is not dict or set(space) != {"id", "source_id", "origins"}
            or space["id"] != "hydreigon" or space["source_id"] != "C11-140"
            or len(row["part_ids"]) != 3 or len(set(row["part_ids"])) != 3
            or type(space["origins"]) is not dict or set(space["origins"]) != set(row["part_ids"])):
        raise ValueError("exact three-head Hydreigon starting origins required")
    for location in space["origins"].values():
        if F.location(location)["kind"] != "grid":
            raise ValueError("Hydreigon starting origins need actual grid locations")
    return space


def _configure_multipart_space(engine, row, profile, footprints, reason):
    import world_entities as W, body_state as BODY
    if profile not in (None, "hydreigon"):
        raise ValueError("unknown multipart spatial profile")
    if profile is None and footprints is not None:
        raise ValueError("part footprints require explicit Hydreigon adoption")
    if profile is None and not row.get("spatial_profile"):
        return
    index = W.actor_index(engine)
    parts = [index[uid] for uid in row["part_ids"]]
    if len(parts) != 3 or any(part.kind != "pokemon" or part.spec.get("species") != "pokemon/삼삼드래" for part in parts):
        raise ValueError("Hydreigon adoption needs exactly three actual Hydreigon heads")
    if engine.grid is None:
        raise ValueError("Hydreigon adoption needs an actual mapped battlefield")
    if footprints is not None:
        if type(footprints) is not dict or set(footprints) != set(row["part_ids"]):
            raise ValueError("exact footprint observations for all three heads required")
        for part in parts:
            BODY.observe(engine, part, footprints[part.entity_id], reason=reason)
    for part in parts:
        _head_shape(part)
    # Re-observing membership must not refill the stretch region after a move.
    if not row.get("spatial_profile"):
        row["spatial_profile"] = {"id": "hydreigon", "source_id": "C11-140",
            "origins": {part.entity_id: W.location_of(part) for part in parts}}
    _multipart_space(row)
    if any(not BODY.can_place(engine, part, part.pos) for part in parts):
        raise ValueError("Hydreigon head placement exceeds its region or actual body clearance")


def multipart_can_place(engine, actor, position):
    """Source stretch is a starting-point region, not a movement allowance."""
    import world_entities as W
    parent_id = actor.spec.get("multipart_parent_id")
    if not parent_id:
        return True
    row = getattr(engine, "_physical_objects", {}).get(parent_id)
    if not row or row.get("kind") != "multipart_actor" or actor.entity_id not in row["part_ids"]:
        raise ValueError("actual multipart membership required")
    space = _multipart_space(row)
    if space is None:
        return True
    _head_shape(actor)
    origin = space["origins"][actor.entity_id]
    if W.location_of(actor).get("map_id") != origin.get("map_id"):
        raise ValueError("Hydreigon starting origin belongs to another battlefield")
    from grid import cheb
    return cheb(position, origin["cell"]) <= 7


def relocate_multipart(engine, *, parent_id, destinations, reason):
    """Observe all three new positions as the new stretch origins atomically.

    The source supplies neither a reposition frequency nor an action cost.
    This GM observation does not grant an action or invent a travelled path.
    """
    import state_grants as G
    return G.transition(engine, None, lambda e, _: _relocate_multipart(
        e, parent_id=parent_id, destinations=destinations, reason=reason))


def _relocate_multipart(engine, *, parent_id, destinations, reason):
    import world_entities as W, body_state as BODY, state_fields as F
    from copy import deepcopy
    _text(reason, "whole multipart relocation reason")
    before = multipart_projection(engine, parent_id)
    row = engine._physical_objects[parent_id]
    if _multipart_space(row) is None:
        raise ValueError("whole reposition requires the selected Hydreigon sample")
    if engine.grid is None:
        raise ValueError("whole reposition needs an actual mapped battlefield")
    if type(destinations) is not dict or set(destinations) != set(row["part_ids"]):
        raise ValueError("exact destinations for all three actual heads required")
    index = W.actor_index(engine)
    locations = {uid: F.location(dict(W.location_of(index[uid]), cell=destination))
        for uid, destination in destinations.items()}
    row["spatial_profile"]["origins"] = deepcopy(locations)
    for uid, location in locations.items():
        W.observe_location(engine, index[uid], location, reason=reason, source="C11-140")
    if any(not BODY.can_place(engine, index[uid], index[uid].pos) for uid in row["part_ids"]):
        raise ValueError("whole Hydreigon relocation needs clear full-body placements")
    result = multipart_projection(engine, parent_id)
    engine.gm._rec("multipart relocation", before, result, reason, None)
    return result


def multipart_projection(engine, parent_id):
    import world_entities as W
    from copy import deepcopy
    row = getattr(engine, "_physical_objects", {}).get(parent_id)
    if not row or row.get("kind") != "multipart_actor":
        raise ValueError("actual multipart entity required")
    index = W.actor_index(engine)
    import body_state as BODY
    result = deepcopy(row); result["parts"] = []
    space = _multipart_space(row)
    for uid in row["part_ids"]:
        actor = index.get(uid)
        if actor is None or actor.spec.get("multipart_parent_id") != parent_id:
            raise ValueError("multipart contains an unresolved or mismatched part")
        if space is not None:
            policy(actor)
            if actor.kind != "pokemon" or actor.spec.get("species") != "pokemon/삼삼드래":
                raise ValueError("selected Hydreigon head species required")
            if not multipart_can_place(engine, actor, W.grid_cell(actor)):
                raise ValueError("Hydreigon head exceeds its starting-position 7m region")
        result["parts"].append({"entity_id": uid, "hp": actor.hp, "max_hp": actor.max_hp,
          "location": W.location_of(actor), "footprint": BODY.projection(actor),
          "moves": list(actor.moves), "abilities": list(actor.abilities),
          "template": projection(actor)})
    return result


def validate_world_templates(engine):
    import world_entities as W
    index = W.actor_index(engine)
    for actor in index.values():
        validate_template(actor)
        if actor.spec.get("multipart_parent_id"):
            row = multipart_projection(engine, actor.spec["multipart_parent_id"])
            if actor.entity_id not in row["part_ids"]:
                raise ValueError("actor refers to a multipart parent that does not include it")
    for uid, row in getattr(engine, "_physical_objects", {}).items():
        if row.get("kind") == "multipart_actor":
            multipart_projection(engine, uid)
    return True
