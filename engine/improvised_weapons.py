"""C09-062: explicit GM rulings on an actual ordinary weapon instance.

The printed AC -1 called a penalty remains unresolved. Each table chooses
either a roll modifier or an AC-threshold modifier; neither is a default.
"""
from copy import deepcopy
import root_resolution as ROOT
import world_entities as WORLD
import state_grants as GRANTS
from source_context import verified_source

SOURCE = 'ch09-equipment/장비/무기'
CLAUSE = 'C09-062'
REFERENCE = {'file': 'input/ch09-equipment.md',
             'sha256': 'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'}
STATEMENT_SHA256 = '5da472ed6ba095044aa837c6e2f3f66166b0630bb510bd9075b13474aaac8190'
AC_CONFLICT = 'Printed AC -1 is called a penalty; native AC -1 lowers the hit threshold.'
FIELD = 'improvised_weapon_ruling'
MARK = '_improvised_weapon'


def _source(e):
    if (e.r._selected_rule(SOURCE) != SOURCE or e.rulings.mech.get(SOURCE)
            or e.rulings.effects.get(SOURCE)):
        raise ValueError('selected improvised weapon source needs its own adapter')
    verified_source(e.r, REFERENCE, label='improvised weapon')


def ruling(e, uid):
    import optional_weapon_framework as FW
    obj, weapon = FW.object_profile(e, uid, usable=False)
    row = obj.get(FIELD)
    if row is None:
        return None
    _source(e)
    fields = {'clause_id', 'rule_source', 'reference', 'statement_sha256', 'source_conflict',
              'instance_id', 'item_rule_id', 'weapon_profile', 'ac_mode', 'ac_delta', 'db_delta',
              'break_after_attack', 'gm_id', 'source', 'reason', 'fingerprint'}
    if (type(row) is not dict or set(row) != fields or row['clause_id'] != CLAUSE
            or row['rule_source'] != SOURCE or row['reference'] != REFERENCE
            or row['statement_sha256'] != STATEMENT_SHA256 or row['source_conflict'] != AC_CONFLICT
            or row['instance_id'] != uid or row['item_rule_id'] != obj.get('item_rule_id')
            or row['weapon_profile'] != ROOT.fingerprint(weapon)
            or row['fingerprint'] != ROOT.fingerprint({k: v for k, v in row.items() if k != 'fingerprint'})
            or row['ac_mode'] not in ('accuracy_roll', 'ac_threshold')
            or type(row['ac_delta']) is not int or type(row['db_delta']) is not int or row['db_delta'] > 0
            or type(row['break_after_attack']) is not bool
            or not (row['ac_delta'] or row['db_delta'] or row['break_after_attack'])):
        raise ValueError('actual explicit improvised weapon ruling changed')
    for key in ('gm_id', 'source', 'reason'):
        WORLD._text(row[key], 'GM improvised weapon ' + key)
    if weapon['arcane']:
        raise ValueError('Arcane weapon improvisation requires its own sourced adapter')
    if row['item_rule_id'] and e.r._selected_rule(row['item_rule_id']) != row['item_rule_id']:
        raise ValueError('selected actual improvised item identity changed')
    return row


def configure(e, actor, uid, *, ac_mode, ac_delta, db_delta, break_after_attack,
              gm_id, source, reason):
    """Adopt this GM's explicit choices once, before equipping the real object."""
    WORLD.require_actors(e, actor)
    _source(e)
    import optional_weapon_framework as FW
    obj, weapon = FW.object_profile(e, uid)
    if (actor.kind != 'trainer' or actor.entity_id not in (obj.get('owner_id'), obj.get('carrier_id'))
            or obj.get('equipped_by')):
        raise ValueError('actual accessible unequipped trainer object required')
    row = dict(clause_id=CLAUSE, rule_source=SOURCE, reference=deepcopy(REFERENCE),
               statement_sha256=STATEMENT_SHA256, source_conflict=AC_CONFLICT,
               instance_id=uid, item_rule_id=obj.get('item_rule_id'),
               weapon_profile=ROOT.fingerprint(weapon), ac_mode=ac_mode,
               ac_delta=ac_delta, db_delta=db_delta, break_after_attack=break_after_attack,
               gm_id=gm_id, source=source, reason=reason)
    row['fingerprint'] = ROOT.fingerprint(row)
    def apply(staged, owner):
        target = staged._physical_objects[uid]
        if FIELD in target and target[FIELD] != row:
            raise ValueError('improvised weapon ruling is immutable')
        target[FIELD] = deepcopy(row)
        return deepcopy(ruling(staged, uid))
    return GRANTS.transition(e, actor, apply)


def adapt(e, actor, move):
    """Called after the existing weapon adapter, keeping its DB marker intact."""
    attack = move.get('_weapon_attack', {})
    entry = actor.custom_conditions.get('equipped_weapons', {}).get(attack.get('key'))
    uid = entry.get('instance_id') if entry else None
    if uid is None or FIELD not in getattr(e, '_physical_objects', {}).get(uid, {}):
        return move
    row = ruling(e, uid)
    import optional_weapon_framework as FW
    obj, weapon = FW.object_profile(e, uid)
    if (actor.kind != 'trainer' or obj.get('equipped_by') != actor.entity_id
            or attack.get('source') != entry.get('item_id', SOURCE) or move['id'] not in entry['available_moves']):
        raise ValueError('improvised attack requires its actual equipped trainer weapon')
    import turn as TURN
    struggle = move['id'] == entry['struggle_id']
    base_ac = e.r.move(move['id'])['ac']
    if not struggle and '_optional_crafted_equipment' not in move:
        base_ac += TURN.WEAPON_KIND[weapon['kind']]['ac']
    if struggle and FW.skill_rank(e, actor, entry['weapon']) >= 5:
        base_ac -= 1
    threshold = row['ac_delta'] if row['ac_mode'] == 'ac_threshold' else 0
    marker = dict(instance_id=uid, weapon_key=attack['key'], ruling_fingerprint=row['fingerprint'],
                  ac_threshold_delta=threshold,
                  accuracy_roll_delta=row['ac_delta'] if row['ac_mode'] == 'accuracy_roll' else 0,
                  db_delta=row['db_delta'])
    if MARK in move:
        if move[MARK] != marker or move['ac'] != base_ac + threshold:
            raise ValueError('prepared improvised weapon authority changed')
        return move
    if move['ac'] != base_ac:
        raise ValueError('improvised modifier requires the native ordinary weapon accuracy')
    out = deepcopy(move)
    out['ac'] += threshold
    out[MARK] = marker
    return out


def observe_completion(e, completion):
    """A real completed miss uses the weapon too; refusals never break it."""
    marker = completion['move'].get(MARK)
    if marker is None:
        return
    if (getattr(e, '_move_completions', {}).get(completion['id']) is not completion
            or completion['phase'] != 'completion_effects' or not completion['sealed']
            or set(completion['results']) != {t.entity_id for t in completion['targets']}):
        raise ValueError('actual whole weapon Move completion required')
    if not any(not result['cancelled'] for result in completion['results'].values()):
        return
    uid = marker['instance_id']
    obj = e._physical_objects[uid]
    row = ruling(e, uid)
    if marker['ruling_fingerprint'] != row['fingerprint']:
        raise ValueError('completed improvised weapon ruling changed')
    _break(e, uid, completion['actor'], row, {'completion_id': completion['id']})


def bonus(move, field):
    marker = move.get(MARK)
    if marker is None:
        return 0
    if (move.get('_weapon_attack', {}).get('key') != marker['weapon_key']
            or move.get('_optional_weapon_framework', {}).get('instance_id') != marker['instance_id']):
        raise ValueError('improvised bonus requires its actual prepared physical weapon')
    return marker[field]


def observe_tool_attack(e, actor, receipt):
    """The existing object-target producer has its own completed-use receipt."""
    import physical_object_attacks as ATTACKS
    move = receipt.get('tool_attack', {}).get('definition', {})
    marker = move.get(MARK)
    if marker is None:
        return
    target = e._physical_objects[receipt['intent']['object_id']]
    if (not any(actual is receipt for actual in target[ATTACKS.FIELD]['attacks'])
            or receipt['intent']['actor_id'] != actor.entity_id
            or receipt['intent']['tool_id'] != marker['instance_id']
            or receipt['receipt_hash'] != ATTACKS._hash({k: v for k, v in receipt.items() if k != 'receipt_hash'})):
        raise ValueError('actual returned physical tool attack required')
    uid = marker['instance_id']
    row = ruling(e, uid)
    if marker['ruling_fingerprint'] != row['fingerprint']:
        raise ValueError('completed tool attack ruling changed')
    _break(e, uid, actor, row, {'tool_event_id': receipt['event_id'], 'target_object_id': target['id']})


def _break(e, uid, actor, row, event):
    obj = e._physical_objects[uid]
    if not row['break_after_attack'] or any(WORLD.physical_lifecycle(obj)[k] for k in ('destroyed', 'consumed')):
        return
    holder_id = obj.get('equipped_by')
    if holder_id:
        holder = WORLD.actor_index(e)[holder_id]
        keys = [key for key, entry in holder.custom_conditions.get('equipped_weapons', {}).items()
                if entry.get('instance_id') == uid]
        if len(keys) != 1:
            raise ValueError('breaking weapon requires its actual equipment relation')
        registration = next((key for key, entry in getattr(holder, '_item_reg', {}).items()
                             if entry.get('instance_id') == uid), None)
        if registration is not None:
            import items as ITEMS
            ITEMS.unregister_item(e, holder, registration_key=registration)
        else:
            import turn as TURN
            TURN.unequip_weapon(e, holder, keys[0])
    if obj.get('carrier_id'):
        carrier = WORLD.actor_index(e)[obj['carrier_id']]
        import capability_actions as CAP
        CAP.set_carried(e, carrier, [x for x in carrier.spec['_carried_load']['objects'] if x['id'] != uid],
                        'improvised weapon broke after its actual attack')
    WORLD.finish_physical_use(e, obj, 'destroyed', dict(source=SOURCE,
        former_holder_id=actor.entity_id, ruling_fingerprint=row['fingerprint'], at=e.elapsed_seconds, **event))


def validate_world(e):
    for uid, obj in getattr(e, '_physical_objects', {}).items():
        if FIELD not in obj:
            continue
        row = ruling(e, uid)
        terminal = obj.get('destroyed')
        if isinstance(terminal, dict) and terminal.get('source') == SOURCE:
            if 'completion_id' in terminal:
                completion = getattr(e, '_move_completions', {}).get(terminal['completion_id'])
                valid = (completion is not None and completion['phase'] == 'complete'
                         and completion['move'].get(MARK, {}).get('instance_id') == uid
                         and any(not result['cancelled'] for result in completion['results'].values()))
            else:
                import physical_object_attacks as ATTACKS
                target = getattr(e, '_physical_objects', {}).get(terminal.get('target_object_id'), {})
                valid = any(receipt['event_id'] == terminal.get('tool_event_id')
                            and receipt['intent'].get('tool_id') == uid
                            and receipt.get('tool_attack', {}).get('definition', {}).get(MARK, {}).get('ruling_fingerprint') == row['fingerprint']
                            for receipt in target.get(ATTACKS.FIELD, {}).get('attacks', []))
            if not row['break_after_attack'] or terminal.get('ruling_fingerprint') != row['fingerprint'] or not valid:
                raise ValueError('improvised destruction requires its actual completed attack')
