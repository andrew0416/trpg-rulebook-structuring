"""GM-observed collateral effects on actual physical items.

Material and exposure are observations, never inferred from damage or an item
name. The GM supplies the actual move and why its environmental effect applies.
Default protected storage, exact replay and the selected physical instance are
shared; thawable medicine, electrical failure and destruction stay distinct.
"""
from copy import deepcopy
import common_checks as C
import state_grants as G
import resolution_transaction as TX
import world_entities as W
import environmental_item_state as ENV

FIELD = 'environmental_attack_observations'
PROFILES = {'liquid_medicine': (('얼음',), 'frozen'),
            'herb': (('불꽃',), 'destroyed'), 'apricorn': (('불꽃',), 'destroyed'),
            'ordinary_electronics': (('물', '전기'), 'electrical_failure'),
            'shielded_class_tool': (('물', '전기'), 'electrical_failure')}
SHIELDED_TOOLS = {'item/캡쳐-스타일러', 'item/고장기'}
RECOVERIES = {'ordinary_electronics': 'scene', 'shielded_class_tool': 'three_rounds'}


def _native_type(engine, move_id, reference, *, observed_at=None):
    """Read the retained application, never recalculate a consumed type choice."""
    import attack_damage_history as HISTORY
    if type(reference) is not dict or set(reference) != {'attacker_id', 'target_id', 'sequence'}:
        raise ValueError('native attack needs its attacker, target and sequence')
    for key in ('attacker_id', 'target_id'):
        G._text(reference[key], 'native attack ' + key)
    sequence = C.integer(reference['sequence'], 'native attack sequence', 1)
    index = W.actor_index(engine)
    target = index.get(reference['target_id'])
    if target is None or reference['attacker_id'] not in index:
        raise ValueError('native attack actors must belong to this world')
    HISTORY.validate_actor(target)
    rows = HISTORY.records(target)
    if sequence > len(rows):
        raise ValueError('native attack occurrence does not exist')
    row = rows[sequence - 1]
    if (row['attacker_id'] != reference['attacker_id'] or row['target_id'] != reference['target_id']
            or row['receipt']['source'] != move_id or row['at'] > engine.elapsed_seconds
            or row['round'] > engine.round_no
            or (observed_at is not None and row['at'] > observed_at)):
        raise ValueError('native attack occurrence does not match the observed move and actors')
    return row['move_type'], dict(kind='native_attack', **reference,
                                  occurrence_sha256=TX.request_fingerprint(row))


def _rows(obj):
    rows = obj.get(FIELD, {})
    if type(rows) is not dict:
        raise ValueError('environmental attacks must retain event identity')
    for event_id, row in rows.items():
        if type(row) is not dict or set(row) - {'round_offset_seconds', 'type_evidence'} != {
                'event_id', 'instance_id', 'item_rule_id', 'holder_id', 'move_id',
                'move_type', 'material', 'reason', 'exposed', 'at', 'outcome', 'sha256'}:
            raise ValueError('environmental attack observation is malformed')
        if row['sha256'] != TX.request_fingerprint({k: v for k, v in row.items() if k != 'sha256'}):
            raise ValueError('environmental attack observation changed')
        for key in ('event_id', 'holder_id', 'move_id', 'reason'):
            G._text(row[key], 'environmental attack ' + key)
        profile = PROFILES.get(row['material'])
        if (row['event_id'] != event_id or row['instance_id'] != obj.get('id')
                or row['item_rule_id'] != obj.get('item_rule_id')
                or not profile or row['move_type'] not in profile[0]
                or type(row['exposed']) is not bool
                or row['outcome'] != (profile[1] if row['exposed'] else 'protected')):
            raise ValueError('environmental attack identity or material disagrees')
        C.integer(row['at'], 'environmental attack time', 0)
        evidence = row.get('type_evidence')
        if 'type_evidence' in row and (type(evidence) is not dict or
                (evidence != {'kind': 'gm_observation'} and
                 (set(evidence) != {'kind', 'attacker_id', 'target_id', 'sequence', 'occurrence_sha256'}
                  or evidence.get('kind') != 'native_attack'))):
            raise ValueError('environmental attack actual type evidence is malformed')
        if 'round_offset_seconds' in row:
            C.integer(row['round_offset_seconds'], 'environmental attack round offset', 0, 10)
        if row['material'] in ('liquid_medicine', *RECOVERIES) and obj.get('kind') != 'item_instance':
            raise ValueError('medicine/electronics require an actual item rule')
        if row['material'] == 'ordinary_electronics' and obj.get('item_rule_id') in SHIELDED_TOOLS:
            raise ValueError('the named special tools have shielded recovery')
        if row['outcome'] in ('frozen', 'electrical_failure'):
            block = ENV._blocks(obj).get('environmental-attack:' + event_id)
            if not block or any(block[k] != v for k, v in {
                    'source': row['move_id'], 'condition': row['outcome'], 'exposed': True,
                    'holder_id': row['holder_id'], 'reason': row['reason'], 'at': row['at']}.items()):
                raise ValueError('observed environmental failure lost its actual use block')
            if row['outcome'] == 'electrical_failure' and (block.get('recovery') or {}).get('kind') != RECOVERIES[row['material']]:
                raise ValueError('electronic failure recovery changed its source policy')
            if (block.get('recovery') or {}).get('observed_offset') != row.get('round_offset_seconds'):
                raise ValueError('environmental attack timestamp differs from its use block')
        if row['outcome'] == 'destroyed':
            evidence = obj.get('destroyed')
            if not isinstance(evidence, dict) or any(evidence.get(k) != v for k, v in {
                    'source': row['move_id'], 'environmental_event_id': event_id,
                    'former_holder_id': row['holder_id']}.items()):
                raise ValueError('observed burning lost its actual destruction')
    return rows


def observe(engine, holder, instance_id, *, event_id, move_id, material, reason, exposed=False,
            round_offset_seconds=None, actual_type=None, native_attack=None):
    """Observe actual type via a native occurrence or explicit targetless GM fact."""
    W.require_actors(engine, holder)
    for value, label in ((event_id, 'event'), (move_id, 'move'), (reason, 'reason')):
        G._text(value, 'environmental attack ' + label)
    profile = PROFILES.get(material)
    if not profile or type(exposed) is not bool:
        raise ValueError('explicit supported material and boolean exposure required')
    if round_offset_seconds is not None:
        C.integer(round_offset_seconds, 'environmental attack round offset', 0, 10)
        if material != 'shielded_class_tool' or not exposed:
            raise ValueError('timestamp belongs to an exposed shielded tool')
    move = engine.r.move(move_id)
    if move['id'] != move_id:
        raise ValueError('canonical observed move identity required')
    if actual_type is not None and native_attack is not None:
        raise ValueError('choose one actual type evidence source')

    def apply(staged, actual):
        obj = getattr(staged, '_physical_objects', {}).get(instance_id)
        if not isinstance(obj, dict) or obj.get('kind') not in ('item_instance', 'physical_object'):
            raise ValueError('environmental attack requires an actual physical object')
        if material in ('liquid_medicine', *RECOVERIES) and obj['kind'] != 'item_instance':
            raise ValueError('medicine/electronics require an actual item rule')
        if material == 'ordinary_electronics' and obj.get('item_rule_id') in SHIELDED_TOOLS:
            raise ValueError('the named special tools have shielded recovery')
        rows = _rows(obj)
        previous = rows.get(event_id)
        if native_attack is not None:
            move_type, evidence = _native_type(staged, move_id, native_attack)
        elif actual_type is not None:
            G._text(actual_type, 'GM-observed actual attack type')
            move_type = actual_type
            evidence = {'kind': 'gm_observation'}
            if previous is not None and 'type_evidence' not in previous:
                evidence = None  # Legacy facts keep their original evidence and type.
        elif previous is not None:
            move_type, evidence = previous['move_type'], previous.get('type_evidence')
        else:
            raise ValueError('new observation needs a native attack or explicit GM-observed actual type')
        if evidence is not None and evidence['kind'] == 'native_attack':
            reference = {k: evidence[k] for k in ('attacker_id', 'target_id', 'sequence')}
            retained_type, retained = _native_type(staged, move_id, reference,
                                          observed_at=previous['at'] if previous else staged.elapsed_seconds)
            if retained_type != move_type or retained != evidence:
                raise ValueError('environmental attack lost its retained native occurrence')
        if move_type not in profile[0]:
            raise ValueError('observed actual attack type does not support this material effect')
        payload = dict(event_id=event_id, instance_id=instance_id,
                       item_rule_id=obj.get('item_rule_id'), holder_id=actual.entity_id,
                       move_id=move_id, move_type=move_type, material=material,
                       reason=reason, exposed=exposed)
        if evidence is not None:payload['type_evidence'] = deepcopy(evidence)
        if round_offset_seconds is not None:payload['round_offset_seconds'] = round_offset_seconds
        if event_id in rows:
            if (any(rows[event_id].get(k) != v for k, v in payload.items())
                    or rows[event_id].get('type_evidence') != evidence
                    or rows[event_id].get('round_offset_seconds') != round_offset_seconds):
                raise ValueError('environmental attack replay changed its observation')
            return deepcopy(rows[event_id])
        W.require_physical_access(obj)
        owner = obj.get('equipped_by') or obj.get('carrier_id') or obj.get('owner_id')
        if owner != actual.entity_id:
            raise ValueError('environmental attack needs the actual holder/owner')
        outcome = profile[1] if exposed else 'protected'
        if outcome in ('frozen', 'electrical_failure'):
            ENV.observe(staged, actual, instance_id, event_id='environmental-attack:' + event_id,
                        condition=outcome, source=move_id, reason=reason, exposed=True,
                        recovery=RECOVERIES.get(material), round_offset_seconds=round_offset_seconds)
        elif outcome == 'destroyed':
            if obj.get('equipped_by'):
                import items as I
                I.destroy_equipment(staged, actual, instance_id, reason=move_id)
            else:
                W.finish_physical_use(staged, obj, 'destroyed',
                                      dict(source=move_id, former_holder_id=actual.entity_id))
            # Nested transitions preserve object identity, including load/remnants.
            obj = staged._physical_objects[instance_id]
            obj['destroyed']['environmental_event_id'] = event_id
        row = dict(payload, at=staged.elapsed_seconds, outcome=outcome)
        row['sha256'] = TX.request_fingerprint(row)
        obj.setdefault(FIELD, {})[event_id] = row
        return deepcopy(row)
    return G.transition(engine, holder, apply)


def validate_world(engine):
    for obj in getattr(engine, '_physical_objects', {}).values():
        if FIELD in obj:
            for row in _rows(obj).values():
                evidence = row.get('type_evidence') or {}
                if evidence.get('kind') == 'native_attack':
                    reference = {k: evidence[k] for k in ('attacker_id', 'target_id', 'sequence')}
                    actual_type, actual_evidence = _native_type(engine, row['move_id'], reference, observed_at=row['at'])
                    if actual_type != row['move_type'] or actual_evidence != evidence:
                        raise ValueError('environmental attack lost its retained native occurrence')
