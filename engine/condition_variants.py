"""C11-083's explicitly adopted venom on the existing native Poison family.

The actual inflictor owns the adoption; the poisoned holder owns its immutable
application. Ordinary condition flags, native stage changes and while-condition
lifetimes remain the consumers. No species name or global move is rewritten.
"""
from copy import deepcopy
from pathlib import Path
import json
import common_checks as C
import condition_instances as CI
import effect_instances as E
import combat_stage_sources as STAGES
import resolution_transaction as F

ADOPTION = 'alternate_poison_adoption'
CLAUSE = 'C11-083'
SOURCE = {'file': 'input/ch11-running-the-game.md',
          'sha256': '5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad'}
PAYLOAD = {'kind': 'condition_variant', 'condition': '독', 'variant': 'slowing_venom'}
SLOWED = {'type': 'apply_status', 'status': '둔화',
          'while': {'owner': 'target', 'condition': '독'}}


def policy(rules):
    from source_context import verified_source
    row = json.loads((Path(rules.root) / 'data/core-condition-variant-policy.json').read_text(encoding='utf-8'))
    expected = {'schema_version': 1, 'clause_id': CLAUSE, 'source': SOURCE,
                'lines': [1827, 1828], 'payload': PAYLOAD, 'slowed_effect': SLOWED,
                'timing': 'holder_end_of_turn', 'stat_pool': list(STAGES.STATS)}
    if row != expected:
        raise ValueError('reviewed alternate Poison policy changed')
    verified_source(rules, SOURCE, label='alternate Poison')
    CI.selected_definition(rules, '독')
    return row


def adoption(actor):
    row = actor.spec.get(ADOPTION)
    if row is None:
        return None
    policy(actor.r)
    if (not isinstance(row, dict) or set(row) != {'actor_id', 'clause_id', 'source', 'reason', 'active'}
            or row['actor_id'] != actor.entity_id or row['clause_id'] != CLAUSE
            or row['source'] != SOURCE or type(row['active']) is not bool):
        raise ValueError('actual actor-owned alternate Poison adoption required')
    E.text(row['reason'], 'alternate Poison adoption reason')
    if actor.kind != 'pokemon':
        raise ValueError('alternate Move example requires an actual Pokemon')
    return row


def adopt(engine, actor, *, reason):
    """Explicit native scripting entry; the sample is never enabled by species."""
    import world_entities as W
    import state_grants as G
    W.require_actors(engine, actor)
    policy(engine.r)
    E.text(reason, 'alternate Poison adoption reason')
    if actor.kind != 'pokemon':
        raise ValueError('alternate Move example requires an actual Pokemon')
    if adoption(actor) is not None:
        raise ValueError('alternate Poison adoption already recorded')
    def apply(staged, actual):
        actual.spec[ADOPTION] = {'actor_id': actual.entity_id, 'clause_id': CLAUSE,
                                 'source': deepcopy(SOURCE), 'reason': reason, 'active': True}
        staged.log('    '+actual.name+': slowing venom adopted', CLAUSE)
        return deepcopy(actual.spec[ADOPTION])
    return G.transition(engine, actor, apply)


def withdraw(engine, actor, *, reason):
    """Stop future applications; already inflicted Poison retains its source."""
    import world_entities as W
    import state_grants as G
    W.require_actors(engine, actor)
    E.text(reason, 'alternate Poison withdrawal reason')
    row = adoption(actor)
    if row is None or not row['active']:
        return False
    def apply(staged, actual):
        actual.spec[ADOPTION]['active'] = False
        staged.log('    '+actual.name+': slowing venom withdrawn: '+reason, CLAUSE)
        return True
    return G.transition(engine, actor, apply)


def _source(rules, source):
    if source not in rules.moves or rules._selected_rule(source) != source:
        raise ValueError('alternate Poison requires its actual selected inflicting Move')
    mechanics = rules.move_mech(source)[0]
    def poisons(value):
        if isinstance(value, list):
            return any(poisons(x) for x in value)
        if not isinstance(value, dict):
            return False
        return (value.get('apply_status') in ('독', '맹독')
                or value.get('type') == 'apply_status' and value.get('status') in ('독', '맹독')
                or any(poisons(x) for x in value.values()))
    if not poisons(mechanics):
        raise ValueError('alternate Poison requires an actual Poison-inflicting Move')
    return F.json_fingerprint(mechanics, sort_keys=True, compact=True, allow_nan=True)


def prepare_infliction(engine, target, condition, source, applied_by):
    if condition != '독' or applied_by is None:
        return None
    selected = adoption(applied_by)
    if selected is None or not selected['active'] or source not in engine.r.moves:
        return None
    import world_entities as W
    W.require_actors(engine, target, applied_by)
    return {'adoption': deepcopy(selected), 'source_fingerprint': _source(engine.r, source)}


def owns(row):
    return row.get('effect', {}).get('kind') == 'condition_variant'


def active(actor):
    rows = [row for row in CI.records(actor, '독') if owns(row)]
    if len(rows) > 1:
        raise ValueError('one actual Poison variant instance required')
    return rows[0] if rows else None


def effects(engine, actor, condition):
    """Actor-specific replacement, while the ordinary catalog stays untouched."""
    if condition == '독' and active(actor) is not None:
        validate_record(actor, active(actor))
        return []
    return __import__('type_ace').condition_effects(actor,condition,engine.r.condition_effects(condition))


def grant(engine, actor, *, source, applied_by, prepared):
    if '독' not in actor.conditions or CI.records(actor, '독'):
        raise ValueError('new actual Poison presence required for alternate venom')
    row = E.create(engine, actor, kind='condition', source=source, payload=PAYLOAD,
                   capacity={'bucket': 'condition:독', 'source': 'condition/독'},
                   lifetime={'boundary': 'persistent_condition_cure'}, applied_by=applied_by)
    row.update(deepcopy(prepared), issued_turn=actor.custom_conditions.get('combat_turn_serial', 0),
               applications=[], slowed_receipt=None)
    actor.custom_conditions.setdefault(CI.KEY, []).append(row)
    engine.time_actors([actor, applied_by])
    import effects as FX
    result = FX.run_effects(engine, applied_by, actor, [deepcopy(SLOWED)], {'hit': True}, source)
    if result.pending or result != (1, 0) or result.outcomes[0].status != 'completed':
        raise ValueError('alternate Poison Slowed contribution did not complete')
    row['slowed_receipt'] = result.outcomes[0].receipt
    validate_record(actor, row)
    return row


def retain_dependent(actor, condition):
    """An active venom still imposes Slowed when another cure removes its cause."""
    row = active(actor)
    if condition != '둔화' or row is None:
        return False
    import combat_timing as TIME
    children = [child for child in TIME.records(actor)
                if child.get('effect_receipt') is row['slowed_receipt']]
    if not children or condition not in actor.conditions:
        return False
    TIME.on_status_cure(actor, condition)
    children[0]['owned_statuses'].add(condition)
    return True


def archive(engine, actor, row, event):
    """Keep opaque native producer aliases across the common history copy."""
    closed = E.archive(engine, actor, row, state='expired', event=event)
    closed['slowed_receipt'] = row['slowed_receipt']
    for original, saved in zip(row['applications'], closed['applications']):
        saved['stage_receipt'] = original['stage_receipt']
    return closed


def end_turn(engine, actor):
    row = active(actor)
    if row is None:
        return
    import boss_transitions as BOSS
    if not BOSS.condition_applies_this_turn(actor, '독'):
        return
    validate_record(actor, row)
    if getattr(engine, '_active_turn_actor', None) is not actor:
        raise ValueError('alternate Poison requires its actual holder turn')
    turn = C.integer(actor.custom_conditions.get('combat_turn_serial'), 'actual venom holder turn', 1)
    if row['applications'] and row['applications'][-1]['turn'] == turn:
        return
    stat = engine.rng.choice(STAGES.STATS)
    before = actor.stages[stat]
    import world_entities as W
    import effects as FX
    issuer = W.actor_index(engine)[row[E.KEY]['applied_by_actor_id']]
    consequence = {'type': 'stage_change', 'stat': stat, 'delta': -1}
    result = FX.run_effects(engine, issuer, actor, [consequence], {'hit': True}, row['source'])
    if result.pending or result != (1, 0) or result.outcomes[0].status != 'completed':
        raise ValueError('alternate Poison stage contribution did not complete')
    row['applications'].append({'turn': turn, 'at': engine.elapsed_seconds, 'stat': stat,
                                'requested_delta': -1, 'before': before, 'after': actor.stages[stat],
                                'stage_receipt': result.outcomes[0].receipt})


def validate_record(actor, row, *, terminal=False):
    E.validate(row, actor=actor, terminal=terminal)
    policy(actor.r)
    meta = row[E.KEY]
    if (row['effect'] != PAYLOAD or meta['kind'] != 'condition'
            or meta['capacity'] != {'bucket': 'condition:독', 'source': 'condition/독'}
            or meta['lifetime'] != {'boundary': 'persistent_condition_cure'}):
        raise ValueError('alternate Poison effect authority changed')
    selected = row.get('adoption')
    if (not isinstance(selected, dict) or set(selected) != {'actor_id', 'clause_id', 'source', 'reason', 'active'}
            or selected['clause_id'] != CLAUSE or selected['source'] != SOURCE or selected['active'] is not True
            or selected['actor_id'] != meta.get('applied_by_actor_id')):
        raise ValueError('alternate Poison needs its actual inflictor adoption')
    E.text(selected['reason'], 'alternate Poison adoption reason')
    if row.get('source_fingerprint') != _source(actor.r, row['source']):
        raise ValueError('actual Poison-inflicting source changed')
    previous = C.integer(row.get('issued_turn'), 'alternate Poison issue turn', 0)
    if not isinstance(row.get('applications'), list):
        raise ValueError('alternate Poison turn applications required')
    when = row['at']
    for index, event in enumerate(row['applications']):
        if set(event) != {'turn', 'at', 'stat', 'requested_delta', 'before', 'after', 'stage_receipt'}:
            raise ValueError('actual alternate Poison stage event required')
        previous = C.integer(event['turn'], 'alternate Poison holder turn', previous + (index > 0),
                             actor.custom_conditions.get('combat_turn_serial', 0))
        when = C.integer(event['at'], 'alternate Poison actual turn time', when)
        if event['stat'] not in STAGES.STATS or event['requested_delta'] != -1:
            raise ValueError('alternate Poison only requests one non-HP stage loss')
        for key in ('before', 'after'):
            C.integer(event[key], 'actual alternate Poison stage', -6, 6)
    if not terminal and ('독' not in actor.conditions or len(CI.records(actor, '독')) != 1):
        raise ValueError('alternate Poison requires its single live Poison projection')
    if terminal and meta['end_event'] != {'kind': 'condition_cure', 'condition': '독'}:
        raise ValueError('alternate Poison ends only on actual Poison cure')
    return True


def validate_world(engine, index):
    for actor in index.values():
        adoption(actor)
        for row, phase in E.records(actor):
            if not owns(row):
                continue
            issuer = index.get(row[E.KEY].get('applied_by_actor_id'))
            chosen = adoption(issuer) if issuer is not None else None
            if chosen is None or {k: v for k, v in chosen.items() if k != 'active'} != {
                    k: v for k, v in row['adoption'].items() if k != 'active'}:
                raise ValueError('alternate Poison issuer adoption is missing or changed')
            producer = getattr(engine, '_effect_dispatch_receipts', {}).get(row.get('slowed_receipt'))
            if (producer is None or producer.get('status') != 'completed' or producer['actor'] is not issuer
                    or producer['target'] is not actor or producer['effect'] != SLOWED
                    or producer['source_id'] != row['source']):
                raise ValueError('alternate Poison needs its actual native Slowed producer')
            for event in row['applications']:
                stage = getattr(engine, '_effect_dispatch_receipts', {}).get(event['stage_receipt'])
                if (stage is None or stage.get('status') != 'completed' or stage['actor'] is not issuer
                        or stage['target'] is not actor or stage['source_id'] != row['source']
                        or stage['effect'] != {'type': 'stage_change', 'stat': event['stat'], 'delta': -1}):
                    raise ValueError('alternate Poison needs its actual native stage producer')
    return True
