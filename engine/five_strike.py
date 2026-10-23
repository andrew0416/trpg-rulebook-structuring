"""One native d8 observation, then combined DB before STAB and other bonuses."""
from copy import deepcopy
import common_checks as C

KEY = 'five_strike_history'
SOURCE_REF = {'file': 'input/ch10-index-reference.md',
    'sha256': 'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}


def hits(face):
    C.integer(face, 'Five Strike d8', 1, 8)
    return (1, 2, 2, 3, 3, 3, 4, 5)[face-1]


def applies(move):
    return '오단타격' in str(move.get('range', ''))


def validate_actor(actor):
    rows = actor.spec.get(KEY, [])
    if not isinstance(rows, list): raise ValueError('Five Strike history must be a list')
    for number, row in enumerate(rows, 1):
        required = {'sequence', 'actor_id', 'move_id', 'target_ids', 'face', 'hits', 'at', 'choice_id'}
        if not isinstance(row, dict) or set(row) not in (required, required | {'loaded_dice'}):
            raise ValueError('Five Strike observation changed')
        if row['sequence'] != number or row['actor_id'] != actor.entity_id:
            raise ValueError('Five Strike observation owner changed')
        if not applies(actor.r.move(row['move_id'])) or row['hits'] != hits(row['face']):
            raise ValueError('Five Strike source or hit count changed')
        dice = row.get('loaded_dice')
        if dice is not None:
            if (not isinstance(dice, dict) or set(dice) != {'rolls','hits','item_id','instance_id'}
                    or dice.get('item_id') != 'item/속임수주사위'
                    or not isinstance(dice.get('instance_id'), str) or not dice['instance_id']
                    or not isinstance(dice.get('rolls'), list) or len(dice['rolls']) != 2):
                raise ValueError('Five Strike Loaded Dice source changed')
            for face in dice['rolls']:C.integer(face,'Loaded Dice d8',1,8)
            if row['face'] != max(dice['rolls']) or row['hits'] != dice['hits']:
                raise ValueError('Five Strike differs from its two Loaded Dice observations')
            if row['choice_id'] is not None:
                raise ValueError('fixed Five Strike mode cannot also claim a dice roll')
        C.integer(row['at'], 'Five Strike time', 0)
        if not isinstance(row['target_ids'], list) or not row['target_ids'] or len(set(row['target_ids'])) != len(row['target_ids']):
            raise ValueError('Five Strike actual targets required')
        if row['choice_id'] is not None:
            import optional_move_modes as OPTIONAL
            choice = next((r for r in OPTIONAL.history(actor) if r['id'] == row['choice_id']), None)
            policy = OPTIONAL.definition(actor.r, row['move_id'])
            if (choice is None or choice['move_id'] != row['move_id'] or choice['use'] is None
                    or policy.get('selected_move', {}).get('_five_strike_roll') != row['face']):
                raise ValueError('Five Strike fixed roll needs its actual optional choice')


def preflight(engine, actor, move):
    if not applies(move): return
    from source_context import verified_source
    verified_source(engine.r,SOURCE_REF,label='Five Strike')
    validate_actor(actor)


def begin_move_use(engine, actor, target, move):
    if not applies(move): return
    preflight(engine,actor,move)
    import move_activation as ACTIVATION
    scopes = getattr(engine, '_event_use_scopes', [])
    if not scopes or scopes[-1].get('move_id') != move['id'] or scopes[-1]['actor'] is not actor:
        raise ValueError('actual Five Strike activation required')
    validate_actor(actor)
    group = ACTIVATION.current_scope(engine, actor, target, move['id'])
    row = group.get('five_strike') if group is not None else None
    if row is None:
        loaded_dice = None
        # The index definition explicitly owns this d8, even for a missed attack.
        if '_five_strike_roll' in move:
            import optional_move_modes as OPTIONAL
            policy = OPTIONAL.definition(engine.r, move['id'])
            if (policy is None or policy.get('selected_move', {}).get('_five_strike_roll') != move['_five_strike_roll']
                    or '_optional_move_choice' not in move):
                raise ValueError('fixed Five Strike roll requires a reviewed optional effect')
            face = move['_five_strike_roll']
        else:
            import csv_item_physical_contracts as CSV_ITEMS
            loaded_dice = CSV_ITEMS.loaded_dice_hits(engine, actor, optional=True)
            if loaded_dice is None:
                face, _ = engine.roll_expr('1d8')
            else:
                face = max(loaded_dice['rolls'])
        row = dict(sequence=len(actor.spec.get(KEY, []))+1, actor_id=actor.entity_id,
                   move_id=move['id'], target_ids=[t.entity_id for t in move.get('_actual_targets', [target])],
                   face=face, hits=hits(face), at=engine.elapsed_seconds,
                   choice_id=move.get('_optional_move_choice'))
        if loaded_dice is not None:row['loaded_dice'] = loaded_dice
        actor.spec.setdefault(KEY, []).append(row)
        if group is not None: group['five_strike'] = row
    move['_five_strike'] = deepcopy(row)
    validate_actor(actor)
    engine.log(f"    오단타격 d8={row['face']}: {row['hits']}회 합산", 'input/ch10-index-reference.md:336-337')


def combined_base(actor, move, base):
    if not applies(move): return base
    row = move.get('_five_strike')
    if row is None or row not in actor.spec.get(KEY, []) or row['move_id'] != move['id']:
        raise ValueError('Five Strike damage requires its native d8 observation')
    return C.integer(base, 'printed Five Strike DB', 1)*row['hits']


def technician_bonus(actor, move):
    if not applies(move) or actor.abilities_suppressed: return 0
    # The source's ordinary DB<=6 predicate is waived for this keyword.
    return 2 if '테크니션' in actor.abilities or 'ability/테크니션' in actor.abilities else 0


def validate_world(engine, index):
    for actor in index.values():
        validate_actor(actor)
        for row in actor.spec.get(KEY, []):
            if row['at'] > engine.elapsed_seconds or any(uid not in index for uid in row['target_ids']):
                raise ValueError('Five Strike references missing target or future event')
            dice = row.get('loaded_dice')
            if dice is not None:
                obj = getattr(engine,'_physical_objects',{}).get(dice['instance_id'])
                if not isinstance(obj,dict) or obj.get('item_rule_id') != dice['item_id']:
                    raise ValueError('Five Strike Loaded Dice physical source is missing')
