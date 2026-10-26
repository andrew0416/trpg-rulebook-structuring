"""Source ownership for effective grants and registered passive contributions.

This records state ownership, not acquisition legality. Permanent moves/abilities
remain in spec; an equipment or temporary source never becomes that baseline.
All receipts under spec are JSON-compatible; runtime rows carry source tokens.
"""
from copy import deepcopy
from contextvars import ContextVar

_TRANSITION_MOVE_ALIASES = ContextVar("transition_move_aliases", default=())

KEY = "state_grants"
LIST_FIELDS = ("moves", "abilities", "capabilities")
SET_FIELDS = ("status_immune", "weather_immune", "keyword_immune", "move_immune", "stage_loss_immune")
NUMBER_FIELDS = ("initiative_bonus", "save_mod", "movement", "accuracy_stage", "evasion_mod", "damage_reduction")
ROW_FIELDS = ("modifiers", "registry", "ability_triggers", "coats", "blessings")
SCALAR_FIELDS = ("_weight_class", "grounded", "damage_cap", "form", "form_rule", "type_override_next")
TAG = "_state_source"


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty identity")
    return value


def state(c):
    result = c.spec.get(KEY)
    if result is None:
        result = {"version": 1, "sources": {}, "legacy": {}, "overlays": {},
                  "numbers": {}, "sets": {}, "effects": {}, "ability_receipts": {}, "scalar_sources": {}}
        # Existing live-only values are imported as unverified runtime state,
        # never asserted to be a legally acquired permanent sheet value.
        for field in LIST_FIELDS:
            base = c.spec.get(field, [])
            result["legacy"][field] = list(dict.fromkeys(v for v in getattr(c, field, []) if v not in base))
        c.spec[KEY] = result
    if not isinstance(result, dict) or result.get("version") != 1:
        raise ValueError("unsupported source-grant state")
    return result


def _source(c, source_id, kind, **metadata):
    _text(source_id, "source"); _text(kind, "source kind")
    st = state(c)
    row = st["sources"].get(source_id)
    if row is not None and row.get('payment_id'):
        raise ValueError('paid group source cannot be extended; acquire a new group')
    if row is None and any(source_id in payment['children'] for payment in st.get('payments',{}).values()):
        raise ValueError('paid grant identity cannot be reused after withdrawal')
    if row is None:
        row = {"kind": kind, "grants": {}, **deepcopy(metadata)}
        st["sources"][source_id] = row
    elif row["kind"] != kind or any(k in row and row[k] != v for k, v in metadata.items()):
        raise ValueError("source identity cannot be reused with different provenance")
    else:
        for k, v in metadata.items():
            row.setdefault(k, deepcopy(v))
    return row


def effective(c, field, *, include_suppressed=False, only=None):
    if field not in LIST_FIELDS:
        raise ValueError("unknown source-owned list field")
    if only is not None:
        if field!='capabilities' or not isinstance(only,(list,tuple,set,frozenset)) or any(type(v)is not str or not v for v in only):
            raise ValueError('named capability query needs exact capability identities')
    st = c.spec.get(KEY, {}) if field == "capabilities" else state(c)
    result = list(c.spec.get(field, []))
    if field == 'capabilities' and c.spec.get('csv_remaining_form_state', {}).get('weapon_union'):
        import csv_item_form_contracts as CSV_FORMS
        result = CSV_FORMS.capability_baseline(c, result)
    result += st.get("legacy", {}).get(field, [])
    import move_state as MOVES_STATE
    for row in st.get("sources", {}).values():
        if not MOVES_STATE.source_active(c.spec,row):continue
        result.extend(row["grants"].get(field, []))
    if field=='capabilities':
        import move_capabilities as MOVE_CAPABILITIES
        result.extend(row['capability'] for row in MOVE_CAPABILITIES.contributions(c))
        result.extend(__import__('survivalist_class').capability_contributions(c))
    overlays = [r[field] for r in st.get("overlays", {}).values() if field in r]
    if overlays:
        result = overlays[-1]
    if field=='capabilities':
        import csv_item_capability_contracts as CSV_CAP
        if c.spec.get('csv_essence_projection',{}).get('essence',10)<=4:
            result=[value for value in result if not CSV_CAP.aura_capability(value)]
    if field=="abilities":
        import ability_transitions as ABILITY_TRANSITIONS
        result=ABILITY_TRANSITIONS.project(c,result,include_suppressed=include_suppressed)
    if field=='capabilities':
        if only is not None:
            import skill_modifiers as SKILL
            names={SKILL.key(value.removeprefix('capability/')) for value in only}
            result=[value for value in result if SKILL.key(value.removeprefix('capability/')) in names]
        if not include_suppressed:result=filter_capability_losses(c,result)
    return list(dict.fromkeys(result))


def materialize(c, field):
    result = effective(c, field)
    if field != "capabilities":setattr(c, field, result)
    else:
        import item_maturation as MATURATION
        MATURATION.capability_changed(c,result)
    return result


def grant(c, field, value, source_id, kind, *, owner_id=None, lifetime=None,
          rule_id=None, tutor_points=0):
    if field not in LIST_FIELDS:
        raise ValueError("unknown source-owned list field")
    _text(value, "grant")
    if field == "moves":
        return grant_moves(c,[value],source_id,kind,owner_id=owner_id,lifetime=lifetime,rule_id=rule_id,tutor_points=tutor_points)
    if type(tutor_points) is not int or tutor_points < 0:
        raise ValueError("refundable tutor points must be nonnegative whole points")
    import move_state as MOVES_STATE
    MOVES_STATE.preflight_grant(c,field,value,source_id,tutor_points=tutor_points)
    row = _source(c, source_id, kind, owner_id=owner_id, lifetime=lifetime,
                  rule_id=rule_id, tutor_points=tutor_points)
    values = row["grants"].setdefault(field, [])
    changed = value not in values
    if changed:
        values.append(value)
    materialize(c, field)
    return changed


def skill_modifier(c,skill,delta,source_id,kind,*,rule_id,owner_id=None,lifetime=None):
    """Own an unconditional flat check modifier, never a permanent rank/die."""
    import skill_modifiers as SKILL
    canonical=SKILL.skill_id(c.r.skill_policy,skill,required=True)
    if type(delta) is not int:raise ValueError('whole-number skill modifier required')
    if c.r._selected_rule(rule_id)!=rule_id:raise ValueError('selected skill modifier source required')
    row=_source(c,source_id,kind,rule_id=rule_id,owner_id=owner_id,lifetime=lifetime,tutor_points=0)
    contribution={'skill':canonical,'delta':delta}
    existing=row['grants'].get('skill_modifiers')
    if existing is not None and existing!=[contribution]:raise ValueError('skill modifier source identity collision')
    row['grants']['skill_modifiers']=[contribution]
    return deepcopy(contribution)


def grant_moves(c,values,source_id,kind,*,owner_id=None,lifetime=None,rule_id=None,tutor_points=0,mode="learned"):
    """Validate a whole sourced move batch before creating any ledger record."""
    _text(source_id,'source');_text(kind,'source kind')
    if type(tutor_points)is not int or tutor_points<0:raise ValueError('refundable tutor points must be nonnegative whole points')
    ids=move_grants(c.r,{'moves':values})
    if any(mid in getattr(c.r,'excluded_moves',{}) for mid in ids):raise ValueError('move grant belongs to an excluded source')
    if mode not in ('learned','permission'):raise ValueError('explicit learned move or temporary use permission required')
    if mode=='permission' and tutor_points:raise ValueError('temporary permission cannot claim paid learning points')
    metadata=dict(owner_id=owner_id,lifetime=lifetime,rule_id=rule_id,tutor_points=tutor_points,move_mode=mode)
    import move_state as MOVES_STATE
    MOVES_STATE.preflight_move_grants(c,ids,source_id,kind,metadata)
    import move_capabilities as MOVE_CAPABILITIES
    capability_plan=MOVE_CAPABILITIES.plan_change(c,granted=ids) if mode=='learned' else {}
    row=_source(c,source_id,kind,**metadata)
    MOVE_CAPABILITIES.commit_change(c,capability_plan)
    prior=row['grants'].setdefault('moves',[]);changed=any(mid not in prior for mid in ids)
    prior.extend(mid for mid in ids if mid not in prior)
    materialize(c,'moves')
    return changed


def set_baseline(c, field, values):
    if field not in LIST_FIELDS or not isinstance(values, (list, tuple)):
        raise ValueError("baseline requires a move or ability list")
    if any(not isinstance(v, str) or not v for v in values):
        raise ValueError("baseline entries need identities")
    import move_state as MOVES_STATE
    MOVES_STATE.preflight_baseline(c,field,values)
    if field in ('abilities','capabilities'):
        import actor_templates as TEMPLATES
        TEMPLATES.validate_soulless_default(c.r,dict(c.spec,**{field:list(values)}))
    import move_capabilities as MOVE_CAPABILITIES
    capability_plan=MOVE_CAPABILITIES.plan_change(c,baseline=values) if field=='moves' else {}
    if field=='moves' and c.kind=='pokemon':
        MOVES_STATE.record_natural_opportunities(c.r,c.spec,reason='known natural history before permanent-list observation')
    st = state(c)
    previous_base = c.spec.get(field, [])
    st["legacy"][field] = [v for v in st["legacy"].get(field, []) if v not in values and v not in previous_base]
    c.spec[field] = list(dict.fromkeys(values))
    if field=='moves' and c.kind=='pokemon':
        MOVES_STATE.record_natural_opportunities(c.r,c.spec,reason='known natural history after permanent-list observation')
    MOVE_CAPABILITIES.commit_change(c,capability_plan)
    return materialize(c, field)


def overlay(c, source_id, **fields):
    _text(source_id, "overlay source")
    if not fields or any(k not in LIST_FIELDS for k in fields):
        raise ValueError("list replacement overlay requires moves or abilities")
    if any(not isinstance(v, (list, tuple)) or any(not isinstance(x, str) for x in v) for v in fields.values()):
        raise ValueError("overlay values must be identity lists")
    state(c)["overlays"][source_id] = {k:list(dict.fromkeys(v)) for k,v in fields.items()}
    for field in fields:
        materialize(c, field)


def _get(c, field):
    if "." in field:
        head, key = field.split(".", 1)
        return getattr(c, head).get(key)
    return getattr(c, field, 0)


def _put(c, field, value):
    if "." in field:
        head, key = field.split(".", 1)
        getattr(c, head)[key] = value
    else:
        setattr(c, field, value)


def _bounded(value, bounds):
    if bounds is None:
        return value
    return max(bounds[0], min(bounds[1], value))


def numeric(c, field, delta, source_id, *, bounds=None):
    """Add a declared contribution, preserving independent additive changes."""
    if type(delta) is not int:
        raise ValueError("numeric source contribution must be a whole number")
    st = state(c)
    row = st["numbers"].get(field)
    bounds = list(bounds) if bounds is not None else None
    if row is None:
        row = {"base": _get(c, field), "sources": {}, "bounds": bounds, "visible": _get(c, field)}
        st["numbers"][field] = row
    elif row["bounds"] != bounds:
        raise ValueError("numeric channel bounds disagree")
    _sync_number(c, field, row)
    if source_id in row["sources"]:
        if row["sources"][source_id] != delta:
            raise ValueError("numeric contribution identity collision")
        return
    previous = _get(c, field)
    row["sources"][source_id] = delta
    _render_number(c, field, row)
    if field in ("accuracy_stage", "evasion_mod"):
        marker = "_passive_acc" if field == "accuracy_stage" else "_passive_eva"
        setattr(c, marker, getattr(c, marker, 0) + _get(c, field) - previous)


def _sync_number(c, field, row):
    live = _get(c, field)
    if live == row["visible"]:
        return
    if row["bounds"] is not None:
        raise ValueError("untracked bounded state change requires explicit reconciliation: " + field)
    row["base"] += live - row["visible"]
    row["visible"] = live


def _render_number(c, field, row):
    value = _bounded(row["base"] + sum(row["sources"].values()), row["bounds"])
    _put(c, field, value)
    row["visible"] = value


def adjust_numeric(c, field, delta):
    """Explicit ordinary mutation on a source-owned bounded channel."""
    row = state(c)["numbers"].get(field)
    if row is None:
        return False
    _sync_number(c, field, row)
    desired = _bounded(_get(c, field) + delta, row["bounds"])
    row["base"] = desired - sum(row["sources"].values())
    _render_number(c, field, row)
    return True


def set_numeric_base(c, field, value):
    row = state(c)["numbers"].get(field)
    if row is None:
        return False
    row["base"] = value
    _render_number(c, field, row)
    return True


def set_member(c, field, value, source_id):
    if field not in SET_FIELDS:
        raise ValueError("unsupported set contribution")
    st = state(c)
    row = st["sets"].setdefault(field, {"base": sorted(getattr(c, field, set())), "sources": {}, "visible": sorted(getattr(c, field, set()))})
    # New, distinct untracked members are safely retained. Overlapping ownership
    # must use this API; a set alone cannot prove that a second owner exists.
    live = set(getattr(c, field, set()))
    row["base"] = sorted(set(row["base"]) | (live - set(row["visible"])))
    row["sources"].setdefault(source_id, [])
    if value not in row["sources"][source_id]:
        row["sources"][source_id].append(value)
    _render_set(c, field, row)


def _render_set(c, field, row):
    value = set(row["base"])
    for values in row["sources"].values():
        value.update(values)
    setattr(c, field, value)
    row["visible"] = sorted(value)


def scalar(c, field, value, source_id):
    if field == "_weight_class":
        return weight(c,value,source_id)
    if field == "_types":
        return type_operation(c,"set",value,source_id)
    st = state(c)
    row = st["scalar_sources"].setdefault(field, {"base": deepcopy(_get(c,field)), "sources": {}, "visible": deepcopy(_get(c,field))})
    if _get(c,field) != row["visible"]:
        row["base"] = deepcopy(_get(c,field))
    row["sources"][source_id] = deepcopy(value)
    row["visible"] = deepcopy(value)
    _put(c, field, deepcopy(value))


def weight(c,value,source_id,*,mode="set",minimum=1):
    """Ordered replacements and additive weight changes, without sheet writes."""
    if mode not in ("set","add") or type(value)is not int or type(minimum)is not int:
        raise ValueError("weight source needs an explicit whole-number operation")
    st=state(c)
    row=st.setdefault("weight_sources",{"base":c._weight_class,"sources":{},"visible":c._weight_class})
    if c._weight_class!=row["visible"]:
        raise ValueError("untracked weight change requires explicit reconciliation")
    operation={"mode":mode,"value":value,"minimum":minimum}
    previous=row["sources"].get(source_id)
    if previous is not None and previous!=operation:raise ValueError("weight source identity collision")
    row["sources"][source_id]=operation
    _render_weight(c,row)


def _weight_value(row,base):
    value=row["base"]
    if row["sources"]:
        if value is None:value=base
        if type(value)is not int:raise ValueError("weight modification requires known base weight")
        for op in row["sources"].values():
            value=op["value"] if op["mode"]=="set" else max(op["minimum"],value+op["value"])
    return value


def _render_weight(c,row):
    value=_weight_value(row,c.spec.get("weight_class"))
    row["visible"]=value;c._weight_class=value


def prepare_weight_baseline(c,new_weight):
    row=c.spec.get(KEY,{}).get("weight_sources")
    if row is None:return c._weight_class
    if c._weight_class!=row["visible"]:raise ValueError("untracked weight change requires explicit reconciliation")
    return _weight_value(row,new_weight)


def commit_weight_baseline(c):
    row=c.spec.get(KEY,{}).get("weight_sources")
    if row is not None:_render_weight(c,row)


def type_operation(c,mode,values,source_id,*,fallback=None):
    import homebrew_state as HOME
    if HOME.type_change_blocked(c):return False
    if mode not in ("set","add","remove") or not isinstance(values,(list,tuple)) or any(not isinstance(value,str) or not value for value in values):
        raise ValueError("type source requires an explicit type operation")
    import type_state as TYPES
    TYPES.validate_types(c.r,values,label="type-source values")
    if fallback is not None:TYPES.validate_types(c.r,[fallback],label="type-source fallback")
    _text(source_id,"type source identity")
    st=state(c)
    row=st.setdefault("type_sources",{"base":None if c._types==c.spec.get("types",[]) else list(c._types),"sources":{},"visible":list(c._types)})
    if c._types!=row["visible"]:raise ValueError("untracked type change requires explicit reconciliation")
    operation={"mode":mode,"values":list(dict.fromkeys(values)),"fallback":fallback}
    if source_id in row["sources"] and row["sources"][source_id]!=operation:raise ValueError("type source identity collision")
    row["sources"][source_id]=operation
    _render_types(c,row)


def _type_value(row,base):
    value=list(base if row["base"] is None else row["base"])
    for op in row["sources"].values():
        if op["mode"]=="set":value=list(op["values"])
        elif op["mode"]=="add":value=list(dict.fromkeys(value+op["values"]))
        else:
            value=[item for item in value if item not in op["values"]]
            if not value and op["fallback"]:value=[op["fallback"]]
    return value


def _render_types(c,row):
    value=_type_value(row,c.spec.get("types",[]))
    row["visible"]=list(value);c._types=value


def prepare_type_baseline(c,new_types):
    row=c.spec.get(KEY,{}).get("type_sources")
    if row is None:return list(new_types) if c._types==c.spec.get("types",[]) else list(c._types)
    if c._types!=row["visible"]:raise ValueError("untracked type change requires explicit reconciliation")
    return _type_value(row,new_types)


def commit_type_baseline(c):
    row=c.spec.get(KEY,{}).get("type_sources")
    if row is not None:_render_types(c,row)


def stat(c,field,delta,source_id,*,minimum=None,operation_id="0"):
    """Record the declared raw operation only after validating its result."""
    if field not in c.stats or type(delta)is not int or (minimum is not None and type(minimum)is not int):
        raise ValueError("stat source requires a known statistic and whole-number operation")
    _text(source_id,"stat source identity")
    st=c.spec.get(KEY,{})
    if st.get('sources',{}).get(source_id,{}).get('payment_id'):
        raise ValueError('paid group source cannot be extended; acquire a new group')
    if "stats."+field in st.get("numbers",{}):
        raise ValueError("legacy observed stat contribution requires explicit raw-source import")
    current=st.get("stat_sources",{}).get(field)
    if current is not None and c.stats[field]!=current["visible"]:
        raise ValueError("untracked stat change requires explicit reconciliation: "+field)
    row=deepcopy(current) if current is not None else {
        "base_offset":c.stats[field]-c.spec["stats"][field],"sources":{},"visible":c.stats[field]}
    operations=row["sources"].setdefault(source_id,{})
    operation={"delta":delta,"minimum":minimum};key=str(operation_id)
    if key in operations and operations[key]!=operation:raise ValueError("stat operation identity collision")
    operations[key]=operation
    value=_stat_value(row,c.spec["stats"][field])
    from state_fields import stat_minimum
    if value<stat_minimum(c.spec,field):raise ValueError("source would make effective statistic invalid")
    row["visible"]=value
    rows=state(c).setdefault("stat_sources",{})
    if current is None:rows[field]=row
    else:
        current["sources"].setdefault(source_id,{})[key]=operation
        current["visible"]=value
    c.stats[field]=value


def reconcile_stat(c,field,delta,source_id,*,minimum=None,operation_id="0"):
    """Replace one declared source operation without changing its baseline.

    Level-derived Static features own a formula, not the integer that happened
    to be visible when they were first registered.  This narrow reconciliation
    path keeps the same source and operation identities while a reviewed input
    to that formula changes.  Ordinary callers still use :func:`stat`, whose
    collision check prevents accidental rewrites.
    """
    if field not in c.stats or type(delta) is not int or (minimum is not None and type(minimum) is not int):
        raise ValueError("stat source requires a known statistic and whole-number operation")
    _text(source_id,"stat source identity")
    key=str(operation_id)
    row=(state(c) if c.spec.get(KEY) is not None else {}).get("stat_sources",{}).get(field)
    if row is None or source_id not in row.get("sources",{}) or key not in row["sources"][source_id]:
        return stat(c,field,delta,source_id,minimum=minimum,operation_id=key)
    if c.stats[field]!=row["visible"]:
        raise ValueError("untracked stat change requires explicit reconciliation: "+field)
    expected={"delta":delta,"minimum":minimum}
    if row["sources"][source_id][key]==expected:return False
    proposed=deepcopy(row)
    proposed["sources"][source_id][key]=expected
    value=_stat_value(proposed,c.spec["stats"][field])
    from state_fields import stat_minimum
    if value<stat_minimum(c.spec,field):raise ValueError("source would make effective statistic invalid")
    row["sources"][source_id][key]=expected
    row["visible"]=value;c.stats[field]=value
    return True


def _stat_value(row,base):
    value=base+row["base_offset"]
    for operations in row["sources"].values():
        for operation in operations.values():
            value+=operation["delta"]
            if operation["minimum"] is not None:value=max(operation["minimum"],value)
    return value


def prepare_stat_baseline(c,new_stats,*,new_spec=None):
    """Validate/recompute a proposed baseline without mutating actor or receipts."""
    result={key:c.stats[key]+new_stats[key]-c.spec["stats"][key] for key in c.stats}
    for field,row in c.spec.get(KEY,{}).get("stat_sources",{}).items():
        if c.stats[field]!=row["visible"]:
            raise ValueError("untracked stat change requires explicit reconciliation: "+field)
        result[field]=_stat_value(row,new_stats[field])
    from state_fields import stat_minimum
    if any(type(value)is not int or value<stat_minimum(c.spec if new_spec is None else new_spec,field) for field,value in result.items()):
        raise ValueError("base change would make effective statistics invalid")
    return result


def commit_stat_baseline(c):
    """Refresh source visibility after the validated permanent baseline commit."""
    for field,row in c.spec.get(KEY,{}).get("stat_sources",{}).items():
        value=_stat_value(row,c.spec["stats"][field])
        row["visible"]=value;c.stats[field]=value


def _snapshot(c):
    return {
        "numbers": {**{f:_get(c,f) for f in NUMBER_FIELDS}, **{"stats."+k:v for k,v in c.stats.items()}},
        "sets": {f:set(getattr(c,f,set())) for f in SET_FIELDS},
        "rows": {f:list(getattr(c,f,[])) for f in ROW_FIELDS},
        "scalars": {f:deepcopy(getattr(c,f,None)) for f in SCALAR_FIELDS},
        "stages": dict(c.stages),
        "moves": list(c.moves),
    }


def _restore(c, before):
    for f,v in before["numbers"].items(): _put(c,f,v)
    for f,v in before["sets"].items(): setattr(c,f,set(v))
    for f,v in before["rows"].items(): setattr(c,f,list(v))
    for f,v in before["scalars"].items(): setattr(c,f,deepcopy(v))
    c.stages = dict(before["stages"])
    c.moves = list(before["moves"])


def _declared(effects):
    import combat_modifiers as COMBAT_MODS
    numbers = {}
    sets = {}
    # A trigger/reaction body is registered, not applied as a Static effect.
    if any(isinstance(e,dict) and e.get("type") in ("trigger","reaction") for e in effects):
        return numbers,sets
    for e in effects:
        if not isinstance(e,dict): continue
        t=e.get("type");v=e.get("value")
        if t=="immune_stage_loss":
            sets.setdefault("stage_loss_immune",set()).add(e.get("stat") or "all")
        elif COMBAT_MODS.passive_field(e)=="evasion_mod":
            numbers["evasion_mod"]=numbers.get("evasion_mod",0)+v
        elif COMBAT_MODS.passive_field(e)=="accuracy_stage":
            numbers["accuracy_stage"]=numbers.get("accuracy_stage",0)+v
    return numbers,sets


class ActiveEffects:
    """Own live source registration and removal, separate from acquisition history.

    Native projections and source receipts retain their existing storage. All
    handles resolve through the actor, including after transaction restoration.
    """

    __slots__ = ("actor",)

    def __init__(self, actor):
        self.actor = actor

    def register(self, e, source_id, callback, *, effects=()):
        """Rollback failed native registration without changing graph identities."""
        c = self.actor
        originals={}
        def capture(value):
            if not isinstance(value,(dict,list,set,tuple)) or id(value) in originals:return
            if isinstance(value,dict):content=list(value.items())
            else:content=list(value)
            originals[id(value)]=(value,content)
            if isinstance(value,dict):
                for key,child in content:capture(key);capture(child)
            else:
                for child in content:capture(child)
        capture(vars(e));capture(vars(c))
        if hasattr(e,"gm"):
            capture(vars(e.gm))
            for actor in e.gm._snapshot_actors(vars(e)).values():capture(vars(actor))
        rng=e.rng.getstate()
        try:return self._register(e,source_id,callback,effects=effects)
        except Exception:
            for value,content in originals.values():
                if isinstance(value,dict):value.clear();value.update(content)
                elif isinstance(value,list):value[:]=content
                elif isinstance(value,set):value.clear();value.update(content)
            e.rng.setstate(rng)
            raise

    def register_definition_row(self, e, source_id, field, value):
        """Materialize a definition-backed executable row without replaying effects.

        Sheet-only restoration retains receipts but not runtime registries. Only
        row-only registrations can be rebuilt here; passive contributions and
        live buffs continue to require their own restoration contract.
        """
        c = self.actor
        _text(source_id,"registration source")
        if field not in ("registry","ability_triggers") or not isinstance(value,dict) or TAG in value:
            raise ValueError("definition registration requires an untagged executable row")
        st=state(c)
        receipt=st["effects"].get(source_id)
        rows=getattr(c,field)
        live=[row for row in rows if isinstance(row,dict) and row.get(TAG)==source_id]
        if receipt is None:
            if live:raise ValueError("executable registration has no source receipt")
            return self.register(e,source_id,lambda:rows.append(deepcopy(value)))
        if receipt!={"rows":[field],"listeners":[]}:
            raise ValueError("only a row-only source receipt can rebuild an executable registration")
        if len(live)>1:
            raise ValueError("duplicate executable source registration")
        if live:return False
        rows.append(dict(deepcopy(value),**{TAG:source_id}))
        return True

    def _register(self, e, source_id, callback, *, effects=()):
        """Attach exact additive, membership and appended-row contributions."""
        c = self.actor
        st=state(c)
        if source_id in st["effects"]: return False
        before=_snapshot(c)
        listeners=set(getattr(e,"_passive_listeners",{}).get(c,{}))
        previous_registration=getattr(c,"_state_registration_source",None)
        c._state_registration_source=source_id
        try:
            callback()
        except Exception:
            _restore(c,before)
            raise
        finally:
            if previous_registration is None:c.__dict__.pop("_state_registration_source",None)
            else:c._state_registration_source=previous_registration
        after=_snapshot(c)
        declared,declared_sets=_declared(effects)
        receipt={"rows":[],"listeners":sorted(set(getattr(e,"_passive_listeners",{}).get(c,{}))-listeners)}
        # Callback registration values are converted to independent contributions;
        # already tagged nested registration belongs to its own receipt.
        for field,old in before["numbers"].items():
            if field.startswith("stats.") and source_id in st.get("stat_sources",{}).get(field.split(".",1)[1],{}).get("sources",{}):continue
            if field.startswith("stats.") and after["numbers"][field]!=old:
                raise ValueError("untracked native stat writer requires an explicit raw operation: "+field)
            delta=declared.get(field,after["numbers"][field]-old)
            if delta:
                _put(c,field,old)
                numeric(c,field,delta,source_id,bounds=(-6,6) if field in ("accuracy_stage","evasion_mod") else None)
        for field,old in before["sets"].items():
            added=(after["sets"][field]-old)|declared_sets.get(field,set())
            if added:
                setattr(c,field,set(old))
                for value in sorted(added): set_member(c,field,value,source_id)
        for field,old in before["rows"].items():
            identities={id(x) for x in old}
            for value in getattr(c,field,[]):
                if id(value) not in identities and isinstance(value,dict) and TAG not in value:
                    value[TAG]=source_id
                    if field not in receipt["rows"]:receipt["rows"].append(field)
        for field,old in before["scalars"].items():
            if field=="_weight_class" and source_id in st.get("weight_sources",{}).get("sources",{}):continue
            if after["scalars"][field]!=old:
                setattr(c,field,deepcopy(old))
                scalar(c,field,after["scalars"][field],source_id)
        stage_delta={k:after["stages"][k]-v for k,v in before["stages"].items() if after["stages"][k]!=v}
        if stage_delta:
            import combat_stage_sources as CS
            c.stages=dict(before["stages"])
            for stat,delta in stage_delta.items():
                CS.add_base(c,source_id,stat,delta,source=source_id,ends=source_id)
            receipt["stages"]=True
        for move in after["moves"]:
            if move not in before["moves"] and move not in st["sources"].get(source_id,{}).get("grants",{}).get("moves",[]):
                grant(c,"moves",move,source_id,"passive",rule_id=source_id)
        st["effects"][source_id]=receipt
        return True

    def remove(self, e, source_id):
        c = self.actor
        st=state(c)
        receipt=st["effects"].get(source_id)
        # Preflight all bounded channels before any state removal.
        for field,row in st["numbers"].items():
            if source_id in row["sources"]:_sync_number(c,field,row)
        for field,row in st["numbers"].items():
            if source_id in row["sources"]:
                previous=_get(c,field)
                del row["sources"][source_id];_render_number(c,field,row)
                if field in ("accuracy_stage","evasion_mod"):
                    marker="_passive_acc" if field=="accuracy_stage" else "_passive_eva"
                    setattr(c,marker,getattr(c,marker,0)+_get(c,field)-previous)
        for field,row in st["sets"].items():
            if source_id in row["sources"]:
                live=set(getattr(c,field,set()))
                row["base"]=sorted(set(row["base"])|(live-set(row["visible"])))
                del row["sources"][source_id];_render_set(c,field,row)
        for field,row in st.get("stat_sources",{}).items():
            if source_id in row["sources"]:
                if c.stats[field]!=row["visible"]:raise ValueError("untracked stat change requires explicit reconciliation: "+field)
                del row["sources"][source_id]
                row["visible"]=_stat_value(row,c.spec["stats"][field]);c.stats[field]=row["visible"]
        types=st.get("type_sources")
        if types and source_id in types["sources"]:
            if c._types!=types["visible"]:raise ValueError("untracked type change requires explicit reconciliation")
            del types["sources"][source_id];_render_types(c,types)
        weights=st.get("weight_sources")
        if weights and source_id in weights["sources"]:
            del weights["sources"][source_id];_render_weight(c,weights)
        for field,row in st["scalar_sources"].items():
            if source_id in row["sources"]:
                live=deepcopy(_get(c,field))
                if live!=row["visible"]:row["base"]=live
                del row["sources"][source_id]
                value=next(reversed(row["sources"].values())) if row["sources"] else row["base"]
                row["visible"]=deepcopy(value);_put(c,field,deepcopy(value))
        if receipt:
            for field in receipt["rows"]:
                setattr(c,field,[r for r in getattr(c,field,[]) if not isinstance(r,dict) or r.get(TAG)!=source_id])
            for listener in receipt["listeners"]:
                getattr(e,"_passive_listeners",{}).get(c,{}).pop(listener,None)
            if receipt.get("stages"):
                import combat_stage_sources as CS
                CS.end_source(c,ends=source_id)
            del st["effects"][source_id]
        return bool(receipt)


def apply_owned(e,c,source_id,callback,*,effects=()):
    return ActiveEffects(c).register(e, source_id, callback, effects=effects)


def register_definition_row(e,c,source_id,field,value):
    return ActiveEffects(c).register_definition_row(e, source_id, field, value)


def _apply_owned(e,c,source_id,callback,*,effects=()):
    return ActiveEffects(c)._register(e, source_id, callback, effects=effects)


def remove_owned(e,c,source_id):
    return ActiveEffects(c).remove(e, source_id)


def _ability_key(rules,name):
    import move_state as MOVES_STATE
    slot=MOVES_STATE.ability_registration(rules,name)
    return slot['name'] if slot else getattr(rules,'ability_alias',{}).get(name,name)


def ensure_ability(e,c,name):
    """Engine public wrapper; invokes only the private native registration."""
    if name not in c.abilities:return False
    if name in getattr(e.r,"excluded_abilities",{}):
        e._register_abilities_one(c,name)
        return False
    import move_state as MOVES_STATE
    registration=MOVES_STATE.ability_registration(e.r,name)
    canonical=registration['name'] if registration else getattr(e.r,'ability_alias',{}).get(name,name)
    # Resolve before initializing grant storage or binding conditional effects.
    # Reviewed exact registrations may disambiguate a name; bare names may not.
    if registration is None and name in getattr(e.r,'unresolved_abilities',{}):
        from ruleset import UnresolvedRuleSelection
        raise UnresolvedRuleSelection(name,e.r.unresolved_abilities[name])
    selected=registration['source_id'] if registration else None
    if hasattr(e.r,'selection'):
        e.r.selection.require_current_filter(e.r.ruleset)
        selected=registration['source_id'] if registration else e.r.selection.resolve_name(canonical,('ability/',))
        e.r.selection.require_supported_version(selected)
    import core_weather_abilities as CORE_WEATHER
    CORE_WEATHER.bind(e,c,name)
    st=state(c)
    if canonical in st["ability_receipts"]:return False
    source_id="ability:"+canonical
    import typed_defensive_bypass as TYPED
    effects=TYPED.effects(e.r,selected) if TYPED.handles(selected) else getattr(e.r,"ability_effects",{}).get(canonical,[])
    callback=(lambda:e._register_abilities_one(c,registration['name'],selected_id=registration['source_id'])) if registration else (lambda:e._register_abilities_one(c,name))
    apply_owned(e,c,source_id,callback,effects=effects)
    st["ability_receipts"][canonical]=source_id
    import base_stage_abilities as BASE_ABILITIES
    BASE_ABILITIES.refresh(c)
    if registration and registration['source_id']=='ability/기분파':
        import ability_state_projection as PROJECTION
        PROJECTION.reconcile_weather(e,c)
    return True


def _forget_source(c,source_id):
    from acquisition_ledger import AcquisitionLedger
    AcquisitionLedger(c).end_source(source_id)


def remove_ability(e,c,name):
    canonical=_ability_key(e.r,name)
    if any(_ability_key(e.r,a)==canonical for a in c.abilities):
        return False
    st=state(c)
    source_id=st["ability_receipts"].get(canonical)
    if source_id is None:return False
    import acquisition_withdrawal as WITHDRAWAL
    WITHDRAWAL.preflight(c,{source_id})
    import move_capabilities as MOVE_CAPABILITIES
    capability_plan=MOVE_CAPABILITIES.plan_change(c,revoked=(source_id,))
    MOVE_CAPABILITIES.commit_change(c,capability_plan)
    remove_owned(e,c,source_id)
    st["ability_receipts"].pop(canonical,None)
    import move_permissions as PERMISSIONS
    PERMISSIONS.end_ability(e,c,canonical)
    # Passive abilities may themselves grant moves; those use the same source.
    _forget_source(c,source_id)
    import reactive_ability_events as REACTIVE
    REACTIVE.withdraw_ability(e,c,source_id)
    materialize(c,"moves");materialize(c,"capabilities")
    return True


def reconcile(e,c,*,activate_existing=True):
    before=list(c.abilities)
    for field in LIST_FIELDS:materialize(c,field)
    for name in list(state(c)["ability_receipts"]):
        remove_ability(e,c,name)
    for name in before:
        if name not in c.abilities:remove_ability(e,c,name)
    for name in c.abilities:
        canonical=_ability_key(e.r,name)
        if activate_existing or name not in before or canonical in state(c)["ability_receipts"]:
            ensure_ability(e,c,name)
    import base_stage_abilities as BASE_ABILITIES
    BASE_ABILITIES.refresh(c)
    import items as ITEMS
    ITEMS.synchronize_equipment_suppression(e,(c,))
    import ability_state_projection as PROJECTION
    PROJECTION.reconcile_weather(e,c)


def _revocation_sources(c, source_ids):
    st=c.spec.get(KEY)
    if st is None:return set()
    pending=list(source_ids);result=set()
    while pending:
        key=pending.pop()
        if key in result:continue
        result.add(key)
        pending.extend(st["sources"].get(key,{}).get("effect_sources",[]))
    return result


def preflight_revoke(c, source_id):
    """Read-only validation; never initializes or reconciles a legacy ledger."""
    st=c.spec.get(KEY)
    if st is None:return
    sources=_revocation_sources(c,[source_id] if isinstance(source_id,str) else source_id)
    import capture_techniques as CAPTURE
    CAPTURE.preflight_revoke(c, sources)
    remaining=list(c.spec.get("abilities",[]))+list(st["legacy"].get("abilities",[]))
    for key,row in st["sources"].items():
        if key not in sources:remaining.extend(row.get("grants",{}).get("abilities",[]))
    overlays=[row["abilities"] for key,row in st["overlays"].items() if key not in sources and "abilities" in row]
    if overlays:remaining=overlays[-1]
    import ability_transitions as ABILITY_TRANSITIONS
    remaining=ABILITY_TRANSITIONS.project(c,remaining,ignored_sources=sources)
    aliases=getattr(c.r,"ability_alias",{})
    canonical_remaining={_ability_key(c.r,name) for name in remaining}
    sources.update(receipt for name,receipt in st["ability_receipts"].items() if name not in canonical_remaining)
    import acquisition_withdrawal as WITHDRAWAL
    WITHDRAWAL.preflight(c,sources)
    import move_state as MOVES_STATE
    MOVES_STATE.preflight_revoke(c,sources)
    for name in remaining:
        if name in c.abilities or _ability_key(c.r,name) in st["ability_receipts"]:continue
        if name in getattr(c.r,"excluded_abilities",{}):continue
        if name in getattr(c.r,"unresolved_abilities",{}):
            from ruleset import UnresolvedRuleSelection
            raise UnresolvedRuleSelection(name,c.r.unresolved_abilities[name])
        if hasattr(c.r,"selection"):
            registration=MOVES_STATE.ability_registration(c.r,name)
            selected=registration["source_id"] if registration else c.r.selection.resolve_name(aliases.get(name,name),("ability/",))
            c.r.selection.require_supported_version(selected)
    for field,row in st["numbers"].items():
        if sources.intersection(row["sources"]) and row["bounds"] is not None and _get(c,field)!=row["visible"]:
            raise ValueError("untracked bounded state change requires explicit reconciliation: "+field)
    for field,row in st.get("stat_sources",{}).items():
        if sources.intersection(row["sources"]) and c.stats[field]!=row["visible"]:
            raise ValueError("untracked stat change requires explicit reconciliation: "+field)
        if sources.intersection(row["sources"]):
            from state_fields import stat_minimum
            remaining=deepcopy(row)
            remaining['sources']={key:value for key,value in row['sources'].items() if key not in sources}
            if _stat_value(remaining,c.spec['stats'][field])<stat_minimum(c.spec,field):
                raise ValueError('withdrawal would make effective statistic invalid: '+field)
    types=st.get("type_sources")
    if types and sources.intersection(types["sources"]) and c._types!=types["visible"]:
        raise ValueError("untracked type change requires explicit reconciliation")
    weights=st.get("weight_sources")
    if weights and sources.intersection(weights["sources"]) and c._weight_class!=weights["visible"]:
        raise ValueError("untracked weight change requires explicit reconciliation")
    if any(st["effects"].get(key,{}).get("stages") for key in sources):
        import combat_stage_sources as CS
        CS.validate(c)


def _revoke_sources(c,source_ids,engine,*,_settled_payment_ids=()):
    st=c.spec.get(KEY)
    if st is None:return False
    preflight_revoke(c,source_ids)
    old=list(c.abilities)
    sources=_revocation_sources(c,source_ids)
    if engine is not None:__import__('telekinetic').before_revoke(engine,c,sources)
    if engine is not None:__import__('telepath').before_revoke(engine,c,sources)
    groups={st['sources'][key]['payment_id'] for key in sources if key in st['sources'] and st['sources'][key].get('payment_id')}
    if groups-set(_settled_payment_ids):raise ValueError('group payment settlement required before withdrawal')
    found=any(key in st["sources"] or key in st["overlays"] or key in st["effects"] for key in sources)
    if engine is None and any(key in st["effects"] for key in sources):
        raise ValueError("effect source revocation requires its engine")
    import move_capabilities as MOVE_CAPABILITIES
    capability_plan=MOVE_CAPABILITIES.plan_change(c,revoked=sources)
    MOVE_CAPABILITIES.commit_change(c,capability_plan)
    for key in sources:
        __import__("provocateur").before_revoke(c,st["sources"].get(key,{}))
        if engine is not None:remove_owned(engine,c,key)
        _forget_source(c,key);st["overlays"].pop(key,None)
    if engine is not None:
        __import__('ace_trainer').forget_missing(c.r,c.spec,at=engine.elapsed_seconds,reason='actual learned source withdrawal')
    for field in LIST_FIELDS:materialize(c,field)
    if engine is not None:
        for name in list(st["ability_receipts"]):remove_ability(engine,c,name)
        for name in c.abilities:
            if name not in old:ensure_ability(engine,c,name)
    transformed=c.custom_conditions.get("transformed")
    if isinstance(transformed,dict) and transformed.get("source") in sources:c.custom_conditions.pop("transformed",None)
    if engine is not None:
        import items as ITEMS
        ITEMS.synchronize_equipment_suppression(engine,(c,))
    return found


def revoke(c,source_id,*,engine=None):
    return _revoke_sources(c,[source_id],engine)


def preview_owner_revoke(c,owner_id):
    """Pure plan for an ownership transfer; missing ledger implies no known grant."""
    _text(owner_id,"former owner")
    st=c.spec.get(KEY)
    if st is None:return {"former_owner_id":owner_id,"sources":[],"tutor_points_refunded":0}
    sources=[(key,row) for key,row in st["sources"].items()
             if row.get("owner_id")==owner_id and row.get("lifetime") in ("owner_bound","your_pokemon")]
    import grant_payments as PAYMENTS
    import acquisition_withdrawal as WITHDRAWAL
    group_refunds,refund,withdrawal_policies=WITHDRAWAL.owner_loss_plan(c,sources)
    balance=c.spec.get("tutor_points",0)
    if type(balance)is not int or balance<0:raise ValueError("invalid tutor-point balance")
    preflight_revoke(c,[source_id for source_id,_ in sources])
    plan={"former_owner_id":owner_id,"sources":[key for key,_ in sources],"tutor_points_refunded":refund}
    if group_refunds:plan['group_refunds']=group_refunds
    if withdrawal_policies:plan['withdrawal_policies']=withdrawal_policies
    return plan


def revoke_owner(e,c,owner_id,reason):
    _text(reason,"ownership change reason")
    plan=preview_owner_revoke(c,owner_id)
    if not plan["sources"]:return dict(plan,reason=reason)
    def apply(staged_engine,staged_c):
        import grant_payments as PAYMENTS
        groups=plan.get('group_refunds',[])
        PAYMENTS.settle_sources(staged_engine,staged_c,plan['sources'],groups,reason,
            legacy_refund=plan['tutor_points_refunded']-sum(row['amount'] for row in groups))
        return dict(plan,reason=reason)
    return transition(e,c,apply)


def effect_source(c, context, label):
    """Use an issued occurrence when available; legacy direct calls are explicit."""
    occurrence=context.get("effect_occurrence")
    st=state(c)
    if isinstance(occurrence,(str,int)):
        token=str(occurrence)
    else:
        st["sequence"]=st.get("sequence",0)+1
        token="legacy-"+str(st["sequence"])
    return "effect:"+str(context.get("source_id","unclassified"))+":"+label+":"+token


def effective_capabilities(c,*,only=None):
    """Read effective capability ownership without creating runtime/spec records."""
    return effective(c,"capabilities",only=only)


def capability_losses(c):
    """Source-owned subtraction, after all living positive contributions.

    elapsed_bounds is a derived projection delivered by the native world clock,
    not another clock. World validation checks it against elapsed_time.bounds.
    A source keeps its original receipt after expiry; no baseline is restored.
    """
    rows=c.spec.get(KEY,{}).get('capability_losses',{})
    if type(rows)is not dict:raise ValueError('source-owned capability losses required')
    for uid,row in rows.items():
        _text(uid,'capability loss source')
        if type(row)is not dict or set(row)!={'values','rule_id','receipt','duration','clock_anchor','unknown_index','elapsed_base','elapsed_bounds'}:
            raise ValueError('complete capability loss receipt required')
        _text(row['rule_id'],'capability loss rule');_text(row['receipt'],'capability loss receipt')
        if type(row['values'])is not list or not row['values'] or any(type(v)is not str or not v for v in row['values']):
            raise ValueError('exact lost capability identities required')
        for field in ('duration','clock_anchor','unknown_index','elapsed_base'):
            if type(row[field])is not int or row[field]<(1 if field=='duration' else 0):raise ValueError('valid capability loss clock required')
        bounds=row['elapsed_bounds']
        if type(bounds)is not list or len(bounds)!=2 or any(type(v)is not int or v<0 for v in bounds) or bounds[0]>bounds[1]:
            raise ValueError('bounded capability loss clock projection required')
    return rows


def filter_capability_losses(c,values):
    import skill_modifiers as SKILL
    blocked=set();uncertain=set()
    import special_entities as SPECIAL
    if c.spec.get(SPECIAL.PRIME_KEY) or getattr(c,'_prime_unown_loss_pending',False):
        blocked.update(SKILL.key(v) for v in ('약골','Underdog'))
    for row in capability_losses(c).values():
        low,high=row['elapsed_bounds'];names={SKILL.key(v.removeprefix('capability/')) for v in row['values']}
        if high<row['duration']:blocked.update(names)
        elif low<row['duration']:uncertain.update(names)
    present={SKILL.key(v.removeprefix('capability/')) for v in values}
    if (uncertain-blocked)&present:raise ValueError('observe actual capability loss elapsed time at the expiry boundary')
    return [v for v in values if SKILL.key(v.removeprefix('capability/')) not in blocked]


def capability_loss(engine,c,source_id,values,*,rule_id,receipt,duration):
    """Admitted consumers call inside their native state transaction."""
    _text(source_id,'capability loss source')
    if source_id in capability_losses(c):raise ValueError('capability loss source already issued')
    row=dict(values=list(dict.fromkeys(values)),rule_id=rule_id,receipt=receipt,duration=duration,
        clock_anchor=engine.elapsed_seconds,unknown_index=len(engine.unresolved_time_intervals),elapsed_base=0,elapsed_bounds=[0,0])
    state(c).setdefault('capability_losses',{})[source_id]=row
    capability_losses(c)
    return row


def sync_capability_losses(engine,index=None):
    """Refresh only derived views at existing native clock deliveries."""
    import elapsed_time as TIME
    if index is None:
        import world_entities as WORLD
        index=WORLD.actor_index(engine)
    for c in index.values():
        for row in capability_losses(c).values():
            row['elapsed_bounds']=list(TIME.bounds(engine,row['clock_anchor'],row['unknown_index'],row['elapsed_base'],label='capability loss clock'))


def validate_capability_losses(engine,index):
    import elapsed_time as TIME
    for c in index.values():
        for row in capability_losses(c).values():
            actual=list(TIME.bounds(engine,row['clock_anchor'],row['unknown_index'],row['elapsed_base'],label='capability loss clock'))
            if row['elapsed_bounds']!=actual:raise ValueError('stale or changed capability loss clock projection')


def capability_values(value):
    import re
    if isinstance(value,str):values=re.split(r",\s*(?![^()]*\))",value)
    elif isinstance(value,(list,tuple)):values=list(value)
    else:raise ValueError("capability grant needs named capabilities")
    if not values or any(not isinstance(v,str) or not v.strip() for v in values):
        raise ValueError("capability grant needs nonempty names")
    return list(dict.fromkeys(v.strip() for v in values))


def move_grants(rules,effect):
    values=effect.get("moves")
    if not isinstance(values,list) or not values:raise ValueError("move grant needs a nonempty complete move list")
    result=[]
    for value in values:
        if not isinstance(value,str):raise ValueError("move grant needs named moves")
        uid=rules.move_id(value)
        if uid is None:raise ValueError("unresolved move grant: "+value)
        result.append(uid)
    return list(dict.fromkeys(result))


def ability_grant(rules,effect,source_rule_id=None):
    value=effect.get("grant_ability")
    import source_scoped_ability_grants as SOURCE_SCOPED
    resolved=SOURCE_SCOPED.resolve(rules,effect,source_rule_id)
    if resolved is not None:return resolved
    if not isinstance(value,str) or value not in rules.ability_effects:
        raise ValueError("unresolved ability grant; explicit selected-source identity required: "+str(value))
    if value in getattr(rules,"excluded_abilities",{}):
        raise ValueError("ability grant belongs to an excluded source: "+value)
    return value


def register_feature_effect(e,owner,target,name,rule_id,index,effect):
    """Owned Static feature contribution; acquisition remains a separate rule."""
    import effects as FX
    kind=effect.get("type")
    ability=ability_grant(e.r,effect,rule_id) if kind=="grant_ability" else None
    moves=move_grants(e.r,effect) if kind=="grant_move" else None
    capabilities=capability_values(effect.get("capability")) if kind=="grant_capability" else None
    key="feature:"+str(owner.spec.get("id",owner.name))+":"+rule_id
    lifetime="your_pokemon" if target is not owner else "while_owned"
    if kind=="grant_move":
        import move_state as MOVES_STATE
        MOVES_STATE.preflight_move_grants(target,moves,key,"feature",dict(owner_id=owner.spec.get("id"),lifetime=lifetime,rule_id=rule_id,tutor_points=0))
    row=_source(target,key,"feature",owner_id=owner.spec.get("id"),lifetime=lifetime,rule_id=rule_id,tutor_points=0)
    part=key+":"+str(index)
    parts=row.setdefault("effect_sources",[])
    if part in parts:return False
    kind=effect.get("type")
    if kind=="grant_ability":
        grant(target,"abilities",ability,key,"feature",owner_id=owner.spec.get("id"),lifetime=lifetime,rule_id=rule_id)
        e.register_abilities_one(target,ability)
    elif kind=="grant_move":
        grant_moves(target,moves,key,"feature",owner_id=owner.spec.get("id"),lifetime=lifetime,rule_id=rule_id)
    elif kind=="grant_capability":
        for value in capabilities:grant(target,"capabilities",value,key,"feature",owner_id=owner.spec.get("id"),lifetime=lifetime,rule_id=rule_id)
    elif kind in ("status_immunity","keyword_immunity","weather_immunity"):
        import re
        field,label={"status_immunity":("status_immune","status"),"keyword_immunity":("keyword_immune","keyword"),"weather_immunity":("weather_immune","weather")}[kind]
        values=effect.get(label)
        values=values if isinstance(values,list) else re.split(r"[/,]",str(values or ""))
        for value in values:set_member(target,field,_text(value.strip(),label),part)
    elif kind=="immunity" and effect.get("status"):
        for value in effect["status"]:set_member(target,"status_immune",value,part)
    elif kind=="save_mod" and isinstance(effect.get("value"),int):
        numeric(target,"save_mod",effect["value"],part)
    elif kind=="initiative_mod" and isinstance(effect.get("value"),int):
        numeric(target,"initiative_bonus",effect["value"],part)
    elif kind=="crit_range":
        apply_owned(e,target,part,lambda:target.modifiers.append(effect))
    elif FX.passive_supported(effect) and not effect.get("if") and not effect.get("duration") and not effect.get("while"):
        apply_owned(e,target,part,lambda:FX.apply_passives(e,target,[effect]),effects=[effect])
    else:
        apply_owned(e,target,part,lambda:target.registry.append(effect))
    parts.append(part)
    return True


def assign_numeric(c,field,value):
    row=c.spec.get(KEY,{}).get("numbers",{}).get(field)
    if row is None:return False
    _sync_number(c,field,row)
    desired=_bounded(value,row["bounds"])
    row["base"]=desired-sum(row["sources"].values())
    _render_number(c,field,row)
    return True


def reset_numeric(c,field):
    row=c.spec.get(KEY,{}).get("numbers",{}).get(field)
    if row is None:return False
    row["base"]=0
    _render_number(c,field,row)
    marker="_passive_acc" if field=="accuracy_stage" else "_passive_eva"
    if field in ("accuracy_stage","evasion_mod"):setattr(c,marker,_get(c,field))
    return True


def _transition_token_anchors(engine):
    """Keep only issued native receipt/grant keys live across in-process staging.

    A caller may still hold these opaque identities while its effect mutates the
    state graph. This is not a save/load authority adapter and must not preserve
    arbitrary objects discovered in specs or user-provided dictionaries.
    """
    anchors={}
    for field in ("_effect_dispatch_receipts","_heavy_native_receipts","_heavy_standard_receipts"):
        ledger=getattr(engine,field,{})
        if not isinstance(ledger,dict):raise ValueError("native receipt ledger must be a mapping: "+field)
        for token,row in ledger.items():
            if type(token) is not object:continue
            if not isinstance(row,dict):raise ValueError("native receipt record must be a mapping")
            if field=="_effect_dispatch_receipts" and row.get("receipt") is not token:
                raise ValueError("native effect receipt identity disagrees with its ledger")
            anchors[id(token)]=token
    for entry in getattr(engine,"_action_grants",[]):
        if isinstance(entry,tuple) and entry and type(entry[0]) is object:
            anchors[id(entry[0])]=entry[0]
    # These exact native immutable observations contain only integer/tuple data.
    # Do not anchor SkillEvent itself: it contains actor references and must stage.
    import skill_feature_actions as SKILL_EVENTS
    import common_checks as CHECKS
    for record in getattr(engine,"_ap_rolls",{}).values():
        event=record.get("skill_event") if isinstance(record,dict) else None
        if type(event) is not SKILL_EVENTS.SkillEvent:continue
        for observed in (event.first,event.final):
            if type(observed) not in (CHECKS.SkillRoll,CHECKS.AdjustedSkillRoll):continue
            values=vars(observed).values()
            if not all(value is None or type(value) is int or (type(value) is tuple and all(type(face) is int for face in value)) for value in values):
                raise ValueError("native immutable skill observation contains unsupported mutable data")
            anchors[id(observed)]=observed
    return anchors


def _stage_transition_payload(engine,staged_engine,payload):
    """Copy one native invocation graph into its already-staged actor world.

    Actor references follow the original-to-staged index; only existing issued
    token anchors stay live. Keep the whole payload together to retain aliases
    between positional collections and options. This does not admit authority.
    """
    import world_entities as WORLD
    staged_actors=WORLD.actor_index(staged_engine)
    memo={id(actor):staged_actors[uid] for uid,actor in WORLD.actor_index(engine).items()}
    memo.update(_transition_token_anchors(engine))
    # Registered precision observations are native identity-bearing records,
    # including when a resumed accuracy tail enters a new atomic graph.
    staged_events={event['id']:event for event in getattr(staged_engine,'_precision_events',())}
    for event in getattr(engine,'_precision_events',()):
        staged=staged_events.get(event['id'])
        if staged is None:raise ValueError('native precision observation missing from staged world')
        if any(staged[key]!=event[key] for key in ('id','round','kind','source')):
            raise ValueError('native precision observation identity changed during staging')
        memo[id(event)]=staged
    issued_aliases=None
    for original, staged, aliases in reversed(_TRANSITION_MOVE_ALIASES.get()):
        if original is engine and staged is staged_engine:
            issued_aliases=aliases
            break
    if issued_aliases is not None:
        # These aliases came from the actual validated deepcopy graph.
        memo.update(issued_aliases)
    else:
        # Join issued groups to their existing staged counterparts, including a
        # resumed recipient that starts a new atomic move transaction. Look-alike
        # caller dictionaries are not keys in this memo and still get copied.
        source_scopes=getattr(engine,'_move_activation_scopes',())
        staged_scopes=getattr(staged_engine,'_move_activation_scopes',())
        if len(source_scopes)!=len(staged_scopes):raise ValueError('staged native group stack changed')
        for scope,staged in zip(source_scopes,staged_scopes):
            if (staged['actor'] is not staged_actors[scope['actor'].entity_id] or
                    any(scope.get(key)!=staged.get(key) for key in ('move_id','index','completion_id','profile')) or
                    tuple(staged['targets'])!=tuple(staged_actors[a.entity_id] for a in scope['targets'])):
                raise ValueError('staged native group identity changed')
            for field in ('activation','accuracy'):
                value=scope.get(field)
                if value is not None:memo[id(value)]=staged[field]
    return deepcopy(payload,memo)


def record_native_pending(engine, error, pending):
    """Keep only exact, registered native waits across a committed transition."""
    import passive_events as PASSIVE
    import heavy_injury_adapter as HEAVY
    if (type(error) is PASSIVE.PassiveEventPending and
            engine._passive_pending == error.event_id and error.event_id in engine._passive_events):
        pending.append((PASSIVE.PassiveEventPending, error.event_id))
        return True
    if (type(error) is HEAVY.HeavyPending and
            engine._heavy_pending == error.event_id and error.event_id in engine._heavy_events):
        pending.append((HEAVY.HeavyPending, error.event_id))
        return True
    return False


def transition(engine,c,apply,*,participants=(),include_rulings=False,include_grid=False,completion=None):
    # Native equipment can publish derived Move definitions into shared Rules.
    # Keep those publications inside the same outer failure boundary as the graph.
    from ruleset import generated_weapon_transaction
    with generated_weapon_transaction(engine.r):
        return _transition(engine,c,apply,participants=participants,include_rulings=include_rulings,
                           include_grid=include_grid,completion=completion)


def _transition(engine,c,apply,*,participants=(),include_rulings=False,include_grid=False,completion=None):
    """Stage a state graph; preserve actors and surviving mutable-container aliases.

    A None primary permits world-only transitions such as an empty-world clock.
    Explicit participants must still be real native actors.
    An optional native completion reports the reconciled candidate before its
    final validation and commit, using the same staged subjects as apply.
    """
    import gm_state
    import world_entities as WORLD
    stateful_rng=callable(getattr(engine.rng,'getstate',None)) and callable(getattr(engine.rng,'setstate',None))
    if not stateful_rng and not hasattr(engine.rng,'__dict__'):
        raise TypeError('RNG must expose getstate/setstate or mutable object state')
    participants=tuple(participants)
    subjects=participants if c is None else (c,*participants)
    actors={id(actor):actor for actor in WORLD.actor_index(engine,extra=subjects).values()}
    if any(id(actor) not in actors for actor in subjects):
        raise ValueError('native state transition requires actual combatant subjects')
    WORLD.entity_index(engine, extra=subjects)
    fields=set(gm_state.ENGINE_FIELDS)|{"log_lines","gm_prompts"}
    # Preserve an existing move stack even when it becomes empty during delivery.
    if hasattr(engine,'_move_activation_scopes'):fields.add('_move_activation_scopes')
    if getattr(engine,'_setup_move_scopes',()):fields.add('_setup_move_scopes')
    # Keep original container identities before staging. These include spec,
    # runtime registries and aliases reached through different actor/engine paths.
    originals={}
    def collect(value):
        if id(value) in originals:return
        if isinstance(value,(dict,list,set,tuple)):
            originals[id(value)]=value
            if isinstance(value,dict):
                for key,child in value.items():collect(key);collect(child)
            else:
                for child in value:collect(child)
    for actor in actors.values():collect(vars(actor))
    if not stateful_rng:collect(vars(engine.rng))
    collect(engine.gm.everyone)
    for field in fields:
        if hasattr(engine,field):collect(getattr(engine,field))
    if include_rulings:collect(vars(engine.rulings))
    if include_grid:
        if engine.grid is None:raise ValueError('grid transition requires an actual map')
        collect(vars(engine.grid))
    token_anchors=_transition_token_anchors(engine)
    memo={id(engine.r):engine.r,**token_anchors}
    if include_rulings:
        # Rules data stays shared; only mutable adjudications belong to this commit.
        from copy import copy
        staged_rules=copy(engine.r)
        memo[id(engine.r)]=staged_rules
        staged_rules.rulings=deepcopy(engine.rulings,memo)
    staged_engine=deepcopy(engine,memo);staged_c=deepcopy(c,memo)
    staged_actors={key:deepcopy(actor,memo) for key,actor in actors.items()}
    staged_participants=[deepcopy(actor,memo) for actor in participants]
    sync_capability_losses(staged_engine)
    before_prompts=len(staged_engine.gm_prompts)
    import event_trace as TRACE
    # Only the actual deepcopy graph can identify a native group's staged
    # dictionaries. Matching contents or external IDs cannot issue authority.
    move_aliases={}
    staged_scopes=getattr(staged_engine,"_move_activation_scopes",())
    for scope in getattr(engine,"_move_activation_scopes",()):
        copied_scope=memo.get(id(scope))
        if not any(copied_scope is actual for actual in staged_scopes):
            raise ValueError("native move scope missing from staged graph")
        for field in ("activation","accuracy"):
            value=scope.get(field)
            if value is None:continue
            copied=memo.get(id(value))
            if type(value) is not dict or type(copied) is not dict or copied_scope.get(field) is not copied:
                raise ValueError("native move group alias changed during graph staging")
            move_aliases[id(value)]=copied
    context=_TRANSITION_MOVE_ALIASES.set((*_TRANSITION_MOVE_ALIASES.get(),
                                        (engine,staged_engine,move_aliases)))
    try:
        with TRACE.staged_scope(engine,staged_engine):
            result=apply(staged_engine,staged_c,*staged_participants)
    finally:
        _TRANSITION_MOVE_ALIASES.reset(context)
    import ranged_struggle as RANGED
    for original_key,staged_actor in staged_actors.items():
        import csv_item_capability_contracts as CSV_CAP
        CSV_CAP.sync_essence(staged_engine,staged_actor)
        import ability_mastery as ABILITY_MASTERY
        ABILITY_MASTERY.reconcile(staged_engine,staged_actor,reason='completed native state transition')
        import advanced_connection as CONNECTION
        CONNECTION.reconcile(staged_actor,reason='completed native state transition',engine=staged_engine,before=actors[original_key])
        import capability_parameter_edges as PARAMETERS
        PARAMETERS.reconcile(staged_actor,reason='completed native state transition',engine=staged_engine)
        RANGED.reconcile(staged_actor,reason='completed native state transition')
        import tk_mastery as TK_MASTERY
        TK_MASTERY.reconcile(staged_actor,reason='completed native state transition')
        import underdog_edges as UNDERDOG
        UNDERDOG.reconcile(staged_engine,staged_actor,reason='completed native state transition')
        import mixed_sweeper as MIXED
        MIXED.reconcile(staged_engine,staged_actor,reason='completed native state transition')
        __import__('pokemon_move_edges').reconcile_mixed(staged_engine,staged_actor,reason='completed native state transition')
        import underdog_lessons as LESSONS
        LESSONS.reconcile(staged_actor,reason='completed native state transition')
        import invisibility_edge as INVISIBILITY_EDGE
        INVISIBILITY_EDGE.reconcile(staged_engine,staged_actor)
    import composition_reconcile as COMPOSITION
    retention_cache={}
    while True:
        removed=[]
        for staged_actor in staged_actors.values():
            removed.extend(COMPOSITION.reconcile(staged_engine,staged_actor,cache=retention_cache)['removed'])
        if not removed:break
    import form_allocations as FORMS
    for staged_actor in staged_actors.values():
        if FORMS.KEY in staged_actor.spec:FORMS.project(staged_actor)
    import effect_lifetime_policy as LIFETIMES
    LIFETIMES.reconcile(staged_engine)
    if completion is not None:completion(staged_engine,staged_c,*staged_participants)
    __import__('ability_exchange_contracts').refresh(staged_engine)
    __import__('ability_control_contracts').refresh(staged_engine)
    if len(staged_engine.gm_prompts)!=before_prompts:
        raise ValueError("state transition needs unresolved source input before commit")
    # Validate the resulting current world before exposing any staged mutation.
    # Historical snapshots are not live participants and are excluded by WORLD.
    import iron_mind as IRON_MIND
    import throwing_masteries as THROWING
    import wallrunner as WALL
    import stamina as STAMINA
    for staged_actor in staged_actors.values():
        IRON_MIND.validate(staged_actor);THROWING.validate(staged_actor);WALL.validate(staged_actor);STAMINA.validate(staged_actor)
    WORLD.entity_index(staged_engine,extra=tuple(staged_actors.values()))
    if hasattr(staged_engine,'_burrow_tunnels'):
        import burrow_tunnels as TUNNELS
        TUNNELS.validate(staged_engine)
    if include_grid:
        import map_terrain as TERRAIN
        TERRAIN.validate(staged_engine.grid)
    if any(WORLD.actor_id(staged)!=WORLD.actor_id(actors[key]) for key,staged in staged_actors.items()):
        raise ValueError('state transition cannot replace an existing actor identity')
    payload={"actors":{key:vars(actor) for key,actor in staged_actors.items()},"gm_everyone":staged_engine.gm.everyone,
             "engine":{key:getattr(staged_engine,key) for key in fields if hasattr(staged_engine,key)},"result":result}
    anchors={id(staged_engine):engine,id(engine.r):engine.r,**token_anchors,
             **{id(staged):actors[key] for key,staged in staged_actors.items()}}
    if not stateful_rng:
        payload['rng']=vars(staged_engine.rng)
        anchors[id(staged_engine.rng)]=engine.rng
        anchors[id(vars(staged_engine.rng))]=vars(engine.rng)
    if include_rulings:
        payload['rulings']=vars(staged_engine.rulings)
        anchors[id(staged_engine.r)]=engine.r
        anchors[id(staged_engine.rulings)]=engine.rulings
        anchors[id(vars(staged_engine.rulings))]=vars(engine.rulings)
    if include_grid:
        payload['grid']=vars(staged_engine.grid)
        anchors[id(staged_engine.grid)]=engine.grid
        anchors[id(vars(staged_engine.grid))]=vars(engine.grid)
    for key,original in originals.items():
        staged=memo.get(key)
        if staged is not None and isinstance(original,(dict,list,set)):
            anchors[id(staged)]=original
    # A transition may replace a top-level field dictionary/list. Retain the
    # original public container when it has not acquired another graph identity.
    replacements=[]
    for key,staged in staged_actors.items():
        original=actors[key]
        anchors[id(vars(staged))]=vars(original)
        for field,value in vars(staged).items():
            previous=getattr(original,field,None)
            if type(value) is type(previous) and isinstance(value,(dict,list,set)):
                replacements.append((value,previous))
    from resolution_transaction import commit_graph
    committed=commit_graph(payload,anchors,replacements)
    engine.gm.everyone=committed["gm_everyone"]
    for key in fields-committed["engine"].keys():vars(engine).pop(key,None)
    for key,value in committed["engine"].items():setattr(engine,key,value)
    if include_grid:engine.grid.__dict__=committed['grid']
    if stateful_rng:engine.rng.setstate(staged_engine.rng.getstate())
    return committed["result"]


def replace_baseline(engine,c,field,values):
    """Atomic permanent-list transition including every passive registration."""
    def apply(staged_engine,staged_c):
        before=list(staged_c.spec.get(field,[]))
        if field=='moves':
            import ace_trainer as ACE
            # Only this native permanent-list transition can forget a Move;
            # overlays and codec restore never refund an investment.
            proposed=deepcopy(staged_c.spec);proposed[field]=list(values)
            legacy=proposed.get(KEY,{}).get('legacy',{})
            legacy[field]=[v for v in legacy.get(field,[]) if v not in values and v not in before]
            retained=ACE._known(staged_c.r,proposed)
            for row in ACE._history(staged_c.spec):
                if row['status']=='active' and row['move_id'] not in retained:
                    ACE.forget_spec(staged_c.r,staged_c.spec,row['move_id'],at=staged_engine.elapsed_seconds,reason='actual permanent Move forgetting')
        set_baseline(staged_c,field,values)
        reconcile(staged_engine,staged_c)
        return {"field":field,"before":before,"after":list(staged_c.spec[field])}
    return transition(engine,c,apply)
