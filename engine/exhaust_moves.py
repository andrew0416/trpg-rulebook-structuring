"""Source-owned next-turn action debt for the Exhaust Move keyword.

The pending loss remains a resource debt, not an action history entry.  This
module owns only the Exhaust producer and its command lock; ordinary debt
settlement stays in :mod:`action_resources`.
"""
from copy import deepcopy
import common_checks as CHECKS

KEY = "exhaust_action_debt"
SOURCE = "input/ch10-index-reference.md:317"
DEBT = {"standard": 1, "swift": 1}

def _policies(rules):
    import json
    from pathlib import Path
    from source_context import verified_source
    value=json.loads((Path(rules.root)/'data/exhaust-vortex-source-policy.json').read_text(encoding='utf-8'))
    if value.get('schema_version')!=1:
        raise ValueError('known Exhaust/Vortex source policy required')
    value=value['rules']['exhaust']
    if value['source']!='keyword/탈진':
        raise ValueError('exact exhaust keyword required')
    verified_source(rules,value['source_reference'],label='exhaust policy')
    for definition in value['definitions'].values():
        reference=definition['source']
        verified_source(rules,reference,label='exhaust definition',
                        source_root='source-audit' if reference['file'].startswith('source-audit/') else 'input')
    return value


def _document(value):
    return {'schema':1,'id':'native/exhaust-source','variants':[{
        'rule_id':value['source'],'source':value['source_reference'],
        'values':{'variant':{'$input':'source_text'},'definitions':value['definitions']},
        'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
            'choices':list(value['definitions']),'question':value['question']}}}]}


def source_choices(actor):
    import source_policy as POLICY
    return POLICY.resolve(actor.r,_document(_policies(actor.r)))


def _selected_policy(actor):
    import source_policy as POLICY
    value=_policies(actor.r);choice=actor.spec.get('exhaust_source_choice')
    result=POLICY.resolve(actor.r,_document(value),
                          decisions={} if choice is None else {'source_text':choice})
    variant=value['default'] if choice is None else result['values']['variant']
    return variant,deepcopy(value['definitions'][variant]['policy']),deepcopy(choice)


def select_source(engine,actor,choice):
    import world_entities as WORLD,state_grants as G,action_lifecycle as ACTION
    WORLD.require_actors(engine,actor)
    ACTION.ensure_resolutions_clear(engine)
    if choice is None:raise ValueError('actual scoped exhaust source decision required')
    def apply(e,c):
        import source_policy as POLICY
        result=POLICY.resolve(e.r,_document(_policies(e.r)),decisions={'source_text':choice})
        if result['status']!='PolicyValuesReady':raise ValueError('actual exhaust source decision required')
        c.spec['exhaust_source_choice']=deepcopy(choice)
        return deepcopy(choice)
    return G.transition(engine,actor,apply,include_rulings=True)


def _recorded_policy(actor,row):
    fields={'policy_variant','source_choice','debt'}
    if not fields&set(row):
        return deepcopy(DEBT)
    if not fields<=set(row):raise ValueError('complete producing exhaust policy required')
    value=_policies(actor.r);variant=row['policy_variant'];choice=row['source_choice']
    if variant not in value['definitions'] or row['debt']!=value['definitions'][variant]['policy']:
        raise ValueError('original complete exhaust definition required')
    if choice is None:
        if variant!='korean_standard_swift':
            raise ValueError('nondefault exhaust needs its actual source decision')
    else:
        import root_resolution as ROOT
        scope=choice.get('scope') if type(choice)is dict else None
        if (type(choice)is not dict or set(choice)!={'value','reason','scope'}
            or choice['value']!=variant or type(choice['reason'])is not str or not choice['reason'].strip()
            or type(scope)is not dict or set(scope)!={'policy_id','selected_id','selected_version','definition_hash','profile_hash'}
            or scope['policy_id']!='native/exhaust-source' or scope['selected_id']!=value['source']
            or scope['selected_version'] is not None or scope['definition_hash']!=ROOT.fingerprint(_document(value))
            or type(scope['profile_hash'])is not str or not scope['profile_hash'].strip()):
            raise ValueError('original scoped exhaust source decision required')
    # Producing scope is history. Current future profile choices cannot rewrite it.
    return deepcopy(row['debt'])


def applies(move):
    return "탈진" in move.get("keywords", ())


def record(actor):
    return actor.spec.get(KEY)


def validate(actor):
    row = record(actor)
    if row is None:
        return True
    required = {"source", "actor_id", "move_id", "issued_turn", "due_turn", "phase"}
    if type(row) is not dict or set(row) not in (required, required | {"policy_variant", "source_choice", "debt"}):
        raise ValueError("Exhaust debt requires one exact source-owned record")
    debt = _recorded_policy(actor, row)
    if (row["source"] != SOURCE or row["actor_id"] != actor.entity_id
            or type(row["move_id"]) is not str or not row["move_id"].startswith("move/")
            or row["phase"] not in ("pending", "active")):
        raise ValueError("Exhaust debt source, actor, Move or phase is invalid")
    issued = CHECKS.integer(row["issued_turn"], "Exhaust issuing owner turn", 0)
    due = CHECKS.integer(row["due_turn"], "Exhaust due owner turn", 1)
    if due != issued + 1:
        raise ValueError("Exhaust debt must belong to the user's next actual turn")
    serial = CHECKS.integer(actor.custom_conditions.get("combat_turn_serial", 0),
                            "actual owner turn serial", 0)
    pending = getattr(actor, "pending_action_loss", None)
    if row["phase"] == "pending":
        # combat_timing advances the actual owner clock before the shared
        # budget reset pays this debt, so both sides of that one boundary are
        # valid while the loss is still physically pending.
        if serial not in (issued, due) or pending != debt:
            raise ValueError("pending Exhaust debt disagrees with its action loss")
    elif serial != due or pending is not None:
        raise ValueError("active Exhaust debt must own exactly its due turn")
    return True


def preflight(engine, actor, move, *, count_use):
    """Reject before action/frequency/RNG if this activation cannot own its debt."""
    if not applies(move) or not count_use:
        return True
    if record(actor) is not None or getattr(actor, "pending_action_loss", None) is not None:
        raise ValueError("Exhaust cannot overlap another pending next-action loss")
    _, debt, _ = _selected_policy(actor)
    budget = getattr(actor, "budget", None)
    if budget is not None:
        if type(budget) is not dict or any(type(budget.get(k)) is not int for k in debt):
            raise ValueError("Exhaust requires the actual action budget")
        if any(budget[key] <= 0 for key in debt):
            engine.log(f"    {actor.name}: 탈진에 필요한 {debt} 행동을 이미 소비함 → 기술 실패", SOURCE)
            return False
    return True


def commit(engine, actor, move, *, count_use):
    """Schedule once, after the Move has become an actual native activation."""
    if not applies(move) or not count_use:
        return None
    if record(actor) is not None or getattr(actor, "pending_action_loss", None) is not None:
        raise ValueError("Exhaust activation lost its preflighted debt boundary")
    import action_resources as RESOURCES
    variant, debt, choice = _selected_policy(actor)
    RESOURCES.schedule(actor, debt)
    issued = CHECKS.integer(actor.custom_conditions.get("combat_turn_serial", 0),
                            "Exhaust issuing owner turn", 0)
    row = {"source": SOURCE, "actor_id": actor.entity_id, "move_id": move["id"],
           "issued_turn": issued, "due_turn": issued + 1, "phase": "pending",
           "policy_variant": variant, "source_choice": choice, "debt": debt}
    actor.spec[KEY] = row
    validate(actor)
    engine.log(f"    {actor.name}: {move['name']} 탈진 부채 예약 (다음 자기 턴 {debt}/명령)", SOURCE)
    return deepcopy(row)


def settle(engine, actor, owed):
    """Called by the shared budget reset after the ordinary debt is paid."""
    row = record(actor)
    if row is None:
        return None
    if row["phase"] != "pending" or owed != _recorded_policy(actor, row):
        raise ValueError("Exhaust settlement disagrees with the shared action debt")
    serial = CHECKS.integer(actor.custom_conditions.get("combat_turn_serial", 0),
                            "Exhaust settlement owner turn", 0)
    if serial != row["due_turn"]:
        raise ValueError("Exhaust debt can settle only at the next actual owner turn")
    row["phase"] = "active"
    validate(actor)
    engine.log(f"    {actor.name}: 탈진으로 이번 턴 {owed} 행동과 트레이너 명령 상실", SOURCE)
    return deepcopy(row)


def require_command(engine, pokemon):
    """The explicit trainer-command producer, without forbidding autonomous acts."""
    row = record(pokemon)
    if row is None:
        return True
    validate(pokemon)
    if row["phase"] == "active":
        raise ValueError("Exhaust prevents this Pokemon from receiving a trainer command this turn")
    return True


def end_turn(engine, actor):
    row = record(actor)
    if row is None:
        return
    validate(actor)
    if row["phase"] == "active":
        actor.spec.pop(KEY)
        engine.log(f"    {actor.name}: 탈진 행동/명령 부채 종료", SOURCE)


def end_encounter(actor):
    actor.spec.pop(KEY, None)
