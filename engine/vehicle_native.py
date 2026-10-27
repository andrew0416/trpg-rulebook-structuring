"""Sourced vehicle bodies and adapters over the existing physical-state owners.

Template/upgrade receipts belong to the registered vehicle, permissions to the
operator's grant ledger, damage to repair_breach, and repairs to repair_restore.
Optional customization prices are explicit GM quotes, never inferred mandates.
"""
from copy import deepcopy
from pathlib import Path
from fractions import Fraction
import hashlib
import json

import common_checks as C
import crafting_recipes as Q
import state_grants as G
import world_entities as W
import resolution_transaction as TX

SOURCE = 'supp-polygon/차량-제작-가이드라인'
TRAINING = 'native:vehicle-training'
MODES = ('land', 'swim', 'levitate', 'sky')


def policy(e):
    value = json.loads((Path(e.r.root) / 'data/vehicle-native-policy.json').read_text(encoding='utf-8'))
    if value['schema_version'] != 1 or value['source'] != SOURCE:
        raise ValueError('known native vehicle source profile required')
    Q._selected(e, SOURCE)
    if hashlib.sha256((Path(e.r.root) / value['source_file']).read_bytes()).hexdigest() != value['source_sha256']:
        raise ValueError('native vehicle source changed')
    from source_context import verified_source
    for reference in value['supporting_sources']:
        verified_source(e.r, reference, source_root='source-audit' if reference['file'].startswith('source-audit/') else 'input')
    return value


def _alloy_document(p):
    return {'schema': 1, 'id': 'native/vehicle-reinforced-alloys', 'variants': [{
        'rule_id': SOURCE, 'source': {'file': p['source_file'], 'sha256': p['source_sha256']},
        'values': {'variant': {'$input': 'source_text'}, 'definitions': {
            'korean_ground': deepcopy(p['upgrades']['reinforced_alloys']),
            'english_grass': deepcopy(p['reinforced_alloys_english'])}},
        'inputs': {'source_text': {'type': 'string', 'authority': 'gm', 'decision_kind': 'source_conflict',
            'choices': ['korean_ground', 'english_grass'],
            'question': 'Reinforced Alloys resists Ground in Korean and Grass in English. Which complete definition applies?'}}}]}


def reinforced_alloys_choices(e):
    """Prepare the existing scoped source decision before the native purchase."""
    import source_policy as POLICY
    return POLICY.resolve(e.r, _alloy_document(policy(e)))


def _upgrade_definition(p, receipt):
    """Read the retained complete definition; legacy purchases retain Korean."""
    import source_selection as SELECTION
    import root_resolution as ROOT
    intent = receipt['intent']; result = receipt['result']; uid = intent['upgrade']
    choice = intent.get('source_choice'); resolved = result.get('source_policy')
    if choice is None and resolved is None:
        return p['upgrades'][uid]
    if uid != 'reinforced_alloys' or type(choice) is not dict or type(resolved) is not dict:
        raise ValueError('actual Reinforced Alloys source choice required')
    Q._fields(choice, ('value', 'reason', 'scope')); Q._text(choice['value']); Q._text(choice['reason'])
    document = _alloy_document(p)
    values = SELECTION.policy_values(resolved['source_policy_binding'], document['variants'])
    selected = choice['value']
    if (selected not in values['definitions'] or resolved['status'] != 'PolicyValuesReady'
            or resolved['values'] != {'variant': selected, 'definitions': values['definitions']}
            or resolved['selected_id'] != SOURCE or resolved['definition_hash'] != ROOT.fingerprint(document)
            or resolved['decision_scope'] != choice['scope']
            or resolved['inputs_hash'] != ROOT.fingerprint({'context': {}, 'decisions': {'source_text': choice}, 'state': {}})
            or resolved['decision_evidence'] != [{'input': 'source_text', 'reason': choice['reason'],
                'decision_kind': 'source_conflict', 'scope': choice['scope']}]):
        raise ValueError('retained Reinforced Alloys source decision changed')
    return values['definitions'][selected]


def _sign(value):
    return dict(value, sha256=TX.request_fingerprint(value))


def _verify(value):
    if type(value) is not dict or value.get('sha256') != TX.request_fingerprint({k: v for k, v in value.items() if k != 'sha256'}):
        raise ValueError('native vehicle receipt changed')


def _ratio(value):
    number = Fraction(value)
    return [number.numerator, number.denominator]


def _derived(p, config):
    template = p['templates'].get(config.get('template'))
    if template is None:
        raise ValueError('exact sourced vehicle template required')
    column = template['column']; counts = config['upgrades']
    if set(counts) != set(p['upgrades']):
        raise ValueError('finite sourced vehicle upgrade counts required')
    for uid, number in counts.items():
        C.integer(number, 'actual purchased vehicle upgrade count', 0)
        rank = p['upgrades'][uid]['rank']
        limit = 1 if rank is None else rank
        if number > limit:
            raise ValueError('vehicle upgrade purchase exceeds sourced rank or single-purchase limit; over-cap legacy records require explicit reconstruction')
    hp = template['hp'] + counts['structural_integrity'] * p['upgrades']['structural_integrity']['amount'][column]
    defense = template['defense'] + counts['armored_plating'] * p['upgrades']['armored_plating']['amount'][column]
    speed = template['speed'] + counts['vehicle_speed']
    armor = counts['breach_resistance'] * 2
    cost = template['cost'] + sum(p['upgrades'][uid]['cost'][column] * n for uid, n in counts.items())
    modes = ['land']
    for quote in config['modifications']:
        Q._fields(quote, ('id', 'kind', 'operation', 'mode', 'cost', 'reason'))
        Q._text(quote['id']); Q._text(quote['reason']); C.integer(quote['cost'], 'actual GM customization quote', 0)
        if quote['kind'] == 'movement':
            if quote['operation'] not in ('add', 'replace') or quote['mode'] not in MODES:
                raise ValueError('explicit added or replaced vehicle movement required')
            if quote['operation'] == 'replace': modes = [quote['mode']]
            elif quote['mode'] in modes: raise ValueError('additional movement must add a distinct mode')
            else: modes.append(quote['mode'])
        elif quote['kind'] in ('underwater', 'spaceworthy'):
            if quote['operation'] is not None or quote['mode'] is not None:
                raise ValueError('environment adaptation does not silently add movement')
        else: raise ValueError('known optional vehicle modification required')
        cost += quote['cost']
    if len({q['id'] for q in config['modifications']}) != len(config['modifications']):
        raise ValueError('distinct actual vehicle customization identities required')
    return {'max_hp': hp, 'stats': {'hp': hp, 'def': defense, 'spd': defense},
            'overland': speed if 'land' in modes else 0, 'movement': {m: speed for m in modes},
            'breach_security': template['security'] + armor, 'breach_capacity': template['capacity'] + armor,
            'breach_resistance_armor': bool(armor), 'total_cost': cost}


def policy_for_body(row):
    """Static source data for the engine-free machine body view.

    Runtime entrypoints validate the selected source and its snapshot first.
    """
    return json.loads((Path(__file__).resolve().parents[1] / 'data/vehicle-native-policy.json').read_text(encoding='utf-8'))


def validate_record(e, row):
    native = row.get('native_vehicle')
    if native is None: return None
    Q._fields(native, ('config', 'upgrades', 'events', 'shield', 'salvage_id'))
    config = native['config']; _verify(config)
    Q._fields(config, ('source', 'template', 'maximum_occupants', 'upgrades', 'modifications', 'sha256'))
    if config['source'] != SOURCE: raise ValueError('actual native vehicle source required')
    C.integer(config['maximum_occupants'], 'actual designed vehicle occupancy', 1)
    p = policy(e); expected = _derived(p, config)
    purchased = {uid: 0 for uid in config['upgrades']}
    for field in ('max_hp', 'stats', 'overland', 'breach_security', 'breach_capacity', 'breach_resistance_armor'):
        if row[field] != expected[field]: raise ValueError('actual vehicle body differs from its template/upgrade receipts: ' + field)
    if len(row['passenger_ids']) > config['maximum_occupants']:
        raise ValueError('actual vehicle occupancy exceeds designed capacity')
    for entries in (native['upgrades'], native['events']):
        if type(entries) is not dict: raise ValueError('actual vehicle request receipts required')
        for uid, receipt in entries.items():
            Q._text(uid); _verify(receipt)
            if receipt['fingerprint'] != TX.request_fingerprint(receipt['intent']):
                raise ValueError('actual vehicle request intent changed')
    for receipt in native['upgrades'].values():
        uid = receipt['intent']['upgrade']
        if uid not in purchased or receipt['intent']['vehicle_id'] != row['id']:
            raise ValueError('actual purchased vehicle upgrade identity required')
        purchased[uid] += 1
        if receipt['result']['count'] != purchased[uid]: raise ValueError('actual vehicle upgrade ordinal changed')
        result = receipt['result']; definition = _upgrade_definition(p, receipt)
        if result['vehicle_id'] != row['id'] or result['upgrade'] != uid or result['cost'] != definition['cost'][p['templates'][config['template']]['column']]:
            raise ValueError('actual purchased vehicle upgrade identity or sourced price changed')
        # Older receipts already retain SOURCE plus their exact upgrade key.
        # New purchases also name the independent source clause and excerpt.
        for field, expected_source in (('definition_clause_id', definition['clause_id']), ('definition_excerpt_sha256', definition['excerpt_sha256'])):
            if result.get(field, expected_source) != expected_source:
                raise ValueError('actual purchased vehicle upgrade source changed')
    if purchased != config['upgrades']: raise ValueError('vehicle upgrade count needs actual purchase receipts')
    Q._fields(native['shield'], ('scene_id', 'temporary_hp'))
    if native['shield']['scene_id'] is not None: Q._text(native['shield']['scene_id'])
    C.integer(native['shield']['temporary_hp'], 'vehicle shield temporary HP', 0)
    shield_maximum = config['upgrades']['shield_generator'] * p['upgrades']['shield_generator']['amount'][p['templates'][config['template']]['column']]
    if native['shield']['temporary_hp'] > shield_maximum or (native['shield']['scene_id'] is None and native['shield']['temporary_hp']):
        raise ValueError('vehicle shield temporary HP requires its installed source and scene')
    if native['salvage_id'] is not None:
        salvage = getattr(e, '_physical_objects', {}).get(native['salvage_id'])
        if not row['destroyed'] or not salvage or salvage.get('vehicle_salvage', {}).get('vehicle_id') != row['id']:
            raise ValueError('vehicle salvage must resolve to its destroyed source body')
    return expected


def register_template(e, owner, identity, template, *, maximum_occupants, location, reason, modifications=()):
    W.require_actors(e, owner); Q._text(identity); Q._text(reason); p = policy(e)
    if identity in W.entity_index(e): raise ValueError('new distinct actual vehicle identity required')
    C.integer(maximum_occupants, 'actual designed vehicle occupancy', 1)
    config = _sign({'source': SOURCE, 'template': template, 'maximum_occupants': maximum_occupants,
                    'upgrades': {uid: 0 for uid in p['upgrades']}, 'modifications': deepcopy(list(modifications))})
    body = _derived(p, config)
    def apply(staged, actor):
        import special_entities as S
        row = {'id': identity, 'kind': 'vehicle', 'location': deepcopy(location),
               **{k: deepcopy(body[k]) for k in ('max_hp', 'stats', 'overland', 'breach_security', 'breach_capacity', 'breach_resistance_armor')},
               'hp': body['max_hp'], 'breaches': 0, 'patched_breaches': 0, 'destroyed': False,
               'owner_id': actor.entity_id, 'driver_id': None, 'passenger_ids': [], 'weapon_ids': [],
               'native_vehicle': {'config': config, 'upgrades': {}, 'events': {},
                                  'shield': {'scene_id': None, 'temporary_hp': 0}, 'salvage_id': None}}
        S.observe(staged, row, reason=reason)
        return deepcopy(staged._physical_objects[identity])
    return G.transition(e, owner, apply)


def _vehicle(e, identity):
    import special_entities as S
    row = getattr(e, '_physical_objects', {}).get(identity)
    if row is None or row.get('kind') != 'vehicle' or 'native_vehicle' not in row:
        raise ValueError('actual sourced native vehicle required')
    S.validate_record(e, row)
    return row


def _replay(native, key, intent, section='events'):
    saved = native[section].get(key)
    if saved is None: return None
    _verify(saved)
    if saved['fingerprint'] != TX.request_fingerprint(intent): raise ValueError('native vehicle request changed intent')
    return deepcopy(saved['result'])


def _save(native, key, intent, result, section='events'):
    native[section][key] = _sign({'intent': deepcopy(intent), 'fingerprint': TX.request_fingerprint(intent), 'result': deepcopy(result)})


def acquire_upgrade(e, owner, identity, upgrade, *, request_id, reason, source_choice=None):
    W.require_actors(e, owner); Q._text(request_id); Q._text(reason); p = policy(e)
    if upgrade not in p['upgrades']: raise ValueError('known sourced vehicle upgrade required')
    intent = {'owner_id': owner.entity_id, 'vehicle_id': identity, 'upgrade': upgrade, 'reason': reason}
    resolved = None
    if source_choice is not None:
        if upgrade != 'reinforced_alloys': raise ValueError('only Reinforced Alloys has a source conflict choice')
        import source_policy as POLICY
        resolved = POLICY.resolve(e.r, _alloy_document(p), decisions={'source_text': source_choice})
        if resolved['status'] != 'PolicyValuesReady': raise ValueError('complete Reinforced Alloys source choice required')
        intent['source_choice'] = deepcopy(source_choice)
    row = _vehicle(e, identity); replay = _replay(row['native_vehicle'], request_id, intent, 'upgrades')
    if replay is not None: return replay
    def apply(staged, actor):
        row = _vehicle(staged, identity); W.require_usable_object(row)
        if row['owner_id'] != actor.entity_id or staged.encounter_active:
            raise ValueError('actual owner purchases vehicle upgrades outside an encounter')
        config = deepcopy(row['native_vehicle']['config']); before = _derived(p, config)
        config['upgrades'][upgrade] += 1; config.pop('sha256'); config = _sign(config); after = _derived(p, config)
        cost = after['total_cost'] - before['total_cost']
        payment = Q.prepare_materials(staged, actor, [{'id': 'vehicle-upgrade', 'options': [{'kind': 'value', 'category': '차량', 'amount': cost, 'scrap': False, 'money': True}]}], inputs={})
        paid = Q.pay_materials(staged, actor, payment['payments'])
        row['native_vehicle']['config'] = config
        row['hp'] += after['max_hp'] - before['max_hp']
        row.update({k: deepcopy(after[k]) for k in ('max_hp', 'stats', 'overland', 'breach_security', 'breach_capacity', 'breach_resistance_armor')})
        definition = p['upgrades'][upgrade] if resolved is None else resolved['values']['definitions'][source_choice['value']]
        result = {'vehicle_id': identity, 'upgrade': upgrade, 'count': config['upgrades'][upgrade], 'cost': cost, 'materials': paid,
                  'definition_clause_id': definition['clause_id'], 'definition_excerpt_sha256': definition['excerpt_sha256']}
        if resolved is not None: result['source_policy'] = deepcopy(resolved)
        _save(row['native_vehicle'], request_id, intent, result, 'upgrades'); validate_record(staged, row)
        return result
    return G.transition(e, owner, apply)


def teach_training(e, trainer, pokemon, *, body_eligible, safe=None):
    import pokemon_teaching as T
    W.require_actors(e, trainer, pokemon); policy(e)
    if body_eligible is not True: raise ValueError('actual appropriate Pokemon control body required')
    def apply(staged, target, teacher):
        T._pokemon(staged, teacher, target)
        if TRAINING in target.spec.get(G.KEY, {}).get('sources', {}): raise ValueError('Vehicle Training is already acquired')
        balance = T._balance(target.spec)
        if balance < 1: raise ValueError('Vehicle Training costs one Tutor Point')
        T.edge_training_hour(staged, teacher, target, SOURCE, TRAINING, safe=safe)
        G._source(target, TRAINING, 'poke_edge', owner_id=target.entity_id, lifetime='permanent',
                  rule_id=SOURCE, tutor_points=1, body_eligible=True)
        target.spec['tutor_points'] = balance - 1
        return {'source_id': TRAINING, 'point_cost': 1}
    return G.transition(e, pokemon, apply, participants=(trainer,))


def training_permission(e, actor):
    policy(e)
    row = actor.spec.get(G.KEY, {}).get('sources', {}).get(TRAINING)
    return bool(actor.kind == 'pokemon' and row and row.get('kind') == 'poke_edge' and
                row.get('rule_id') == SOURCE and row.get('owner_id') == actor.entity_id and
                row.get('tutor_points') == 1 and row.get('body_eligible') is True)


def installed_datajack(e, actor, instance_id):
    import special_entities as S
    device = getattr(e, '_physical_objects', {}).get(instance_id)
    if device is None or any(W.physical_lifecycle(device)[k] for k in ('consumed', 'destroyed', 'disabled', 'suppressed')):
        return False
    for row in getattr(e, '_physical_objects', {}).values():
        if row.get('kind') != 'augmentation_set' or row.get('actor_id') != actor.entity_id: continue
        S.validate_record(e, row)
        if row.get('augmentation_active', True) is not True: continue
        if any(x['instance_id'] == instance_id and x['augmentation_id'] == 'datajack' for x in row['installations']): return True
    return False


def connect_datajack_vehicle(e, pokemon, identity, instance_id, electronics_id, *, enabled, **observation):
    import control_remote as REMOTE
    W.require_actors(e, pokemon); policy(e)
    if enabled is not True: raise ValueError('Datajack vehicle exception requires its explicit optional adoption')
    if pokemon.kind != 'pokemon' or not installed_datajack(e, pokemon, instance_id):
        raise ValueError('actual Pokemon and active installed Datajack required')
    declaration = REMOTE.native_wired_vehicle()
    declaration.update(id='native:datajack-vehicle', capabilities=[], devices=[
        {'host': 'operator', 'module_id': 'augmentation/datajack', 'item_rule_id': None},
        {'host': 'machine', 'module_id': None, 'item_rule_id': None}])
    links = {'devices': [instance_id, electronics_id], 'avatar_id': None, 'node_id': None,
             'recipient_id': None, 'communication_source': None, 'component_id': None}
    return REMOTE.connect(e, pokemon, identity, declaration, links, **observation)


def _refresh_shield(e, row):
    owner = W.actor_index(e).get(row.get('owner_id'))
    if owner is None: raise ValueError('actual vehicle owner scene calendar required')
    scene = owner.spec.get('frequency_state', {}).get('scene', 0)
    C.integer(scene, 'actual vehicle owner scene', 0)
    scene_id = owner.entity_id + ':scene:' + str(scene)
    native = row['native_vehicle']
    if native['shield']['scene_id'] != scene_id:
        config = native['config']; p = policy(e); definition = p['upgrades']['shield_generator']
        native['shield'] = {'scene_id': scene_id, 'temporary_hp': config['upgrades']['shield_generator'] * definition['amount'][p['templates'][config['template']]['column']]}
    return native['shield']


def begin_scene(e, actor, identity):
    W.require_actors(e, actor); policy(e)
    def apply(staged, subject):
        row = _vehicle(staged, identity); W.require_usable_object(row); native = row['native_vehicle']
        if row['owner_id'] != subject.entity_id: raise ValueError('actual vehicle owner scene boundary required')
        return deepcopy(_refresh_shield(staged, row))
    return G.transition(e, actor, apply)


def _salvage(e, row, derived):
    native = row['native_vehicle']
    if row['destroyed'] and native['salvage_id'] is None:
        identity = row['id'] + '/salvage'
        W.register_object(e, identity, location=deepcopy(row['location']), reason='SPOL-053 destroyed vehicle salvage')
        salvage = e._physical_objects[identity]
        salvage['vehicle_salvage'] = {'vehicle_id': row['id'], 'cost': derived['total_cost'],
                                      'value_fraction': [derived['total_cost'], 3], 'source': SOURCE}
        native['salvage_id'] = identity


def defend(e, identity, *, damage_class, total):
    """Consume the vehicle's actual Defense or Special Defense before typing."""
    import combat_damage as DAMAGE
    if damage_class not in ('물리', '특수'): raise ValueError('actual vehicle attack damage class required')
    C.integer(total, 'actual pre-defense attack total', 0)
    row = _vehicle(e, identity); W.require_usable_object(row)
    return DAMAGE.defend(dice=0, attack=total, modifiers=0, defense=row['stats']['def' if damage_class == '물리' else 'spd'], reduction=0)['after_defense']


def hit(e, attacker, identity, *, move_type, after_defense, passenger_after_defense, event_id, reason, breach_policy):
    """Consume resolved defenses, apply actual typing and shared breach producer.

    Each passenger has its own resolved defense input. The actual post-damage
    breach state determines which occupants have lost hull protection.
"""
    import type_state as TYPES
    import repair_breach as B
    import combat_damage as DAMAGE
    import damage_reactions as REACTIONS
    W.require_actors(e, attacker); Q._text(event_id); Q._text(reason); p = policy(e)
    TYPES.validate_attack(e.r, move_type); C.integer(after_defense, 'actual vehicle damage after defense', 0)
    if type(passenger_after_defense) is not dict: raise ValueError('actual passenger defense observations required')
    intent = {'attacker_id': attacker.entity_id, 'vehicle_id': identity, 'type': move_type,
              'after_defense': after_defense, 'passengers': deepcopy(passenger_after_defense), 'reason': reason, 'breach_policy': deepcopy(breach_policy)}
    row = _vehicle(e, identity); replay = _replay(row['native_vehicle'], event_id, intent)
    if replay is not None: return replay
    def apply(staged, actor):
        row = _vehicle(staged, identity); W.require_usable_object(row); derived = validate_record(staged, row)
        steps = int(move_type in ('불꽃', '전기', '땅'))
        alloys = row['native_vehicle']['config']['upgrades']['reinforced_alloys']
        alloy_definition = next((_upgrade_definition(p, receipt) for receipt in row['native_vehicle']['upgrades'].values()
                                 if receipt['intent']['upgrade'] == 'reinforced_alloys'), None)
        if alloys and move_type in alloy_definition['resist']: steps -= 1
        immune = (move_type == '땅' and bool(set(derived['movement']) & {'levitate', 'sky'})) or (alloys and move_type in alloy_definition['immune'])
        multiplier = 0 if immune else staged.r.mech('combat/type-effectiveness')['multiplier_by_net_steps'][str(steps)]
        amount = DAMAGE.scale(after_defense=after_defense, type_multiplier=multiplier)
        shield = _refresh_shield(staged,row); absorbed = min(amount, shield['temporary_hp']); shield['temporary_hp'] -= absorbed
        damage = B.damage(staged, actor, identity, amount - absorbed, breach_policy, event_id='native-hit:' + identity + ':' + event_id, reason=reason)
        exposed = B.exposure(staged, identity)['exposed_passenger_ids']
        if set(passenger_after_defense) != set(exposed): raise ValueError('one resolved defense input per actual exposed passenger required')
        for number in passenger_after_defense.values(): C.integer(number, 'actual passenger damage after defense', 0)
        passengers = []
        for uid in exposed:
            passenger = W.actor_index(staged)[uid]; normal = staged.type_multiplier(move_type, passenger)[0]
            resisted = REACTIONS.resistance_multiplier(staged, normal)
            if resisted is None: raise ValueError('actual passenger resistance step unresolved')
            dealt = DAMAGE.scale(after_defense=passenger_after_defense[uid], type_multiplier=resisted); before = passenger.hp
            staged.take_damage(passenger, dealt)
            passengers.append({'id': uid, 'before': before, 'after': passenger.hp, 'requested': dealt, 'multiplier': _ratio(resisted)})
        _salvage(staged, row, derived)
        result = {'damage': damage, 'type_multiplier': _ratio(multiplier), 'shield_absorbed': absorbed, 'passengers': passengers, 'salvage_id': row['native_vehicle']['salvage_id']}
        _save(row['native_vehicle'], event_id, intent, result); validate_record(staged, row)
        return result
    return G.transition(e, attacker, apply)


def hazard(e, source_actor, identity, *, kind, event_id, reason, hp_loss=0, status=None):
    """Vehicle-only condition/injury immunity; environment reaches exposed crew."""
    import repair_breach as B
    W.require_actors(e, source_actor); policy(e); Q._text(event_id); Q._text(reason)
    if kind not in ('condition', 'injury', 'vacuum', 'hazardous_environment'): raise ValueError('known vehicle exposure required')
    C.integer(hp_loss, 'actual environmental HP loss', 0)
    if status is not None: Q._text(status)
    intent = {'source_actor': source_actor.entity_id, 'vehicle_id': identity, 'kind': kind, 'hp_loss': hp_loss, 'status': status, 'reason': reason}
    row = _vehicle(e, identity); replay = _replay(row['native_vehicle'], event_id, intent)
    if replay is not None: return replay
    def apply(staged, actor):
        row = _vehicle(staged, identity); native = row['native_vehicle']; exposed = []
        if kind in ('vacuum', 'hazardous_environment'):
            for uid in B.exposure(staged, identity)['exposed_passenger_ids']:
                passenger = W.actor_index(staged)[uid]; before = passenger.hp
                if hp_loss: staged.lose_hp(passenger, hp_loss, source=SOURCE)
                if status: staged.apply_status(passenger, status, source=SOURCE, applied_by=actor)
                exposed.append({'id': uid, 'before': before, 'after': passenger.hp})
        result = {'vehicle_id': identity, 'vehicle_immune': True, 'kind': kind, 'passengers': exposed}
        _save(native, event_id, intent, result); return result
    return G.transition(e, source_actor, apply)
