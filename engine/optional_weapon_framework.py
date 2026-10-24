"""Physical Arcane/Steelheart weapons, with attack-local policy and bonds.

Profiles are explicit observations of actual objects, not new catalogue items.
The native weapon ledger owns equipped grants; spec owns the replaceable bond.
"""
from copy import deepcopy
from functools import wraps
import json
from pathlib import Path

import common_checks as C
import skill_modifiers as S
import state_grants as G
import world_entities as W

PROFILE = 'optional_weapon_profile'
BONDS = 'optional_weapon_bonds'
HITS = 'optional_weapon_round_hits'
MARK = '_optional_weapon_framework'
SOURCE = 'ch09-equipment/장비/무기'
TRAINING = 'feat/아케인-훈련'
ARCANIST = 'supp-fantasy/아케니스트'
STEELHEART = 'C2CSV/input/db/feats.csv:R685:main'
STEELHEART_CHOICE = 'steelheart_source_choice'
CALL = 'feat/무기-부름'
MASTER = 'feat/무기의-마스터'
CLAUSES = {'FAN-030', 'FAN-031', 'FAN-063', 'FAN-082', 'FAN-203', 'FAN-209'}
ALIASES = {
    TRAINING: ('아케인 훈련', 'Arcane Training'),
    ARCANIST: ('아케니스트', 'Arcanist'),
    STEELHEART: ('스틸하트', 'Steelheart'),
    CALL: ('무기 부름', 'Call to Arms'),
}


def policy(rules):
    cached = getattr(rules, '_optional_weapon_framework_policy', None)
    if cached is not None:
        return cached
    staged = Path(__file__).resolve().parents[1] / 'data/optional-weapon-framework-policy.json'
    path = staged if staged.is_file() else Path(rules.root) / 'data/optional-weapon-framework-policy.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schema_version') != 1 or set(value.get('clauses', {})) != CLAUSES:
        raise ValueError('exact optional weapon framework policy required')
    indexed = {row['clause_id']: row for row in json.loads((Path(rules.root) / 'data/verification/category2-optional-clause-status.json').read_text(encoding='utf-8'))['rows']}
    for uid, row in value['clauses'].items():
        if row['source'] != indexed[uid]['source']:
            raise ValueError('optional weapon source changed: ' + uid)
    if rules._selected_rule(SOURCE) != SOURCE:
        raise ValueError('selected ordinary weapon policy changed')
    rules._optional_weapon_framework_policy = value
    return value


def owns(actor, feature):
    if feature == CALL:
        # These are capabilities granted by Master of Arms, not separately
        # acquired Call to Arms Features or unproven sheet capability strings.
        import acquired_features as ACQUIRED
        if actor.kind != 'trainer' or ACQUIRED.owned_rule_count(actor, MASTER) != 1:
            return False
        source = 'feature:' + actor.entity_id + ':' + MASTER
        row = actor.spec.get(G.KEY, {}).get('sources', {}).get(source, {})
        capability = ALIASES[CALL][0]
        return (row.get('kind') == 'feature' and row.get('rule_id') == MASTER
                and row.get('owner_id') == actor.entity_id and row.get('lifetime') == 'while_owned'
                and source + ':0' in row.get('effect_sources', ())
                and capability in row.get('grants', {}).get('capabilities', ())
                and capability in G.effective_capabilities(actor, only=(capability,)))
    names = {S.key(x) for x in (feature, *ALIASES[feature])}
    return any(S.key(x) in names for field in ('features', 'feats') for x in actor.spec.get(field, ()))


def require_feature(engine, actor, feature):
    policy(engine.r)
    W.require_actors(engine, actor)
    if actor.kind != 'trainer' or not owns(actor, feature):
        raise ValueError('actual acquired weapon feature required: ' + feature)
    if engine.r._selected_rule(feature) != feature:
        raise ValueError('selected weapon feature changed: ' + feature)
    if feature == CALL:
        # Master and its granted action share this already reviewed source.
        from source_context import verified_source
        reference = policy(engine.r)['clauses']['FAN-209']['source'][0]
        verified_source(engine.r, {'file':reference['file'],'sha256':reference['file_sha256']},
                        label='Master of Arms / Call to Arms')


def arcane_type(engine, actor):
    require_feature(engine, actor, TRAINING)
    if S.rank(engine.r, actor, '오컬트학')[2] < 3:
        raise ValueError('Arcane Training requires Novice Occult')
    import elemental_connection as ELEMENTAL
    choices = ELEMENTAL.choices(engine, actor)
    mystic = any(ELEMENTAL.matches(x, ELEMENTAL.MYSTIC) for field in ('edges', 'feats') for x in actor.spec.get(field, ()))
    if mystic:
        return '노말'
    selected = actor.spec.get('arcane_weapon_type')
    if len(choices) == 1:
        if selected not in (None, choices[0]):
            raise ValueError('Arcane type must use the actual Elemental Connection')
        return choices[0]
    if selected not in choices:
        raise ValueError('one actual Elemental Connection type must be selected')
    return selected


def steelheart(engine, actor):
    if not owns(actor, STEELHEART):
        return False
    require_feature(engine, actor, STEELHEART)
    return True


def quote(engine, grade, market='typical'):
    """Same sourced, explicitly selected regional price band as ordinary gear."""
    table = policy(engine.r)['prices']
    if market not in table or grade not in table[market]:
        raise ValueError('explicit sourced weapon quality and market required')
    return table[market][grade]


def object_profile(engine, instance_id, *, usable=True):
    obj = getattr(engine, '_physical_objects', {}).get(instance_id)
    if obj is None or PROFILE not in obj:
        raise ValueError('actual observed physical weapon required')
    if usable:
        W.require_physical_access(obj)
    row = obj[PROFILE]
    expected = {'schema_version', 'source', 'name', 'kind', 'grade', 'arcane', 'metal', 'moves', 'reason', 'market'}
    if type(row) is not dict or set(row) != expected or row['schema_version'] != 1 or row['source'] != SOURCE:
        raise ValueError('physical weapon profile changed')
    import turn as TURN
    if row['kind'] not in set(TURN.WEAPON_KIND) - {'발 무기'} or row['grade'] not in ('조잡', '간단', '좋음'):
        raise ValueError('four sourced weapon forms and ordinary quality required')
    if type(row['arcane']) is not bool or type(row['metal']) is not bool:
        raise ValueError('explicit Arcane and metal observations required')
    for name in ('name', 'reason'):
        W._text(row[name], 'weapon ' + name)
    quote(engine, row['grade'], row['market'])
    if (type(row['moves']) is not list or any(not isinstance(uid, str) or not uid for uid in row['moves'])
            or len(row['moves']) != len(set(row['moves']))):
        raise ValueError('distinct actual weapon grants required')
    return obj, row


def observe_weapon(engine, actor, instance_id, *, name, kind, grade, arcane, metal,
                   moves=(), market='typical', reason, improvised=None):
    """Observe a real object's profile; does not purchase, equip or create it."""
    W.require_actors(engine, actor)
    obj = getattr(engine, '_physical_objects', {}).get(instance_id)
    if obj is None or actor.entity_id not in (obj.get('owner_id'), obj.get('carrier_id')):
        raise ValueError('actual accessible owned weapon required')
    if obj.get('equipped_by') or PROFILE in obj:
        raise ValueError('observe an unequipped weapon once; profile is persistent')
    row = dict(schema_version=1, source=SOURCE, name=name, kind=kind, grade=grade,
               arcane=arcane, metal=metal, moves=list(moves), reason=reason, market=market)
    def apply(e, a):
        target = e._physical_objects[instance_id]
        target[PROFILE] = deepcopy(row)
        object_profile(e, instance_id)
        if improvised is not None:
            import improvised_weapons as IMPROVISED
            IMPROVISED.configure(e, a, instance_id, **improvised)
        if target.get('item_rule_id'):
            import optional_physical_equipment as OPTIONAL
            known = OPTIONAL.definition(e.r, target['item_rule_id']) if target['item_rule_id'] in OPTIONAL.KINDS else None
            import improvised_weapons as IMPROVISED
            cannon = target['item_rule_id'] == 'item/몬스터볼-캐논'
            if cannon:
                valid = (kind, grade, arcane, name) == (
                    '장거리 사격무기', '좋음', False, e.r.items_mech[target['item_rule_id']]['name'])
            elif known and known.get('weapon_kind'):
                valid = (kind, grade, arcane, name) == (
                    known['weapon_kind'], known.get('weapon_grade', '좋음'), bool(known.get('arcane')), known['name'])
            else:
                valid = IMPROVISED.ruling(e, instance_id) is not None
            if not valid:
                raise ValueError('physical recipe profile must preserve the reviewed catalogue identity')
        validate_loadout(e, a, dict(row, framework_instance=instance_id, instance_id=instance_id, slot='주요손'))
        return deepcopy(row)
    return G.transition(engine, actor, apply)


def profile_for_weapon(engine, actor, weapon):
    uid = weapon.get('framework_instance')
    if uid is None:
        uid = weapon.get('recipe_instance')
        if uid is None:
            return None
        obj = getattr(engine, '_physical_objects', {}).get(uid)
        if obj is None:
            raise ValueError('crafted weapon lost its physical item')
        W.require_physical_access(obj)
        import optional_physical_equipment as OPTIONAL
        definition = OPTIONAL.definition(engine.r, obj.get('item_rule_id'))
        if definition is None or not definition.get('weapon_kind'):
            raise ValueError('crafted weapon lost its selected recipe')
        row = dict(name=definition['name'], kind=definition['weapon_kind'],
                   grade=definition.get('weapon_grade', '좋음'), moves=[],
                   arcane=bool(definition.get('arcane')), metal=False)
    else:
        obj, row = object_profile(engine, uid)
    if any(weapon.get(key) != row[key] for key in ('name', 'kind', 'grade', 'moves')):
        raise ValueError('equipped weapon and physical profile disagree')
    if actor.entity_id not in (obj.get('owner_id'), obj.get('carrier_id'), obj.get('equipped_by')):
        raise ValueError('physical weapon belongs to another holder')
    holder = obj.get('equipped_by') or obj.get('carrier_id')
    if holder not in (None, actor.entity_id):
        raise ValueError('release the actual physical holder before equipment')
    return row


def skill_rank(engine, actor, weapon):
    row = profile_for_weapon(engine, actor, weapon)
    if row and row['arcane']:
        arcane_type(engine, actor)
        return S.rank(engine.r, actor, '오컬트학')[2]
    ranks = [S.rank(engine.r, actor, '전투')[2]]
    if row and row['metal'] and '근접' in row['kind'] and steelheart(engine, actor):
        ranks.extend(S.rank(engine.r, actor, skill)[2] for skill in ('육상', '집중'))
    return max(ranks)


def validate_loadout(engine, actor, weapon):
    row = profile_for_weapon(engine, actor, weapon)
    if row is None:
        return
    rank = skill_rank(engine, actor, weapon)
    if not row['arcane']:
        import weapon_actions as WEAPONS
        for uid in row['moves']:
            WEAPONS.validate_grant(engine, actor, weapon, uid)
        return
    counts = {3: 0, 5: 0}
    for uid in row['moves']:
        grant = policy(engine.r)['arcane_moves'].get(uid)
        if grant is None or engine.r._selected_rule(uid) != uid:
            raise ValueError('selected sourced Arcane Weapon Move required')
        required = grant['rank']
        if actor.kind=='pokemon' and required>4:raise ValueError('Wielder cannot gain weapon moves above Adept')
        if rank < required or row['grade'] == '조잡' or required == 5 and (row['grade'] != '좋음' or weapon.get('slot', '주요손') == '반대손'):
            raise ValueError('Arcane weapon tier prerequisite not met')
        if grant['forms'] and row['kind'] not in grant['forms']:
            raise ValueError('Arcane move requires its printed melee/ranged form')
        counts[required] += 1
    if any(n > 1 for n in counts.values()):
        raise ValueError('Arcane weapon permits one Novice and one Expert grant')


def move_limit(engine, actor, weapon):
    row = profile_for_weapon(engine, actor, weapon)
    validate_loadout(engine, actor, weapon)
    return len(row['moves']) if row and row['arcane'] else None


def crafted_weapon(engine, plan, weapon):
    obj = engine._physical_objects[plan['instance_id']]
    if PROFILE not in obj:
        return dict(weapon, recipe_instance=plan['instance_id'], instance_id=plan['instance_id'])
    _, row = object_profile(engine, plan['instance_id'])
    return {key: deepcopy(row[key]) for key in ('name', 'kind', 'grade', 'moves')} | {'framework_instance': plan['instance_id'], 'instance_id': plan['instance_id']}


def on_equip(engine, actor, key):
    entry = actor.custom_conditions['equipped_weapons'][key]
    uid = entry['weapon'].get('framework_instance')
    if uid is None:
        return
    obj, _ = object_profile(engine, uid)
    entry['instance_id'] = uid
    obj['equipped_by'] = actor.entity_id
    W._set_object_location(obj, {'kind': 'unknown'})


def on_unequip(engine, actor, entry):
    uid = entry['weapon'].get('framework_instance')
    if uid is None:
        return
    obj, _ = object_profile(engine, uid)
    if obj.get('equipped_by') != actor.entity_id:
        raise ValueError('physical weapon holder changed')
    obj.pop('equipped_by', None)
    W._set_object_location(obj, W.location_of(actor))


def equip(engine, actor, instance_id, *, slot='주요손'):
    W.require_actors(engine, actor)
    _, row = object_profile(engine, instance_id)
    def apply(e, a):
        obj, current = object_profile(e, instance_id)
        import improvised_weapons as IMPROVISED
        import optional_physical_equipment as OPTIONAL
        original_weapon = (obj.get('item_rule_id') in OPTIONAL.KINDS
                           and OPTIONAL.definition(e.r, obj['item_rule_id']).get('weapon_kind'))
        if obj.get('item_rule_id') and (IMPROVISED.ruling(e, instance_id) is None or original_weapon):
            if slot != '주요손':
                raise ValueError('crafted catalogue equipment retains its printed slot')
            import items as ITEMS
            ITEMS.register_item(e, a, obj['item_rule_id'], source_instance_id=instance_id)
            return next(k for k, v in a.custom_conditions['equipped_weapons'].items() if v.get('instance_id') == instance_id)
        import turn as TURN
        weapon = {key: deepcopy(current[key]) for key in ('name', 'kind', 'grade', 'moves')}
        weapon.update(framework_instance=instance_id, instance_id=instance_id, slot=slot)
        return TURN.equip_weapon(e, a, weapon)
    return G.transition(engine, actor, apply)


def disarm_skills(engine, actor):
    result = {'combat', 'stealth'}
    for entry in actor.custom_conditions.get('equipped_weapons', {}).values():
        row = profile_for_weapon(engine, actor, entry['weapon'])
        if not row:
            continue
        if row['arcane']:
            arcane_type(engine, actor)
            result.add(S.skill_id(engine.r.skill_policy, '오컬트학', required=True))
        if row['metal'] and '근접' in row['kind'] and steelheart(engine, actor):
            result.update(('athletics', 'focus'))
    return result


def adapt_move(engine, actor, move):
    import living_weapon as LIVING
    borrowed=LIVING.borrowed(engine,actor,move)
    if borrowed is not None:return borrowed
    attack = move.get('_weapon_attack')
    if not attack:
        return move
    if type(attack) is not dict or not isinstance(attack.get('key'), str):
        raise ValueError('actual equipped weapon attack record required')
    if attack.get('source')=='item/몬스터볼-캐논':
        import weapon_actions as WEAPONS
        return WEAPONS.prepare(engine,actor,move,attack['key'])
    if attack.get('intrinsic'):
        import csv_item_capability_contracts as CSV
        actual=CSV.tinkerer_move(actor,engine.r.move(move['id']),engine=engine)
        if actual is None or actual['_weapon_attack']!=attack:
            raise ValueError('intrinsic weapon requires its actual live sourced configuration')
        return actual
    entry = actor.custom_conditions.get('equipped_weapons', {}).get(attack['key'])
    if entry is None:
        raise ValueError('selected weapon is no longer equipped')
    import wielder_capability as WIELDER
    if not LIVING.require_weapon(engine,actor,entry['weapon']):WIELDER.require_weapon(engine,actor,entry['weapon'])
    row = profile_for_weapon(engine, actor, entry['weapon'])
    if row is None:
        return move
    grant_source = (SOURCE if entry.get('item_id') == 'item/몬스터볼-캐논'
                    else entry.get('item_id', SOURCE))
    if move.get('id') not in entry.get('available_moves', ()) or attack.get('source') != grant_source:
        raise ValueError('weapon attack is not granted by this physical source')
    obj = engine._physical_objects[entry['instance_id']]
    if obj.get('equipped_by') != actor.entity_id:
        raise ValueError('attack requires the current physical weapon holder')
    validate_loadout(engine, actor, entry['weapon'])
    out = deepcopy(move)
    struggle = move['id'] == entry['struggle_id']
    alchemy = move['id'] in entry.get('crafted_grants', ())
    rank = skill_rank(engine, actor, entry['weapon'])
    db_bonus = effect_bonus = damage_bonus = 0
    if struggle and rank >= 5:
        db_bonus += 1
    if row['arcane']:
        chosen = arcane_type(engine, actor)
        if struggle or not alchemy:
            out['type'] = chosen
            out['class'] = '특수'
        if chosen == '노말':
            damage_bonus += 5
            effect_bonus += 2
        bond = actor.spec.get(BONDS, {}).get('arcane')
        if bond and owns(actor, ARCANIST) and bond['instance_id'] == entry['instance_id'] and (struggle or not alchemy):
            require_feature(engine, actor, ARCANIST)
            soul = min(3, max(0, S.rank(engine.r, actor, '오컬트학')[2] - 3))
            db_bonus += soul
            effect_bonus += soul
    import turn as TURN
    expected_db = (0 if struggle else TURN.WEAPON_KIND[row['kind']]['db']) + db_bonus
    marker = dict(actor_id=actor.entity_id, instance_id=entry['instance_id'],
                  arcane=row['arcane'], alchemy=alchemy,
                  effect_bonus=effect_bonus, damage_bonus=damage_bonus)
    if MARK in out:
        if out[MARK] != marker or attack['db_bonus'] != expected_db:
            raise ValueError('prepared weapon attack authority changed')
        import improvised_weapons as IMPROVISED
        return IMPROVISED.adapt(engine, actor, out)
    if struggle and rank >= 5:
        out['ac'] -= 1
    out['_weapon_attack']['db_bonus'] = expected_db
    out[MARK] = marker
    import improvised_weapons as IMPROVISED
    return IMPROVISED.adapt(engine, actor, out)


def effect_range_bonus(engine, actor, move):
    prepared = adapt_move(engine, actor, move)
    return prepared.get(MARK, {}).get('effect_bonus', 0)


def damage_roll_bonus(engine, actor, move):
    prepared = adapt_move(engine, actor, move)
    import living_weapon as LIVING
    return prepared.get(MARK, {}).get('damage_bonus', 0)+LIVING.penalty(engine,actor,prepared.get('_weapon_attack',{}).get('key'))


def bond(engine, actor, instance_id, *, family):
    feature = {'arcane': ARCANIST, 'steelheart': CALL}.get(family)
    if feature is None:
        raise ValueError('explicit Arcane or Steelheart bond required')
    require_feature(engine, actor, feature)
    obj, row = object_profile(engine, instance_id)
    if actor.entity_id not in (obj.get('owner_id'), obj.get('carrier_id'), obj.get('equipped_by')):
        raise ValueError('bond requires an accessible actual weapon')
    if family == 'arcane':
        arcane_type(engine, actor)
        if not row['arcane']:
            raise ValueError('Soul Bond requires an Arcane weapon')
    elif not row['metal']:
        raise ValueError('Steelheart Bond requires a metal weapon')
    import turn as TURN
    def apply(e, a):
        if not TURN.spend(e, a, 'extended', feature):
            raise ValueError('Extended weapon bond action not admitted')
        receipt = dict(source=feature, instance_id=instance_id, at=e.elapsed_seconds)
        a.spec.setdefault(BONDS, {})[family] = receipt
        return deepcopy(receipt)
    return G.transition(engine, actor, apply)


def recall(engine, actor, *, family, unwilling=None, skill=None,
           challenger_options=None, defender_options=None, slot='주요손'):
    feature = {'arcane': ARCANIST, 'steelheart': CALL}.get(family)
    if feature is None:
        raise ValueError('explicit weapon bond family required')
    require_feature(engine, actor, feature)
    receipt = actor.spec.get(BONDS, {}).get(family)
    if not receipt:
        raise ValueError('one actual current weapon bond required')
    if (type(receipt) is not dict or set(receipt) != {'source', 'instance_id', 'at'}
            or receipt.get('source') != feature):
        raise ValueError('weapon recall bond authority changed')
    uid = receipt['instance_id']
    obj, profile = object_profile(engine, uid)
    if family == 'arcane':
        arcane_type(engine, actor)
    if family == 'arcane' and not profile['arcane'] or family == 'steelheart' and not profile['metal']:
        raise ValueError('weapon no longer qualifies for its recall bond')
    location, origin = W.effective_location(engine, obj), W.location_of(actor)
    if origin['kind'] != 'grid' or location['kind'] != 'grid' or origin.get('map_id') != location.get('map_id'):
        raise ValueError('recall requires actual positions on the same map')
    from grid import cheb
    if cheb(origin['cell'], location['cell']) > 10:
        raise ValueError('bonded weapon beyond ten metres')
    holder_id = obj.get('equipped_by') or obj.get('carrier_id')
    holder = W.actor_index(engine).get(holder_id) if holder_id else None
    if holder is actor:
        raise ValueError('bonded weapon is already in the caller possession')
    if holder is not None and type(unwilling) is not bool:
        raise ValueError('actual holder willingness must be explicit')
    if holder is None and unwilling not in (None, False):
        raise ValueError('an unheld weapon cannot make an opposed check')
    allowed = ('오컬트학',) if family == 'arcane' else ('육상', '집중')
    skill = skill or max(allowed, key=lambda name: S.rank(engine.r, actor, name)[2])
    if S.skill_id(engine.r.skill_policy, skill) not in {S.skill_id(engine.r.skill_policy, x) for x in allowed}:
        raise ValueError('recall skill does not belong to this bond')
    import turn as TURN
    required = {'주요손', '반대손'} if profile['kind'] in ('대형 근접무기', '장거리 사격무기') else {slot}
    occupied = {s for entry in actor.custom_conditions.get('equipped_weapons', {}).values() for s in entry['slots']}
    occupied.update(s for entry in getattr(actor, '_item_reg', {}).values() for s in entry.get('slots', ()))
    if required & occupied:
        raise ValueError('recall destination hand slots are occupied')
    if holder is not None and unwilling:
        engine._prepare_skill_roll(actor, skill, **(challenger_options or {}))
        engine._prepare_skill_roll(holder, '육상', **(defender_options or {}))
    def apply(e, a, *participants):
        actual_holder = W.actor_index(e).get(holder_id) if holder_id else None
        if not TURN.spend(e, a, 'shift', feature + ':recall'):
            raise ValueError('Shift weapon recall action not admitted')
        if actual_holder is not None and unwilling and not e.opposed_check(a, skill, actual_holder, '육상', challenger_options=challenger_options, defender_options=defender_options):
            return {'recalled': False, 'instance_id': uid, 'opposed': True}
        if actual_holder is not None:
            import items as ITEMS
            registration = next((k for k, v in getattr(actual_holder, '_item_reg', {}).items() if v.get('instance_id') == uid), None)
            if registration is not None:
                ITEMS.unregister_item(e, actual_holder, registration_key=registration)
            else:
                key = next((k for k, v in actual_holder.custom_conditions.get('equipped_weapons', {}).items() if v.get('instance_id') == uid), None)
                if key is not None:
                    TURN.unequip_weapon(e, actual_holder, key)
            carried = actual_holder.spec.get('_carried_load', {}).get('objects', ())
            if any(x['id'] == uid for x in carried):
                import capability_actions as CAP
                CAP.set_carried(e, actual_holder, [x for x in carried if x['id'] != uid], 'bonded weapon recall')
        physical = e._physical_objects[uid]
        physical.pop('carrier_id', None)
        physical['equipped_by'] = a.entity_id
        # This transfer is the actual successful recall, not a copied weapon.
        key = equip(e, a, uid, slot=slot)
        if hasattr(e, 'ground_items'):
            e.ground_items[:] = [x for x in e.ground_items if x.get('weapon_record', {}).get('instance_id') != uid and x.get('instance_id') != uid]
        return {'recalled': True, 'instance_id': uid, 'weapon_key': key, 'opposed': bool(actual_holder is not None and unwilling)}
    return G.transition(engine, actor, apply, participants=() if holder is None else (holder,))


def _steelheart_policy(rules):
    from source_context import verified_source
    value = json.loads((Path(rules.root)/'data/fantasy-q30-source-policy.json').read_text(encoding='utf-8'))['steelheart']
    if value['rule_id'] != STEELHEART:
        raise ValueError('actual registered Steelheart source required')
    verified_source(rules,value['source_reference'],label='Steelheart CSV')
    for definition in value['definitions'].values():
        reference = definition['source']
        verified_source(rules,reference,label='Steelheart definition',
                        source_root='source-audit' if reference['file'].startswith('source-audit/') else 'input')
    return value


def _steelheart_document(value):
    return {'schema':1,'id':'native/steelheart-source','variants':[{
        'rule_id':STEELHEART,'source':value['source_reference'],
        'values':{'variant':{'$input':'source_text'},'definitions':value['definitions']},
        'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
            'choices':list(value['definitions']),
            'question':'Steelheart: complete Korean book prior outgoing hit, or actual incoming CSV with English Melee clarification?'}}}]}


def steelheart_source_choices(engine):
    import source_policy as SOURCE_POLICY
    return SOURCE_POLICY.resolve(engine.r,_steelheart_document(_steelheart_policy(engine.r)))


def _steelheart_selected(engine,actor):
    import source_policy as SOURCE_POLICY
    value = _steelheart_policy(engine.r)
    choice = actor.spec.get(STEELHEART_CHOICE)
    result = SOURCE_POLICY.resolve(engine.r,_steelheart_document(value),decisions={} if choice is None else {'source_text':choice})
    return (value['default'] if choice is None else result['values']['variant']),deepcopy(choice)


def select_steelheart_source(engine,actor,choice):
    import action_lifecycle as ACTION
    require_feature(engine,actor,STEELHEART);ACTION.ensure_resolutions_clear(engine)
    def apply(e,a):
        a.spec[STEELHEART_CHOICE] = deepcopy(choice)
        variant,_ = _steelheart_selected(e,a)
        return variant
    return G.transition(engine,actor,apply)


def _hit_history(engine,holder):
    history = holder.spec.get(HITS)
    if history is None or history['round'] != engine.round_no:
        variant,choice = _steelheart_selected(engine,holder)
        history = {'round':engine.round_no,'targets':[],'receipts':[],
                   'policy_variant':variant,'source_choice':choice}
        holder.spec[HITS] = history
    return history


def _history_variant(engine,history):
    # Unmarked rows were produced by outgoing-any, never by an inferred EN choice.
    if 'policy_variant' not in history:
        return 'korean_book_outgoing'
    value = _steelheart_policy(engine.r)
    variant,choice = history['policy_variant'],history['source_choice']
    if variant not in value['definitions']:
        raise ValueError('original complete Steelheart definition required')
    if choice is None:
        if variant != value['default']:
            raise ValueError('nondefault Steelheart history needs its producing source decision')
    else:
        import root_resolution as RESOLUTION
        document = _steelheart_document(value)
        fixed = {'policy_id':document['id'],'selected_id':STEELHEART,'selected_version':None,
                 'definition_hash':RESOLUTION.fingerprint(document)}
        if (type(choice) is not dict or set(choice) != {'value','reason','scope'} or choice['value'] != variant
                or type(choice['scope']) is not dict or set(choice['scope']) != set(fixed)|{'profile_hash'}
                or any(choice['scope'][key] != wanted for key,wanted in fixed.items())):
            raise ValueError('original scoped Steelheart source decision required')
        if any(not isinstance(text,str) or not text.strip() for text in (choice['reason'],choice['scope']['profile_hash'])):
            raise ValueError('Steelheart source reason and producing profile required')
    return variant


def observe_hit(engine, completion, actor, target):
    """Consume the native completed hit once, including a zero-damage hit."""
    import move_completion as COMPLETE
    result = COMPLETE.recipient_result(completion,target)
    if not result or not result['hit'] or result['cancelled'] or getattr(actor,'side',None) is None or getattr(target,'side',None) is None or actor.side == target.side or actor is target:
        return
    token = completion['id'] + ':' + target.entity_id
    original_id = completion.get('received',{}).get(target.entity_id,{}).get('original_id',target.entity_id)
    move = completion.get('target_moves',{}).get(original_id,completion['move'])
    for holder,foe,outgoing in ((actor,target,True),(target,actor,False)):
        if not owns(holder,STEELHEART):
            continue
        steelheart(engine,holder)
        history = _hit_history(engine,holder)
        if token in history['receipts']:
            continue
        variant = _history_variant(engine,history)
        attack = move.get('_weapon_attack')
        if outgoing and foe.entity_id in history['targets'] and attack and attack.get('source') == SOURCE:
            # Native preparation authenticates ordinary Weapon Attacks too;
            # an optional physical profile is not a printed Tick prerequisite.
            if attack['key'] in holder.custom_conditions.get('equipped_weapons',{}):
                import attack_damage_history as HISTORY
                HISTORY.received_loss(engine,foe,engine.tick_loss(foe),source=STEELHEART,move=move)
        qualifies = outgoing and variant == 'korean_book_outgoing'
        if not outgoing and variant == 'english_incoming_melee':
            import weapon_actions as WEAPONS
            qualifies = WEAPONS.range_spec(engine,move,actor).get('origin') == 'melee'
        if qualifies and foe.entity_id not in history['targets']:
            history['targets'].append(foe.entity_id)
        history['receipts'].append(token)


def validate_world(engine, index):
    for uid, obj in getattr(engine, '_physical_objects', {}).items():
        if PROFILE in obj:
            object_profile(engine, uid, usable=False)
    for actor in index.values():
        bonds = actor.spec.get(BONDS, {})
        if type(bonds) is not dict:
            raise ValueError('weapon bonds must be a family mapping')
        for family, row in bonds.items():
            feature = {'arcane': ARCANIST, 'steelheart': CALL}.get(family)
            if feature is None or type(row) is not dict or set(row) != {'source', 'instance_id', 'at'} or row['source'] != feature:
                raise ValueError('weapon bond source/identity changed')
            require_feature(engine, actor, feature)
            _, profile = object_profile(engine, row['instance_id'], usable=False)
            if (family == 'arcane' and not profile['arcane']) or (family == 'steelheart' and not profile['metal']):
                raise ValueError('weapon no longer qualifies for its bond')
            C.integer(row['at'], 'bond creation time', 0)
            if row['at'] > engine.elapsed_seconds:
                raise ValueError('weapon bond creation is in the future')
        history = actor.spec.get(HITS)
        if history is not None:
            legacy = {'round','targets','receipts'}
            if type(history) is not dict or set(history) not in (legacy,legacy|{'policy_variant','source_choice'}):
                raise ValueError('weapon hit history shape changed')
            _history_variant(engine,history)
            C.integer(history['round'], 'weapon hit history round', 0)
            if history['round'] > engine.round_no:
                raise ValueError('weapon hit history round is in the future')
            for field in ('targets', 'receipts'):
                values = history[field]
                if type(values) is not list or any(not isinstance(x, str) or not x for x in values) or len(values) != len(set(values)):
                    raise ValueError('weapon hit history identities changed')
            if any(uid not in index for uid in history['targets']):
                raise ValueError('weapon hit history target is absent')
        for entry in actor.custom_conditions.get('equipped_weapons', {}).values():
            if entry['weapon'].get('framework_instance') or entry['weapon'].get('recipe_instance'):
                profile_for_weapon(engine, actor, entry['weapon'])
                validate_loadout(engine, actor, entry['weapon'])
                uid = entry['instance_id']
                if engine._physical_objects[uid].get('equipped_by') != actor.entity_id:
                    raise ValueError('equipped physical weapon relation changed')
    import improvised_weapons as IMPROVISED
    IMPROVISED.validate_world(engine)
    return True


def atomic_move(fn):
    """New interested attack paths commit native costs and consequences together."""
    @wraps(fn)
    def run(engine, attacker, *args, **kwargs):
        import living_weapon as LIVING
        interested = owns(attacker, STEELHEART) or any(entry['weapon'].get('framework_instance') or entry['weapon'].get('recipe_instance') for entry in attacker.custom_conditions.get('equipped_weapons', {}).values())
        # A holder may receive the prior Melee hit from an ordinary foe. Keep
        # that same native completion/payment/history within this transaction.
        interested = interested or any(owns(c,STEELHEART) for c in W.actor_index(engine).values())
        interested = interested or LIVING.relation(engine,attacker) is not None
        import cleanse_tags as CLEANSE
        equipped={entry.get('instance_id') for entry in attacker.custom_conditions.get('equipped_weapons',{}).values()}
        interested = interested or any(((CLEANSE.attached_appendage(obj) or {}).get('actor_id')==attacker.entity_id
            or CLEANSE.attached_weapon(obj) in equipped-{None})
            and not any(W.physical_lifecycle(obj)[key] for key in ('consumed','destroyed'))
            for obj in getattr(engine,'_physical_objects',{}).values())
        if not interested or getattr(engine, '_optional_weapon_atomic', False):
            return fn(engine, attacker, *args, **kwargs)
        pending = []
        def apply(e, a):
            copied_args, copied_kwargs = G._stage_transition_payload(engine, e, (args, kwargs))
            e._optional_weapon_atomic = True
            try:
                return fn(e, a, *copied_args, **copied_kwargs)
            except Exception as error:
                import passive_events as EVENTS, heavy_injury_adapter as HEAVY
                if (type(error) is EVENTS.PassiveEventPending and
                        e._passive_pending == error.event_id and error.event_id in e._passive_events):
                    pending.append((EVENTS.PassiveEventPending, error.event_id))
                    return None
                if (type(error) is HEAVY.HeavyPending and
                        e._heavy_pending == error.event_id and error.event_id in e._heavy_events):
                    pending.append((HEAVY.HeavyPending, error.event_id))
                    return None
                raise
            finally:
                del e._optional_weapon_atomic
        result = G.transition(engine, attacker, apply, include_grid=engine.grid is not None, include_rulings=True)
        if pending:
            exception, event_id = pending[0]
            raise exception(event_id)
        return result
    return run
