"""Source-backed temporary-HP lifetime, separate from ordinary healing.

Ordinary grants expire after five minutes outside combat, per the original
PTU1.05 text. Actual combat participation pauses that timer. Explicit GM wall-clock overrides remain
separate, and old rule records without a clock basis need reconciliation.
"""
import common_checks as CHECKS
from copy import deepcopy
from pathlib import Path
import hashlib,json

STATE = "temporary_hp_lifetime"
CLOCK = "out_of_combat_seconds"
LOSS_MODES = ('temp_first', 'bypass')


def loss_policy(engine):
    """Defensive view of the persistent GM interpretation for unpreventable loss."""
    from copy import deepcopy
    row = getattr(engine, '_hp_loss_policy', None)
    if row is None:
        return {'mode': 'temp_first', 'reason': 'user-adopted project default'}
    if (type(row) is not dict or set(row) != {'mode', 'reason'}
            or row['mode'] not in LOSS_MODES or type(row['mode']) is not str
            or type(row['reason']) is not str or not row['reason'].strip()):
        raise ValueError('HP loss policy requires temp_first/bypass and a reason')
    return deepcopy(row)


def configure_loss_policy(engine, mode, *, reason):
    if (type(mode) is not str or mode not in LOSS_MODES
            or type(reason) is not str or not reason.strip()):
        raise ValueError('HP loss policy requires temp_first/bypass and a reason')
    engine._hp_loss_policy = {'mode': mode, 'reason': reason.strip()}
    return loss_policy(engine)


def loss_remainder(engine, actor, amount, *, unpreventable=False):
    """Allocate a loss without changing its amount or granting damage reactions.

    Unpreventable always bypasses damage caps at the producer. Its temporary-HP
    allocation follows the persistent GM choice; HP-setting adapters do not call
    this function. Pain Split reuses it while retaining its no-injury contract.
    """
    CHECKS.integer(amount, 'HP loss', 0)
    if type(unpreventable) is not bool:
        raise ValueError('unpreventable must be an explicit boolean')
    choice = loss_policy(engine)
    if unpreventable and choice['mode'] == 'bypass':
        ensure_certain(engine, actor)
        return amount
    return absorb(engine, actor, amount)


def policy(rules):
    row=getattr(rules,"_temporary_hp_policy",None)
    if row is None:
        row=json.loads((Path(rules.root)/"data/temporary-hp-policy.json").read_text(encoding="utf-8"))
        for file,digest in row["source_files"].items():
            if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError("temporary HP source changed: "+file)
        if row["clock_basis"]!=CLOCK or row["duration_seconds"]!=300:raise ValueError("unsupported temporary HP timer policy")
        rules._temporary_hp_policy=row
    return row



SOURCE_RULES = {'chef_hits': 'feat/이-맛이야', 'chef_taste': 'feat/특색있는-맛',
                'lunchbox': 'ability/도시락통-playtest'}
COMPOSITION_MODES = {'allocation': ('fifo', 'lifo'),
                     'additive_lifetime': ('per_grant', 'refresh_pool')}


def composition_policy(engine, name):
    """Use the existing GM answer boundary; defaults are project choices, not printed rules."""
    answer = engine.rulings.decide({'type': 'temporary_hp_' + name,
        'unit': 'condition/임시-체력', 'text': 'Temporary HP ' + name})
    row = deepcopy(policy(engine.r).get('composition', {}).get(name) if answer is None else answer)
    if row is None:
        raise ValueError('temporary HP ' + name + ' needs an explicit GM policy')
    if (not isinstance(row, dict) or set(row) != {'mode', 'reason', 'scope'}
            or row['mode'] not in COMPOSITION_MODES[name]
            or not isinstance(row['reason'], str) or not row['reason'].strip()
            or row['scope'] not in ('scene', 'campaign')):
        raise ValueError('temporary HP ' + name + ' requires mode, reason and scene/campaign scope')
    return row


def _validate_source(actor, source):
    if source is None:
        return
    if not isinstance(source, dict) or set(source) != {'kind', 'rule_id', 'receipt_sequence', 'buff_id'}:
        raise ValueError('typed temporary HP contribution source required')
    kind = source['kind']
    if kind not in (*SOURCE_RULES, 'food'):
        raise ValueError('unsupported temporary HP contribution source')
    sequence = CHECKS.integer(source['receipt_sequence'], 'temporary HP food receipt sequence', 1)
    receipts = actor.spec.get('food_consumption_receipts', [])
    if not isinstance(receipts, list) or sequence > len(receipts):
        raise ValueError('temporary HP source needs its actual food receipt')
    receipt = receipts[sequence - 1]
    if (not isinstance(receipt, dict) or receipt.get('sequence') != sequence
            or receipt.get('buff_id') != source['buff_id']):
        raise ValueError('temporary HP source food receipt mismatch')
    expected = receipt.get('item') if kind == 'food' else SOURCE_RULES[kind]
    if not isinstance(source['buff_id'], str) or not source['buff_id'] or not isinstance(expected, str) or not expected:
        raise ValueError('temporary HP source needs actual buff and rule identities')
    if source['rule_id'] != expected:
        raise ValueError('temporary HP contribution rule mismatch')
    if kind == 'food' and (not isinstance(receipt.get('benefit'), dict) or receipt['benefit'].get('kind') != 'temporary_hp'):
        raise ValueError('temporary HP Food source did not grant this benefit')
    if kind == 'chef_taste' and (not isinstance(receipt.get('taste_assignment'), dict)
            or receipt['taste_assignment'].get('taste') != '짠맛'
            or receipt['taste_assignment'].get('source') != SOURCE_RULES['chef_taste']):
        raise ValueError('temporary HP taste source needs actual assigned Salty taste')


def food_source(actor, kind, receipt):
    """Bind a native grant to the actual consumption, including an in-progress trade-in."""
    if not isinstance(receipt, dict):
        raise ValueError('actual temporary HP food receipt required')
    source = {'kind': kind, 'rule_id': receipt.get('item') if kind == 'food' else SOURCE_RULES.get(kind),
              'receipt_sequence': receipt.get('sequence'), 'buff_id': receipt.get('buff_id')}
    _validate_source(actor, source)
    if actor.spec['food_consumption_receipts'][source['receipt_sequence'] - 1] is not receipt:
        raise ValueError('actual temporary HP food receipt identity required')
    return source


def _compatible(rules, first, second):
    if first is None or second is None:
        return False
    for row in policy(rules)['composition']['source_pairs']:
        if sorted((first['kind'], second['kind'])) == sorted(row['kinds']):
            return not row.get('same_receipt', False) or first['receipt_sequence'] == second['receipt_sequence']
    return False


def blocked_reason(actor):
    """A prohibited grant is different from a successful max merge with zero increase."""
    import actor_templates as TEMPLATES
    import food_effects as FOOD
    import healing_blocks as HEALING_BLOCKS
    if TEMPLATES.soulless(actor):
        return 'soulless'
    if not FOOD.temp_hp_allowed(actor):
        return 'temporary_hp_restriction'
    if HEALING_BLOCKS.blocked(actor):
        return 'healing_block'
    return None


def _sync_contributions(actor):
    state = actor.custom_conditions[STATE]
    rows = state['contributions']
    actor.temp_hp = sum(row['amount'] for row in rows)
    if not rows:
        actor.custom_conditions.pop(STATE, None)
        return
    state['minimum_seconds'] = min(row['minimum_seconds'] for row in rows)
    state['maximum_seconds'] = max(row['maximum_seconds'] for row in rows)
    if any(row.get('unknown_elapsed', False) for row in rows):
        state['unknown_elapsed'] = True
    else:
        state.pop('unknown_elapsed', None)


def _validate_contributions(actor, state):
    rows = state.get('contributions')
    if rows is None:
        return  # Old event amounts are history, not evidence of surviving source balances.
    if state['kind'] != 'rule_grant' or state.get('clock_basis') != CLOCK or not isinstance(rows, list) or not rows:
        raise ValueError('invalid temporary HP contributions')
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'unknown_elapsed'} != {'amount', 'source', 'minimum_seconds', 'maximum_seconds'}:
            raise ValueError('invalid temporary HP contribution')
        CHECKS.integer(row.get('amount'), 'temporary HP contribution balance', 1)
        _validate_source(actor, row.get('source'))
        low = CHECKS.integer(row.get('minimum_seconds'), 'temporary HP contribution earliest expiry')
        high = CHECKS.integer(row.get('maximum_seconds'), 'temporary HP contribution latest expiry', 0)
        if low > high or type(row.get('unknown_elapsed', False)) is not bool or (low != high and row.get('unknown_elapsed') is not True):
            raise ValueError('temporary HP contribution expiry bounds disagree')
    if any(not _compatible(actor.r, first['source'], second['source'])
           for index, first in enumerate(rows) for second in rows[index + 1:]):
        raise ValueError('unsupported temporary HP source combination')
    if sum(row['amount'] for row in rows) != actor.temp_hp:
        raise ValueError('temporary HP contribution balances disagree with scalar total')
    if (state.get('minimum_seconds') != min(row['minimum_seconds'] for row in rows)
            or state.get('maximum_seconds') != max(row['maximum_seconds'] for row in rows)):
        raise ValueError('temporary HP contribution expiry projection disagrees')
    choices = state.get('composition_policies', {})
    if not isinstance(choices, dict):
        raise ValueError('temporary HP composition policies must be a mapping')
    for name, choice in choices.items():
        if name not in COMPOSITION_MODES or not isinstance(choice, dict) or set(choice) != {'mode', 'reason', 'scope'}:
            raise ValueError('invalid saved temporary HP composition policy')
        if choice['mode'] not in COMPOSITION_MODES[name] or not isinstance(choice['reason'], str) or not choice['reason'].strip() or choice['scope'] not in ('scene', 'campaign'):
            raise ValueError('invalid saved temporary HP composition choice')


def validate(actor):
    """Validate shared balance/lifetime without inventing an imported timestamp."""
    CHECKS.integer(actor.temp_hp, "temporary HP", 0)
    state = actor.custom_conditions.get(STATE)
    if state is None:
        return
    if not isinstance(state, dict):
        raise ValueError("temporary HP lifetime must be a mapping")
    kind = state.get("kind")
    expected = {"rule_grant": "condition/임시-체력", "gm_override": "gm/state"}
    if kind not in expected or state.get("source") != expected[kind]:
        raise ValueError("temporary HP lifetime source mismatch")
    _validate_contributions(actor, state)
    events=state.get('grant_events',[])
    if not isinstance(events,list):raise ValueError('temporary HP grant events must be a list')
    for event in events:
        if not isinstance(event,dict) or set(event)!={'amount','stack','provenance','at','round'}:raise ValueError('invalid temporary HP grant provenance')
        CHECKS.integer(event['amount'],'temporary HP granted amount',1)
        if type(event['stack']) is not bool or not isinstance(event['provenance'],dict):raise ValueError('invalid temporary HP grant mode/provenance')
        CHECKS.integer(event['at'],'temporary HP grant time',0);CHECKS.integer(event['round'],'temporary HP grant round',0)
        try:json.dumps(event['provenance'],ensure_ascii=False)
        except (TypeError,ValueError) as exc:raise ValueError('temporary HP provenance must be JSON data') from exc
    if "expiry_policy" in state:
        if (kind != "gm_override" or state["expiry_policy"] != "explicit_unbounded"
                or "minimum_seconds" in state or "maximum_seconds" in state or "clock_basis" in state):
            raise ValueError("invalid temporary HP expiry policy")
        return
    low = CHECKS.integer(state.get("minimum_seconds"), "temporary HP earliest expiry")
    high = CHECKS.integer(state.get("maximum_seconds"), "temporary HP latest expiry", 0)
    if low > high:
        raise ValueError("temporary HP expiry bounds are reversed")
    basis=state.get("clock_basis")
    if basis is not None:
        if kind!="rule_grant" or basis!=policy(actor.r)["clock_basis"]:raise ValueError("temporary HP clock basis mismatch")
        if state.get("uncertain_birth",False) or state.get("out_of_combat_elapsed_unresolved",False):raise ValueError("outside-combat temporary HP clock cannot inherit a combat-time uncertainty")
        if "contributions" not in state and low!=high and state.get("unknown_elapsed") is not True:raise ValueError("outside-combat temporary HP expiry bounds need an observed unknown interval")
    birth = state.get("birth_round")
    if birth is not None:
        CHECKS.integer(birth, "temporary HP birth round", 0)
    for key in ("uncertain_birth", "unknown_elapsed", "out_of_combat_elapsed_unresolved"):
        if key in state and type(state[key]) is not bool:
            raise ValueError("temporary HP timing flags must be boolean")


def absorb(engine, actor, amount):
    """Spend the shared barrier once and return only the real-HP remainder.

    Callers resolve damage caps and source-specific bypasses before this step.
    Consuming the last point removes its lifetime as part of the same change.
    """
    CHECKS.integer(amount, "HP loss", 0)
    ensure_certain(engine, actor)
    used = min(actor.temp_hp, amount)
    if used:
        state = actor.custom_conditions.get(STATE, {})
        rows = state.get('contributions')
        if rows is not None:
            choice = composition_policy(engine, 'allocation') if len(rows) > 1 and used < actor.temp_hp else None
            remaining = used
            ordered = reversed(rows) if choice and choice['mode'] == 'lifo' else iter(rows)
            for row in ordered:
                consumed = min(row['amount'], remaining)
                row['amount'] -= consumed
                remaining -= consumed
                if not remaining:
                    break
            state['contributions'] = [row for row in rows if row['amount']]
            if choice:
                state.setdefault('composition_policies', {})['allocation'] = choice
            _sync_contributions(actor)
        else:
            actor.temp_hp -= used
            if actor.temp_hp == 0:
                actor.custom_conditions.pop(STATE, None)
        engine.log(f"    임시 체력이 {used} 흡수 (남은 임시 {actor.temp_hp})", "condition/임시-체력")
    return amount - used


def _policy(engine):
    if engine.r._selected_rule("condition/임시-체력") != "condition/임시-체력":
        raise ValueError("selected temporary HP variant requires its own lifetime policy")
    effects = engine.r.condition_effects("임시-체력")
    rule = next((e for e in effects if e.get("type") == "temp_hp_rules"), None)
    if not rule or set(rule.get("lost_on", [])) != {"recall", "5min"}:
        raise ValueError("unsupported temporary HP lifetime policy")
    return policy(engine.r)["duration_seconds"]


def clear(engine, actor, reason):
    before = actor.temp_hp
    actor.temp_hp = 0
    actor.custom_conditions.pop(STATE, None)
    if before:
        engine.log(f"    {actor.name} 임시 체력 {before} 소멸 ({reason})", "condition/임시-체력")


def _grant_composition(engine, before, state, value, contribution_source, duration):
    """Plan only an accepted increase; callers own source validation and mutation."""
    retained = [deepcopy(row) for row in state.get('contributions', [])
                if _compatible(engine.r, row['source'], contribution_source)]
    proposed = value + sum(row['amount'] for row in retained)
    import recovery_resolution as RECOVERY
    recovery = RECOVERY.resolve(before, proposed, resource='temp_hp', mode='at_least')
    if not value or not recovery['applied']:
        return None
    choices = deepcopy(state.get('composition_policies', {})) if retained else {}
    if retained and any(row['minimum_seconds'] != duration or row['maximum_seconds'] != duration for row in retained):
        choice = composition_policy(engine, 'additive_lifetime')
        choices['additive_lifetime'] = choice
        if choice['mode'] == 'refresh_pool':
            for row in retained:
                row.update(minimum_seconds=duration, maximum_seconds=duration)
                row.pop('unknown_elapsed', None)
    retained.append({'amount': value, 'source': deepcopy(contribution_source),
                     'minimum_seconds': duration, 'maximum_seconds': duration})
    return recovery, retained, choices


def preflight_food_grants(engine, actor, grants, *, plan=None):
    """Check ordered grants without consuming food or granting source rights.

    Tagged local keys cannot match existing receipt numbers or predict the next
    one; another hit consumer may consume a berry before this trade-in.
    """
    duration = _policy(engine)
    if blocked_reason(actor) in ('soulless', 'temporary_hp_restriction'):
        return
    ensure_certain(engine, actor)
    if blocked_reason(actor) is not None:
        return
    if plan is None:
        plan = {}
    if not plan:
        plan.update(total=actor.temp_hp, state=deepcopy(actor.custom_conditions.get(STATE, {})), trade_count=0)
    receipt_key = ('unconsumed_food', plan['trade_count'])
    plan['trade_count'] += 1
    for value, kind in grants:
        CHECKS.integer(value, 'temporary HP', 0)
        if kind not in ('food', 'chef_taste'):
            raise ValueError('Food/Taste temporary HP preflight kind required')
        source = {'kind': kind, 'receipt_sequence': receipt_key}
        result = _grant_composition(engine, plan['total'], plan['state'], value, source, duration)
        if result is not None:
            recovery, rows, choices = result
            plan.update(total=recovery['after'], state={'contributions': rows, 'composition_policies': choices})


def grant(engine, actor, value, *, round_offset_seconds=None, stack=False, provenance=None, contribution_source=None):
    CHECKS.integer(value, "temporary HP", 0)
    if type(stack) is not bool:
        raise ValueError('temporary HP stack mode must be boolean')
    if provenance is not None and not isinstance(provenance, dict):
        raise ValueError('temporary HP provenance must be a mapping')
    _validate_source(actor, contribution_source)
    if stack and contribution_source is None:
        raise ValueError('temporary HP stacking needs an explicit supported contribution source')
    duration = _policy(engine)
    if blocked_reason(actor) in ('soulless', 'temporary_hp_restriction'):
        return 0
    if round_offset_seconds is not None:
        engine.at_round_offset(round_offset_seconds)
    ensure_certain(engine, actor)
    if blocked_reason(actor) is not None:
        return 0
    before = actor.temp_hp
    state = actor.custom_conditions.get(STATE, {})
    result = _grant_composition(engine, before, state, value, contribution_source, duration)
    if result is None:
        return 0
    recovery, retained, choices = result
    lifetime = {'kind': 'rule_grant', 'source': 'condition/임시-체력', 'clock_basis': CLOCK,
                'minimum_seconds': duration, 'maximum_seconds': duration,
                'birth_round': engine.round_no if engine.round_start_seconds is not None else None,
                'uncertain_birth': False, 'contributions': retained}
    if choices:
        lifetime['composition_policies'] = choices
    prior = state.get('grant_events', [])
    if prior or provenance is not None:
        lifetime['grant_events'] = deepcopy(prior)
        if provenance is not None:
            lifetime['grant_events'].append({'amount': recovery['applied'], 'stack': stack,
                'provenance': deepcopy(provenance), 'at': engine.elapsed_seconds, 'round': engine.round_no})
    actor.custom_conditions[STATE] = lifetime
    _sync_contributions(actor)
    engine.time_actors([actor])
    engine.log(f"    {actor.name} 임시 체력 {actor.temp_hp}", "condition/임시-체력")
    return recovery['applied']


def advance(engine, actor, seconds):
    CHECKS.integer(seconds,"temporary HP elapsed seconds",0)
    validate(actor)
    state = actor.custom_conditions.get(STATE)
    if state is None or state.get("expiry_policy") == "explicit_unbounded":
        return
    if actor.temp_hp <= 0:
        actor.custom_conditions.pop(STATE, None)
        return
    if state.get("kind")=="rule_grant":
        if state.get("clock_basis")!=CLOCK:return  # preserve unreconciled legacy timing
        if engine.encounter_active:
            import combat_state_lifecycle as COMBAT
            if any(c is actor for c in COMBAT.members(engine)):return
    if 'contributions' in state:
        for row in state['contributions']:
            row['minimum_seconds'] -= seconds
            row['maximum_seconds'] -= seconds
        state['contributions'] = [row for row in state['contributions'] if row['maximum_seconds'] > 0]
        _sync_contributions(actor)
        return
    state["minimum_seconds"] -= seconds
    state["maximum_seconds"] -= seconds
    if state["maximum_seconds"] <= 0:
        clear(engine, actor, "5분 경과")


def unknown_interval(actor, maximum_seconds, *, outside_combat=False):
    CHECKS.integer(maximum_seconds,"unknown combat interval",0)
    validate(actor)
    state = actor.custom_conditions.get(STATE)
    if state and state.get("expiry_policy") != "explicit_unbounded" and actor.temp_hp > 0:
        if state.get("kind")=="rule_grant":
            # Preserve legacy records; actual outsiders still experienced this interval.
            if state.get("clock_basis")!=CLOCK or not outside_combat:return
        if 'contributions' in state:
            for row in state['contributions']:
                row['minimum_seconds'] -= maximum_seconds
                row['unknown_elapsed'] = True
            _sync_contributions(actor)
        else:
            state["minimum_seconds"] -= maximum_seconds
            state["unknown_elapsed"] = True


def ensure_certain(engine, actor):
    # Zero remains the public scalar clear boundary; it cannot retain stacking rights.
    if type(actor.temp_hp) is int and actor.temp_hp == 0:
        actor.custom_conditions.pop(STATE, None)
    validate(actor)
    state = actor.custom_conditions.get(STATE)
    if state is None and actor.temp_hp>0:
        raise ValueError("temporary HP expiry needs an origin/clock observation")
    if state is None or state.get("expiry_policy") == "explicit_unbounded" or actor.temp_hp <= 0:
        return
    if state.get("kind")=="rule_grant" and state.get("clock_basis")!=CLOCK:
        raise ValueError("temporary HP expiry needs legacy clock-basis reconciliation")
    if state["maximum_seconds"] <= 0:
        clear(engine, actor, "5분 경과")
    elif state["minimum_seconds"] <= 0:
        raise ValueError("temporary HP expiry needs the unresolved grant/elapsed timestamp")


def gm_set(engine, actor, value, *, duration_seconds=None, round_offset_seconds=None):
    """Explicit state override; never masquerades as a sourced ordinary grant."""
    CHECKS.integer(value, "GM temporary HP", 0)
    import actor_templates as TEMPLATES
    if value and TEMPLATES.soulless(actor):
        raise ValueError("Soulless requires a rule override before adding temporary HP")
    if duration_seconds is not None:
        CHECKS.integer(duration_seconds, "GM temporary HP duration", 0)
    if round_offset_seconds is not None:
        engine.at_round_offset(round_offset_seconds)
    if value == 0:
        clear(engine, actor, "GM 지정")
        return
    actor.temp_hp = value
    state = {"kind": "gm_override", "source": "gm/state"}
    if duration_seconds is None:
        state["expiry_policy"] = "explicit_unbounded"
    else:
        upper = duration_seconds
        if engine.round_start_seconds is not None and round_offset_seconds is None:
            upper += max(0, 10 - (engine.elapsed_seconds - engine.round_start_seconds))
        state.update(minimum_seconds=duration_seconds, maximum_seconds=upper)
    actor.custom_conditions[STATE] = state
    engine.time_actors([actor])
    if duration_seconds == 0:
        clear(engine, actor, "GM 만료 지정")
